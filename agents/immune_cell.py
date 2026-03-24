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


class ImmuneCell(BaseAgent):
    """Linfocito T CD8+ citotóxico.

    Drives: buscar y eliminar células tumorales, señalizar IFN-γ para
    coordinar macrófagos, conservar energía para mantener efectividad.
    """

    def __init__(
        self,
        position: tuple[float, float],
        memory_store: "MemoryStore",
        energy: float | None = None,
    ) -> None:
        from config import get_config

        cfg = get_config()
        state = AgentState(
            agent_type=AgentType.IMMUNE_CELL,
            position=position,
            energy=energy if energy is not None else cfg.immune_initial_energy,
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
        """Migra hacia la célula tumoral más cercana. Si no hay tumores,
        navega hacia zonas con alta concentración de IL-6 (señal de actividad tumoral).
        """
        from agents.tumor_cell import TumorCell
        from simulation.environment import _distance

        pos = self.state.position
        # Busca el tumor más cercano en radio amplio
        tumors = [
            a for a in env.get_agents_in_radius(pos, env.grid_size * 0.5)
            if isinstance(a, TumorCell) and a.state.alive
        ]
        if tumors:
            nearest = min(tumors, key=lambda a: _distance(pos, a.state.position))
            target_pos = nearest.state.position
            # Mueve un paso hacia el tumor
            dx = target_pos[0] - pos[0]
            dy = target_pos[1] - pos[1]
            dist = max(0.001, (dx**2 + dy**2) ** 0.5)
            step = min(8.0, dist)
            candidate = (
                float(np.clip(pos[0] + dx / dist * step, 0, env.grid_size - 1)),
                float(np.clip(pos[1] + dy / dist * step, 0, env.grid_size - 1)),
            )
            cell = env._to_cell(candidate)
            if cell not in env._occupancy:
                return candidate

        # Sin tumores visibles: navega hacia IL-6 alto
        grid_size = env.grid_size
        best_pos = None
        best_il6 = -1.0
        for _ in range(8):
            angle = np.random.uniform(0, 2 * np.pi)
            dist = np.random.uniform(5, 15)
            cx = float(np.clip(pos[0] + dist * np.cos(angle), 0, grid_size - 1))
            cy = float(np.clip(pos[1] + dist * np.sin(angle), 0, grid_size - 1))
            candidate = (cx, cy)
            il6 = env.sample_cytokine(candidate, CytokineType.IL6.value)
            if il6 > best_il6 and env._to_cell(candidate) not in env._occupancy:
                best_il6 = il6
                best_pos = candidate

        return best_pos or env.find_free_adjacent(pos)

    async def _handle_signal(self, decision, env: "Environment") -> list[BaseAgent]:
        """El CD8+ emite IFN-γ para activar M1 y suprimir tumor."""
        from config import get_config

        cfg = get_config()
        cytokine = decision.signal_type or CytokineType.IFNG.value
        if cytokine not in (ct.value for ct in CytokineType):
            cytokine = CytokineType.IFNG.value

        env.emit_cytokine(self.state.position, cytokine, cfg.cytokine_emit_amount)
        self.state.energy = max(0.0, self.state.energy - 0.05)
        env.log_event(
            f"ImmuneCell {self.state.agent_id} señalizó {cytokine}"
        )
        return []
