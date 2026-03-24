"""NKCell — Natural Killer cell agent.

BIOLOGÍA KRAS G12D PDAC:
  - NK no requieren presentación antigénica previa (inmunidad innata)
  - Kill por reconocimiento de ausencia de MHC-I ("missing self")
  - KRAS G12D downregula MHC-I → tumor potencialmente vulnerable a NK
  - PERO: IL-6 en TME PDAC suprime la actividad NK (Nat Immunol 2021)
  - NK colaboran con DC emitiendo IFN-γ (puente innata-adaptativa)

CALIBRACIÓN:
  - nk_kill_rate = 0.10: kill 20-30% en condiciones ideales
    (Clin Cancer Res 2020), reducido por supresión IL-6 en KRAS G12D
  - nk_il6_suppression_threshold = 0.04: umbral más bajo que CD8+ (0.06)
    → NK más sensibles a la supresión por IL-6 en TME PDAC
  - nk_exhaustion_age = 20: más resistente al agotamiento que CD8+ (15)
    → NK tienen mayor persistencia en tejido que linfocitos T

FUENTES:
  - Kill rate: Clin Cancer Res 2020 (NK cytotoxicity in PDAC models)
  - IL-6 suppression: Nat Immunol 2021 (IL-6 impairs NK function)
  - MHC-I downregulation: Immunity 2023 (KRAS G12D and immune evasion)
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


class NKCell(BaseAgent):
    """Natural Killer cell — inmunidad innata contra tumor."""

    def __init__(
        self,
        position: tuple[float, float],
        memory_store: "MemoryStore",
        energy: float | None = None,
    ) -> None:
        from config import get_config

        cfg = get_config()
        state = AgentState(
            agent_type=AgentType.NK_CELL,
            position=position,
            energy=energy if energy is not None else cfg.nk_initial_energy,
            metadata={"kills_count": 0},
        )
        super().__init__(state, memory_store)

    def _default_action(self) -> AgentAction:
        return AgentAction.MIGRATE

    def _default_signal(self) -> str | None:
        return CytokineType.IFNG.value

    def _choose_migration_target(
        self,
        env: "Environment",
    ) -> tuple[float, float] | None:
        """NK migra hacia tumores por gradiente de IL-6 (señal de peligro).

        Estrategia: IL-6 alto indica actividad tumoral → migra hacia IL-6.
        Secundario: migra directamente al tumor si está en rango.
        """
        from agents.tumor_cell import TumorCell
        from simulation.environment import _distance

        pos = self.state.position
        grid_size = env.grid_size

        # Primero: tumor visible en radio amplio → ir directo
        tumors = [
            a for a in env.get_agents_in_radius(pos, grid_size * 0.5)
            if isinstance(a, TumorCell) and a.state.alive
        ]
        if tumors:
            nearest = min(tumors, key=lambda a: _distance(pos, a.state.position))
            target_pos = nearest.state.position
            dx = target_pos[0] - pos[0]
            dy = target_pos[1] - pos[1]
            dist = max(0.001, (dx**2 + dy**2) ** 0.5)
            step = min(10.0, dist)   # NK más rápidas que CD8+ (mayor migración)
            candidate = (
                float(np.clip(pos[0] + dx / dist * step, 0, grid_size - 1)),
                float(np.clip(pos[1] + dy / dist * step, 0, grid_size - 1)),
            )
            if env._to_cell(candidate) not in env._occupancy:
                return candidate

        # Sin tumor visible: seguir gradiente de IL-6
        best_pos = None
        best_il6 = -1.0
        for _ in range(10):
            angle = np.random.uniform(0, 2 * np.pi)
            dist = np.random.uniform(5, 18)
            cx = float(np.clip(pos[0] + dist * np.cos(angle), 0, grid_size - 1))
            cy = float(np.clip(pos[1] + dist * np.sin(angle), 0, grid_size - 1))
            candidate = (cx, cy)
            il6 = env.sample_cytokine(candidate, CytokineType.IL6.value)
            if il6 > best_il6 and env._to_cell(candidate) not in env._occupancy:
                best_il6 = il6
                best_pos = candidate

        return best_pos or env.find_free_adjacent(pos)

    async def _handle_signal(self, decision, env: "Environment") -> list[BaseAgent]:
        """NK emite IFN-γ para activar DC y macrófagos M1."""
        from config import get_config

        cfg = get_config()
        cytokine = decision.signal_type or CytokineType.IFNG.value
        if cytokine not in (ct.value for ct in CytokineType):
            cytokine = CytokineType.IFNG.value

        env.emit_cytokine(self.state.position, cytokine, cfg.cytokine_emit_amount)
        self.state.energy = max(0.0, self.state.energy - 0.05)
        env.log_event(
            f"NKCell {self.state.agent_id} señalizó {cytokine} "
            f"(e={self.state.energy:.2f})"
        )
        return []
