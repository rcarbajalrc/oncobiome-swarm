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


class MacrophageAgent(BaseAgent):
    """Macrófago polarizable M0/M1/M2.

    La polarización es determinista (InteractionResolver.macrophage_polarisation).
    El LLM decide MOVIMIENTO y SEÑALIZACIÓN según su estado de polarización.

    M1: pro-inflamatorio → migra hacia tumores, emite IFN-γ
    M2: anti-inflamatorio → huye de inmunes, emite IL-6 (favorece tumor)
    M0: neutro → exploración aleatoria
    """

    def __init__(
        self,
        position: tuple[float, float],
        memory_store: "MemoryStore",
        energy: float | None = None,
        polarization: str = "M0",
    ) -> None:
        from config import get_config

        cfg = get_config()
        state = AgentState(
            agent_type=AgentType.MACROPHAGE,
            position=position,
            energy=energy if energy is not None else cfg.macrophage_initial_energy,
            metadata={"polarization": polarization},
        )
        super().__init__(state, memory_store)

    def _default_action(self) -> AgentAction:
        pol = self.state.metadata.get("polarization", "M0")
        return AgentAction.MIGRATE if pol in ("M1", "M0") else AgentAction.SIGNAL

    def _default_signal(self) -> str | None:
        pol = self.state.metadata.get("polarization", "M0")
        if pol == "M1":
            return CytokineType.IFNG.value
        if pol == "M2":
            return CytokineType.IL6.value
        return None

    def _choose_migration_target(
        self,
        env: "Environment",
    ) -> tuple[float, float] | None:
        pol = self.state.metadata.get("polarization", "M0")
        pos = self.state.position
        grid_size = env.grid_size

        if pol == "M1":
            # Migra hacia tumores (igual que ImmuneCell)
            from agents.tumor_cell import TumorCell
            from simulation.environment import _distance

            tumors = [
                a for a in env.get_agents_in_radius(pos, grid_size * 0.4)
                if isinstance(a, TumorCell) and a.state.alive
            ]
            if tumors:
                nearest = min(tumors, key=lambda a: _distance(pos, a.state.position))
                target_pos = nearest.state.position
                dx = target_pos[0] - pos[0]
                dy = target_pos[1] - pos[1]
                dist = max(0.001, (dx**2 + dy**2) ** 0.5)
                step = min(6.0, dist)
                candidate = (
                    float(np.clip(pos[0] + dx / dist * step, 0, grid_size - 1)),
                    float(np.clip(pos[1] + dy / dist * step, 0, grid_size - 1)),
                )
                cell = env._to_cell(candidate)
                if cell not in env._occupancy:
                    return candidate

        elif pol == "M2":
            # Huye de inmunes hacia zonas de alta IL-6
            best_pos = None
            best_score = -1.0
            for _ in range(8):
                angle = np.random.uniform(0, 2 * np.pi)
                dist = np.random.uniform(4, 12)
                cx = float(np.clip(pos[0] + dist * np.cos(angle), 0, grid_size - 1))
                cy = float(np.clip(pos[1] + dist * np.sin(angle), 0, grid_size - 1))
                candidate = (cx, cy)
                il6 = env.sample_cytokine(candidate, CytokineType.IL6.value)
                ifng = env.sample_cytokine(candidate, CytokineType.IFNG.value)
                score = il6 - ifng
                if score > best_score and env._to_cell(candidate) not in env._occupancy:
                    best_score = score
                    best_pos = candidate
            if best_pos:
                return best_pos

        return env.find_free_adjacent(pos)

    async def _handle_signal(self, decision, env: "Environment") -> list[BaseAgent]:
        """M1 emite IFN-γ, M2 emite IL-6."""
        from config import get_config

        cfg = get_config()
        cytokine = decision.signal_type or self._default_signal()
        if not cytokine:
            return []
        if cytokine not in (ct.value for ct in CytokineType):
            cytokine = self._default_signal() or CytokineType.IFNG.value

        env.emit_cytokine(self.state.position, cytokine, cfg.cytokine_emit_amount)
        self.state.energy = max(0.0, self.state.energy - 0.03)
        return []
