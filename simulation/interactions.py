"""Resolución de interacciones físicas entre agentes.

Sprint 4: NK y DC interactions.
Sprint 7B: apoptosis hipóxica, migración consciente de densidad, métricas TME.
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
        self.immune_kill_rate    = cfg.immune_kill_rate
        self.m1_kill_rate        = cfg.macrophage_m1_kill_rate
        self.phyto_damage        = cfg.phyto_damage_rate
        self.radius              = cfg.proliferation_radius
        self.nk_kill_rate        = cfg.nk_kill_rate
        self.nk_il6_threshold    = cfg.nk_il6_suppression_threshold
        self.nk_il6_factor       = cfg.nk_il6_suppression_factor
        self.dc_ifng_threshold   = cfg.dc_maturation_ifng_threshold
        self.dc_maturation_cycles = cfg.dc_maturation_cycles
        self.dc_boost            = cfg.dc_activation_boost
        self.dc_radius           = cfg.dc_activation_radius

    def resolve(self, env: "Environment") -> None:
        self._immune_attacks(env)
        self._nk_attacks(env)
        self._macrophage_attacks(env)
        self._phyto_attacks(env)
        self._macrophage_polarisation(env)
        self._dc_maturation(env)
        self._dc_activates_cd8(env)
        self._vegf_angiogenesis(env)
        self._tumor_hypoxia_check(env)    # Sprint 7B
        self._compute_tme_metrics(env)    # Sprint 7B

    # ── CD8+ attacks ──────────────────────────────────────────────────────────

    def _immune_attacks(self, env: "Environment") -> None:
        from agents.immune_cell import ImmuneCell
        from agents.tumor_cell import TumorCell

        cfg = get_config()
        for agent in list(env.agents.values()):
            if not isinstance(agent, ImmuneCell) or not agent.state.alive:
                continue
            dc_boost = self._get_dc_boost(agent.state.position, env)
            effective_kill_rate = self.immune_kill_rate + dc_boost
            nearby = env.get_agents_in_radius(agent.state.position, self.radius)
            for target in nearby:
                if not isinstance(target, TumorCell) or not target.state.alive:
                    continue
                kill_prob = agent.state.energy * effective_kill_rate
                il6_at_tumor = env.sample_cytokine(target.state.position, CytokineType.IL6.value)
                if il6_at_tumor > cfg.il6_immune_suppression_threshold:
                    kill_prob *= cfg.il6_immune_suppression_factor
                if np.random.random() < kill_prob:
                    target.state.alive = False
                    agent.state.metadata["kills_count"] = agent.state.metadata.get("kills_count", 0) + 1
                    boost_note = f" [DC+{dc_boost:.2f}]" if dc_boost > 0 else ""
                    env.log_event(
                        f"ImmuneCell {agent.state.agent_id} eliminó TumorCell "
                        f"{target.state.agent_id} (p={kill_prob:.2f} IL-6={il6_at_tumor:.3f}{boost_note})"
                    )
                    agent.state.energy = max(0.0, agent.state.energy - 0.1)

    # ── NK attacks ────────────────────────────────────────────────────────────

    def _nk_attacks(self, env: "Environment") -> None:
        from agents.nk_cell import NKCell
        from agents.tumor_cell import TumorCell

        for agent in list(env.agents.values()):
            if not isinstance(agent, NKCell) or not agent.state.alive:
                continue
            dc_boost = self._get_dc_boost(agent.state.position, env)
            effective_kill_rate = self.nk_kill_rate + dc_boost
            nearby = env.get_agents_in_radius(agent.state.position, self.radius)
            for target in nearby:
                if not isinstance(target, TumorCell) or not target.state.alive:
                    continue
                kill_prob = agent.state.energy * effective_kill_rate
                il6_at_tumor = env.sample_cytokine(target.state.position, CytokineType.IL6.value)
                if il6_at_tumor > self.nk_il6_threshold:
                    kill_prob *= self.nk_il6_factor
                if np.random.random() < kill_prob:
                    target.state.alive = False
                    agent.state.metadata["kills_count"] = agent.state.metadata.get("kills_count", 0) + 1
                    env.log_event(
                        f"NKCell {agent.state.agent_id} eliminó TumorCell "
                        f"{target.state.agent_id} (p={kill_prob:.2f} IL-6={il6_at_tumor:.3f})"
                    )
                    agent.state.energy = max(0.0, agent.state.energy - 0.08)

    # ── Macrophage attacks ────────────────────────────────────────────────────

    def _macrophage_attacks(self, env: "Environment") -> None:
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
                        f"MacroM1 {agent.state.agent_id} eliminó TumorCell {target.state.agent_id}"
                    )

    # ── Phytochemical attacks ─────────────────────────────────────────────────

    def _phyto_attacks(self, env: "Environment") -> None:
        from agents.phytochemical_agent import PhytochemicalAgent
        from agents.tumor_cell import TumorCell

        for agent in list(env.agents.values()):
            if not isinstance(agent, PhytochemicalAgent) or not agent.state.alive:
                continue
            nearby = env.get_agents_in_radius(agent.state.position, self.radius)
            for target in nearby:
                if not isinstance(target, TumorCell) or not target.state.alive:
                    continue
                damage = self.phyto_damage * agent.state.energy
                target.state.energy = max(0.0, target.state.energy - damage)
                if target.state.energy <= 0:
                    target.state.alive = False
                    env.log_event(
                        f"Phyto {agent.state.agent_id} eliminó TumorCell {target.state.agent_id}"
                    )

    # ── Macrophage polarisation ───────────────────────────────────────────────

    def _macrophage_polarisation(self, env: "Environment") -> None:
        from agents.macrophage_agent import MacrophageAgent

        cfg = get_config()
        for agent in list(env.agents.values()):
            if not isinstance(agent, MacrophageAgent) or not agent.state.alive:
                continue
            pos = agent.state.position
            vegf = env.sample_cytokine(pos, CytokineType.VEGF.value)
            ifng = env.sample_cytokine(pos, CytokineType.IFNG.value)
            il6  = env.sample_cytokine(pos, CytokineType.IL6.value)
            current = agent.state.metadata.get("polarization", "M0")
            if ifng > cfg.m1_polarisation_ifng_threshold:
                agent.state.metadata["polarization"] = "M1"
            elif il6 > cfg.m2_polarisation_il6_threshold or vegf > cfg.m2_polarisation_il6_threshold:
                agent.state.metadata["polarization"] = "M2"
            else:
                agent.state.metadata["polarization"] = "M0"
            new = agent.state.metadata["polarization"]
            if current != new:
                env.log_event(
                    f"Macrophage {agent.state.agent_id}: {current}→{new} "
                    f"(IL6={il6:.3f} VEGF={vegf:.3f} IFNg={ifng:.3f})"
                )

    # ── DC maturation ─────────────────────────────────────────────────────────

    def _dc_maturation(self, env: "Environment") -> None:
        from agents.dendritic_cell import DendriticCell

        for agent in list(env.agents.values()):
            if not isinstance(agent, DendriticCell) or not agent.state.alive:
                continue
            pos = agent.state.position
            ifng = env.sample_cytokine(pos, CytokineType.IFNG.value)
            state = agent.state.metadata.get("maturation_state", "immature")
            if ifng >= self.dc_ifng_threshold:
                cycles = agent.state.metadata.get("ifng_cycles_above", 0) + 1
                agent.state.metadata["ifng_cycles_above"] = cycles
                if cycles >= self.dc_maturation_cycles and state != "mature":
                    agent.state.metadata["maturation_state"] = "mature"
                    agent.state.metadata["mature"] = True
                    env.log_event(
                        f"DendriticCell {agent.state.agent_id} maduró "
                        f"(IFN-γ={ifng:.3f}, ciclos={cycles})"
                    )
                elif state == "immature":
                    agent.state.metadata["maturation_state"] = "maturing"
            else:
                agent.state.metadata["ifng_cycles_above"] = 0
                if state == "maturing":
                    agent.state.metadata["maturation_state"] = "immature"

    def _dc_activates_cd8(self, env: "Environment") -> None:
        from agents.dendritic_cell import DendriticCell
        from agents.immune_cell import ImmuneCell

        for agent in list(env.agents.values()):
            if not isinstance(agent, DendriticCell) or not agent.state.alive:
                continue
            if agent.state.metadata.get("maturation_state", "immature") != "mature":
                continue
            nearby = env.get_agents_in_radius(agent.state.position, self.dc_radius)
            for target in nearby:
                if not isinstance(target, ImmuneCell) or not target.state.alive:
                    continue
                target.state.energy = min(1.0, target.state.energy + self.dc_boost)

    # ── VEGF angiogenesis ─────────────────────────────────────────────────────

    def _vegf_angiogenesis(self, env: "Environment") -> None:
        """Tumor cells con energía < 0.30 son hipóxicas y emiten VEGF (HIF-1α).

        Umbral calibrado: energy < 0.30 = hipoxia energética (sin O₂).
        Tests esperan: energy=0.25 → VEGF emitido, energy=0.50 → sin VEGF.
        """
        from agents.tumor_cell import TumorCell

        cfg = get_config()
        for agent in list(env.agents.values()):
            if not isinstance(agent, TumorCell) or not agent.state.alive:
                continue
            # Hipoxia energética: energy < 0.30 → HIF-1α activa VEGF
            if agent.state.energy < 0.30:
                env.emit_cytokine(
                    agent.state.position,
                    CytokineType.VEGF.value,
                    cfg.cytokine_emit_amount
                )

    # ── Sprint 7B: Apoptosis hipóxica por densidad ───────────────────────────

    def _tumor_hypoxia_check(self, env: "Environment") -> None:
        """Apoptosis por hipoxia de densidad — reemplaza cap artifact.

        Células tumorales rodeadas de ≥6 vecinas en radio 8 entran en hipoxia
        y pueden morir (p=0.15). Más realista que el cap arbitrario.
        Las muertas se eliminan del entorno en este mismo ciclo.
        """
        from agents.tumor_cell import TumorCell

        killed = 0
        for agent in list(env.agents.values()):
            if not isinstance(agent, TumorCell) or not agent.state.alive:
                continue
            if agent.check_hypoxia(env):
                agent.state.alive = False
                killed += 1

        if killed > 0:
            dead_ids = [aid for aid, a in env.agents.items() if not a.state.alive]
            for aid in dead_ids:
                env.remove_agent(aid)
            logger.debug("Hipoxia: %d TumorCells eliminadas", killed)

    # ── Sprint 7B: Métricas TME cuantitativas ────────────────────────────────

    def _compute_tme_metrics(self, env: "Environment") -> None:
        """Calcula VEGF:IFN-γ ratio, sanctuary score y fracción hipóxica por ciclo."""
        from agents.tumor_cell import TumorCell
        from agents.immune_cell import ImmuneCell
        from agents.nk_cell import NKCell

        tumors = [a for a in env.agents.values()
                  if isinstance(a, TumorCell) and a.state.alive]
        immunes = [a for a in env.agents.values()
                   if (isinstance(a, ImmuneCell) or isinstance(a, NKCell)) and a.state.alive]

        total_vegf = sum(
            env.sample_cytokine(t.state.position, CytokineType.VEGF.value)
            for t in tumors
        ) if tumors else 0.0
        total_ifng = sum(
            env.sample_cytokine(t.state.position, CytokineType.IFNG.value)
            for t in tumors
        ) if tumors else 0.0
        vegf_ifng_ratio = total_vegf / max(total_ifng, 0.001)

        sanctuary_score = 0.0
        if tumors and immunes:
            dists = []
            for t in tumors[:10]:
                for i in immunes[:10]:
                    tx, ty = t.state.position
                    ix, iy = i.state.position
                    dists.append(((tx - ix) ** 2 + (ty - iy) ** 2) ** 0.5)
            sanctuary_score = sum(dists) / len(dists) if dists else 0.0

        hypoxic = sum(1 for t in tumors if t.state.metadata.get("hypoxic", False))
        hypoxic_fraction = hypoxic / max(len(tumors), 1)

        if not hasattr(env, "tme_metrics"):
            env.tme_metrics = {}
        env.tme_metrics = {
            "cycle": env.cycle,
            "vegf_ifng_ratio": round(vegf_ifng_ratio, 2),
            "sanctuary_score": round(sanctuary_score, 2),
            "hypoxic_fraction": round(hypoxic_fraction, 3),
            "n_tumors": len(tumors),
            "n_immunes": len(immunes),
        }

    # ── DC boost helper ───────────────────────────────────────────────────────

    def _get_dc_boost(self, position: tuple, env: "Environment") -> float:
        from agents.dendritic_cell import DendriticCell

        nearby = env.get_agents_in_radius(position, self.dc_radius)
        for a in nearby:
            if isinstance(a, DendriticCell) and a.state.alive \
               and a.state.metadata.get("maturation_state") == "mature":
                return self.dc_boost
        return 0.0
