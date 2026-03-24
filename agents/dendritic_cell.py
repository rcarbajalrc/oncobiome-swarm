"""DendriticCell — Célula dendrítica presentadora de antígeno.

BIOLOGÍA KRAS G12D PDAC:
  - DC son el puente entre inmunidad innata y adaptativa
  - Maduran al detectar señales de peligro (IFN-γ, DAMPs)
  - DC maduras presentan antígeno y activan CD8+ T cells
  - En KRAS G12D PDAC: DC frecuentemente inmaduras o tolerogénicas
    → KRAS G12D suprime la maduración DC (Immunity 2023)
    → DC inmaduras inducen tolerancia en lugar de activación
  - DC maduras son las que activan CD8+ y aumentan su eficacia

ESTADOS:
  - "immature": DC no activada, rol limitado (señaliza solo IFN-γ mínimo)
  - "maturing": en proceso de maduración (acumula ciclos con IFN-γ > umbral)
  - "mature":   DC activa — aumenta kill_rate de CD8+ cercanos vía
                interaction resolver (_dc_activates_cd8)

CALIBRACIÓN:
  - dc_maturation_ifng_threshold = 0.05: IFN-γ > 0.05 activa maduración
  - dc_maturation_cycles = 3: ciclos consecutivos con IFN-γ para madurar
  - dc_activation_boost = 0.20: +20% kill_rate CD8+ en radio de activación
  - dc_activation_radius = 12.0 (igual que llm_context_radius)

FUENTES:
  - Maduración suprimida por KRAS G12D: Immunity 2023
  - DC activan CD8+: revisado en Nat Rev Immunol 2020
  - Rol tolerogénico en PDAC: Gastroenterology 2022 (Somani et al.)
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import numpy as np

from agents.base_agent import BaseAgent
from models.agent_state import AgentAction, AgentState, AgentType
from models.cytokine_state import CytokineType

if TYPE_CHECKING:
    from memory.base_store import MemoryStore
    from simulation.environment import Environment

logger = logging.getLogger(__name__)


class DendriticCell(BaseAgent):
    """Célula dendrítica — presentadora de antígeno, puente innata-adaptativa."""

    def __init__(
        self,
        position: tuple[float, float],
        memory_store: "MemoryStore",
        energy: float | None = None,
        maturation_state: str = "immature",
    ) -> None:
        from config import get_config

        cfg = get_config()
        state = AgentState(
            agent_type=AgentType.DENDRITIC_CELL,
            position=position,
            energy=energy if energy is not None else cfg.dc_initial_energy,
            metadata={
                "maturation_state":   maturation_state,  # "immature" | "maturing" | "mature"
                "ifng_cycles_above":  0,                 # ciclos consecutivos con IFN-γ > umbral
            },
        )
        super().__init__(state, memory_store)

    def _default_action(self) -> AgentAction:
        """DC madura migra; inmadura quiesce para conservar energía."""
        state = self.state.metadata.get("maturation_state", "immature")
        return AgentAction.MIGRATE if state == "mature" else AgentAction.QUIESCE

    def _default_signal(self) -> str | None:
        return CytokineType.IFNG.value

    def _choose_migration_target(
        self,
        env: "Environment",
    ) -> tuple[float, float] | None:
        """DC madura migra hacia zonas de alta actividad (IL-6 + IFN-γ).

        Las DC maduras patrullan el TME buscando zonas donde haya
        tanto tumor (IL-6 alto) como actividad inmune (IFN-γ alto)
        para maximizar su efecto activador sobre CD8+.
        """
        pos = self.state.position
        grid_size = env.grid_size
        best_pos = None
        best_score = -1.0

        for _ in range(8):
            angle = np.random.uniform(0, 2 * np.pi)
            dist = np.random.uniform(4, 14)
            cx = float(np.clip(pos[0] + dist * np.cos(angle), 0, grid_size - 1))
            cy = float(np.clip(pos[1] + dist * np.sin(angle), 0, grid_size - 1))
            candidate = (cx, cy)

            il6  = env.sample_cytokine(candidate, CytokineType.IL6.value)
            ifng = env.sample_cytokine(candidate, CytokineType.IFNG.value)
            # Score: zonas con actividad mixta (tumor + inmune) son las mejores
            score = il6 + ifng
            if score > best_score and env._to_cell(candidate) not in env._occupancy:
                best_score = score
                best_pos = candidate

        return best_pos or env.find_free_adjacent(pos)

    async def _handle_signal(self, decision, env: "Environment") -> list[BaseAgent]:
        """DC señaliza IFN-γ cuando está madura o maturing."""
        from config import get_config

        cfg = get_config()
        maturation = self.state.metadata.get("maturation_state", "immature")

        # Solo señaliza activamente si está madurando o madura
        if maturation == "immature":
            return []

        cytokine = decision.signal_type or CytokineType.IFNG.value
        if cytokine not in (ct.value for ct in CytokineType):
            cytokine = CytokineType.IFNG.value

        # DC madura emite más IFN-γ que una DC inmadura
        emit_amount = cfg.cytokine_emit_amount * (1.5 if maturation == "mature" else 1.0)
        env.emit_cytokine(self.state.position, cytokine, emit_amount)
        self.state.energy = max(0.0, self.state.energy - 0.04)
        env.log_event(
            f"DendriticCell {self.state.agent_id} ({maturation}) "
            f"señalizó {cytokine}"
        )
        return []
