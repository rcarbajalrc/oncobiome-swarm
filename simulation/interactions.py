"""Resolución de interacciones físicas entre agentes.

Las interacciones son DETERMINISTAS (no LLM). Ocurren después de que
todos los agentes han tomado sus decisiones, antes de la difusión.

Parámetros calibrados contra seed biológico KRAS G12D PDAC.
Fuentes:
  PMC4655885 (doubling times)
  ScienceDirect 2020 (CD8+ kill rates)
  Nature Comm 2021 (additive cytotoxicity)
  Frontiers/Medicine 2024 (M2 bias)
  Nat Immunol 2021 (NK IL-6 suppression)
  Immunity 2023 (DC maturation suppression by KRAS G12D)
  Clin Cancer Res 2020 (NK kill rates in PDAC)

Sprint 4: añadidas interacciones NK y DC.
  _nk_attacks(): NK mata tumor con supresión IL-6
  _dc_maturation(): DC madura acumulando ciclos con IFN-γ
  _dc_activates_cd8(): DC madura aumenta kill_rate CD8+ en radio
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import numpy as np

from config import get_config
from models.cytokine_state import CytokineType

if TYPE_CHECKING:
    from simulation.environment import Environment

logger = logging.getLogger(__name__)


class InteractionResolver:
    def __init__(self) -> None:
        cfg = get_config()
        self.immune_kill_rate = cfg.immune_kill_rate
        self.m1_kill_rate     = cfg.macrophage_m1_kill_rate
        self.phyto_damage     = cfg.phyto_damage_rate
        self.radius           = cfg.proliferation_radius
        # Sprint 4: NK parameters
        self.nk_kill_rate     = cfg.nk_kill_rate
        self.nk_il6_threshold = cfg.nk_il6_suppression_threshold
        self.nk_il6_factor    = cfg.nk_il6_suppression_factor
        # Sprint 4: DC parameters
        self.dc_ifng_threshold   = cfg.dc_maturation_ifng_threshold
        self.dc_maturation_cycles = cfg.dc_maturation_cycles
        self.dc_boost            = cfg.dc_activation_boost
        self.dc_radius           = cfg.dc_activation_radius

    def resolve(self, env: "Environment") -> None:
        """Ejecuta todas las interacciones físicas en el orden correcto.

        Orden: primero kills (reducen población), luego polarización
        y activación (modifican estado), luego señalización metabólica.
        """
        self._immune_attacks(env)
        self._nk_attacks(env)            # Sprint 4
        self._macrophage_attacks(env)
        self._phyto_attacks(env)
        self._macrophage_polarisation(env)
        self._dc_maturation(env)         # Sprint 4
        self._dc_activates_cd8(env)      # Sprint 4
        self._vegf_angiogenesis(env)

    # ── CD8+ attacks ──────────────────────────────────────────────────────────

    def _immune_attacks(self, env: "Environment") -> None:
        """ImmuneCell adyacente a TumorCell: probabilidad de muerte calibrada.

        Escape por IL-6: KRAS G12D activa JAK-STAT3 → suprime actividad CD8+.
        Kill_prob reducida 40% cuando IL-6 local > 0.06 (umbral calibrado PDAC).
        Fuente: Frontiers/Medicine 2024; ScienceDirect 2020 (~50% kill/48h E:T 10:1).

        DC boost: si hay una DendriticCell madura en radio dc_activation_radius,
        el kill_rate efectivo se incrementa en dc_activation_boost.
        """
        from agents.immune_cell import ImmuneCell
        from agents.tumor_cell import TumorCell

        cfg = get_config()

        for agent in list(env.agents.values()):
            if not isinstance(agent, ImmuneCell) or not agent.state.alive:
                continue

            # Verificar si hay DC madura en radio → boost de kill_rate
            dc_boost = self._get_dc_boost(agent.state.position, env)
            effective_kill_rate = self.immune_kill_rate + dc_boost

            nearby = env.get_agents_in_radius(agent.state.position, self.radius)
            for target in nearby:
                if not isinstance(target, TumorCell) or not target.state.alive:
                    continue

                kill_prob = agent.state.energy * effective_kill_rate
                il6_at_tumor = env.sample_cytokine(
                    target.state.position, CytokineType.IL6.value
                )
                if il6_at_tumor > cfg.il6_immune_suppression_threshold:
                    kill_prob *= cfg.il6_immune_suppression_factor

                if np.random.random() < kill_prob:
                    target.state.alive = False
                    agent.state.metadata["kills_count"] = (
                        agent.state.metadata.get("kills_count", 0) + 1
                    )
                    boost_note = f" [DC+{dc_boost:.2f}]" if dc_boost > 0 else ""
                    env.log_event(
                        f"ImmuneCell {agent.state.agent_id} eliminó TumorCell "
                        f"{target.state.agent_id} "
                        f"(p={kill_prob:.2f} IL-6={il6_at_tumor:.3f}{boost_note})"
                    )
                    agent.state.energy = max(0.0, agent.state.energy - 0.1)

    # ── NK attacks — Sprint 4 ─────────────────────────────────────────────────

    def _nk_attacks(self, env: "Environment") -> None:
        """NKCell adyacente a TumorCell: kill por missing self.

        Mecanismo: NK reconocen ausencia de MHC-I (downregulado por KRAS G12D).
        Supresión por IL-6: Nat Immunol 2021 — IL-6 impairs NK cytotoxicity.
        Kill rate inferior a CD8+ (0.10 vs 0.15) por mayor resistencia KRAS G12D.

        DC boost también aplica a NK: DC maduras activan tanto CD8+ como NK.
        """
        from agents.nk_cell import NKCell
        from agents.tumor_cell import TumorCell

        for agent in list(env.agents.values()):
            if not isinstance(agent, NKCell) or not agent.state.alive:
                continue

            # DC boost aplica también a NK
            dc_boost = self._get_dc_boost(agent.state.position, env)
            effective_kill_rate = self.nk_kill_rate + dc_boost

            nearby = env.get_agents_in_radius(agent.state.position, self.radius)
            for target in nearby:
                if not isinstance(target, TumorCell) or not target.state.alive:
                    continue

                kill_prob = agent.state.energy * effective_kill_rate
                il6_at_tumor = env.sample_cytokine(
                    target.state.position, CytokineType.IL6.value
                )
                # NK más sensibles a la supresión por IL-6 que CD8+
                if il6_at_tumor > self.nk_il6_threshold:
                    kill_prob *= self.nk_il6_factor

                if np.random.random() < kill_prob:
                    target.state.alive = False
                    agent.state.metadata["kills_count"] = (
                        agent.state.metadata.get("kills_count", 0) + 1
                    )
                    env.log_event(
                        f"NKCell {agent.state.agent_id} eliminó TumorCell "
                        f"{target.state.agent_id} "
                        f"(p={kill_prob:.2f} IL-6={il6_at_tumor:.3f})"
                    )
                    agent.state.energy = max(0.0, agent.state.energy - 0.08)

    # ── Macrophage attacks ────────────────────────────────────────────────────

    def _macrophage_attacks(self, env: "Environment") -> None:
        """MacrophageAgent M1 adyacente a TumorCell."""
        from agents.macrophage_agent import MacrophageAgent
        from agents.tumor_cell import TumorCell

        for agent in list(env.agents.values()):
            if not isinstance(agent, MacrophageAgent) or not agent.state.alive:
                continue
            if agent.state.metadata.get("polarization") != "M1":
                continue
            nearby = env.get_agents_in_radius(agent.state.position, self.radius)
            for target in nearby:
                if not isinstance(target, TumorCell) or not target.state.alive:
                    continue
                if np.random.random() < self.m1_kill_rate:
                    target.state.alive = False
                    env.log_event(
                        f"MacroM1 {agent.state.agent_id} eliminó TumorCell "
                        f"{target.state.agent_id}"
                    )

    # ── Phytochemical attacks ─────────────────────────────────────────────────

    def _phyto_attacks(self, env: "Environment") -> None:
        """PhytochemicalAgent adyacente a TumorCell."""
        from agents.phytochemical_agent import PhytochemicalAgent
        from agents.tumor_cell import TumorCell

        for agent in list(env.agents.values()):
            if not isinstance(agent, PhytochemicalAgent) or not agent.state.alive:
                continue
            nearby = env.get_agents_in_radius(agent.state.position, self.radius)
            for target in nearby:
                if not isinstance(target, TumorCell) or not target.state.alive:
                    continue
                damage = self.phyto_damage * agent.state.metadata.get("concentration", 1.0)
                target.state.energy = max(0.0, target.state.energy - damage)
                if target.state.energy == 0.0:
                    target.state.alive = False
                    env.log_event(
                        f"PhytoAgent {agent.state.agent_id} eliminó TumorCell "
                        f"{target.state.agent_id} por agotamiento"
                    )

    # ── Macrophage polarisation ───────────────────────────────────────────────

    def _macrophage_polarisation(self, env: "Environment") -> None:
        """Polarización M1/M2 calibrada para sesgo pro-tumoral KRAS G12D."""
        from agents.macrophage_agent import MacrophageAgent

        cfg = get_config()
        for agent in env.agents.values():
            if not isinstance(agent, MacrophageAgent) or not agent.state.alive:
                continue
            pos = agent.state.position
            ifng = env.sample_cytokine(pos, CytokineType.IFNG.value)
            il6  = env.sample_cytokine(pos, CytokineType.IL6.value)

            old_pol = agent.state.metadata.get("polarization", "M0")
            if ifng >= cfg.m1_polarisation_ifng_threshold:
                new_pol = "M1"
            elif il6 >= cfg.m2_polarisation_il6_threshold and ifng < cfg.m1_polarisation_ifng_threshold:
                new_pol = "M2"
            else:
                new_pol = "M0"

            if new_pol != old_pol:
                agent.state.metadata["polarization"] = new_pol
                env.log_event(
                    f"Macrophage {agent.state.agent_id} repolarizó: {old_pol} → {new_pol}"
                )

    # ── DC maturation — Sprint 4 ──────────────────────────────────────────────

    def _dc_maturation(self, env: "Environment") -> None:
        """DC madura acumulando ciclos con IFN-γ > umbral.

        Estado: immature → maturing (acumula ifng_cycles_above) → mature.
        La maduración es progresiva — requiere dc_maturation_cycles ciclos
        consecutivos con IFN-γ > dc_maturation_ifng_threshold.

        En KRAS G12D: proceso suprimido (Immunity 2023) → umbral más alto
        y proceso más lento que en TME normal.
        """
        from agents.dendritic_cell import DendriticCell

        for agent in env.agents.values():
            if not isinstance(agent, DendriticCell) or not agent.state.alive:
                continue

            pos  = agent.state.position
            ifng = env.sample_cytokine(pos, CytokineType.IFNG.value)
            meta = agent.state.metadata

            current_state = meta.get("maturation_state", "immature")
            cycles_above  = meta.get("ifng_cycles_above", 0)

            if current_state == "mature":
                continue  # ya madura, no cambia

            if ifng > self.dc_ifng_threshold:
                cycles_above += 1
                meta["ifng_cycles_above"] = cycles_above

                if current_state == "immature" and cycles_above >= 1:
                    meta["maturation_state"] = "maturing"
                    env.log_event(
                        f"DendriticCell {agent.state.agent_id}: "
                        f"immature → maturing (IFN-γ={ifng:.3f})"
                    )
                elif current_state == "maturing" and cycles_above >= self.dc_maturation_cycles:
                    meta["maturation_state"] = "mature"
                    meta["ifng_cycles_above"] = 0
                    env.log_event(
                        f"DendriticCell {agent.state.agent_id}: "
                        f"maturing → MATURE (tras {self.dc_maturation_cycles} ciclos IFN-γ)"
                    )
            else:
                # Sin IFN-γ: resetear contador pero no retroceder estado
                if current_state == "maturing":
                    meta["ifng_cycles_above"] = max(0, cycles_above - 1)

    # ── DC activates CD8+ — Sprint 4 ─────────────────────────────────────────

    def _dc_activates_cd8(self, env: "Environment") -> None:
        """DC madura aumenta temporalmente el kill_rate efectivo de CD8+ cercanos.

        Mecanismo: la activación ya está implementada en _immune_attacks()
        y _nk_attacks() vía _get_dc_boost(). Esta función loguea el evento
        para trazabilidad y actualiza el metadata de CD8+ si hay boost activo.

        El boost es TRANSITORIO — solo aplica durante el ciclo en que la DC
        madura está presente en el radio. No es un buff permanente.
        """
        from agents.dendritic_cell import DendriticCell
        from agents.immune_cell import ImmuneCell
        from agents.nk_cell import NKCell

        for dc in env.agents.values():
            if not isinstance(dc, DendriticCell) or not dc.state.alive:
                continue
            if dc.state.metadata.get("maturation_state") != "mature":
                continue

            nearby = env.get_agents_in_radius(dc.state.position, self.dc_radius)
            activated = []
            for agent in nearby:
                if isinstance(agent, (ImmuneCell, NKCell)) and agent.state.alive:
                    activated.append(agent.state.agent_id[:8])

            if activated:
                env.log_event(
                    f"DendriticCell {dc.state.agent_id} (mature) activando "
                    f"{len(activated)} células inmunes en radio {self.dc_radius:.0f}: "
                    f"{','.join(activated[:3])}{'...' if len(activated) > 3 else ''}"
                )

    # ── Helper: DC boost ──────────────────────────────────────────────────────

    def _get_dc_boost(
        self,
        position: tuple[float, float],
        env: "Environment",
    ) -> float:
        """Retorna el boost de kill_rate si hay una DC madura en radio dc_activation_radius.

        Retorna 0.0 si no hay DC madura cercana.
        El boost es el dc_activation_boost configurado (default: 0.20).
        """
        from agents.dendritic_cell import DendriticCell

        nearby = env.get_agents_in_radius(position, self.dc_radius)
        for agent in nearby:
            if (
                isinstance(agent, DendriticCell)
                and agent.state.alive
                and agent.state.metadata.get("maturation_state") == "mature"
            ):
                return self.dc_boost
        return 0.0

    # ── VEGF angiogenesis ─────────────────────────────────────────────────────

    def _vegf_angiogenesis(self, env: "Environment") -> None:
        """TumorCell hipóxica (energy < 0.30) emite VEGF.

        Mecanismo: HIF-1α → VEGF en hipoxia es canónico en KRAS G12D.
        KRAS G12D tiene mayor señal HIF-1α → VEGF que tumores KRAS WT.
        Emit calibrado a 0.25 (aumentado de 0.20 — mayor angiogénesis PDAC).
        """
        from agents.tumor_cell import TumorCell

        for agent in env.agents.values():
            if not isinstance(agent, TumorCell) or not agent.state.alive:
                continue
            if agent.state.energy < 0.30:
                env.emit_cytokine(
                    agent.state.position, CytokineType.VEGF.value, 0.25
                )
                env.log_event(
                    f"TumorCell {agent.state.agent_id} hipóxica "
                    f"(e={agent.state.energy:.2f}) emite VEGF"
                )
