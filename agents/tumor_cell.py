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


class TumorCell(BaseAgent):
    """Célula tumoral con mutación KRAS_G12D.

    Drives: proliferación, evasión inmune, señalización angiogénica (VEGF).
    Amenazas: ImmuneCell, MacrophageAgent M1, PhytochemicalAgent, IFN-γ alto.
    """

    def __init__(
        self,
        position: tuple[float, float],
        memory_store: "MemoryStore",
        energy: float | None = None,
        mutation: str = "KRAS_G12D",
    ) -> None:
        from config import get_config

        cfg = get_config()
        state = AgentState(
            agent_type=AgentType.TUMOR_CELL,
            position=position,
            energy=energy if energy is not None else cfg.tumor_initial_energy,
            metadata={
                "mutation": mutation,
                "division_count": 0,
            },
        )
        super().__init__(state, memory_store)

    def _default_action(self) -> AgentAction:
        return AgentAction.QUIESCE

    def _default_signal(self) -> str | None:
        return CytokineType.IL6.value

    def _choose_migration_target(
        self,
        env: "Environment",
    ) -> tuple[float, float] | None:
        """El tumor huye de zonas con alto IFN-γ hacia zonas con alto VEGF."""
        pos = self.state.position
        grid_size = env.grid_size
        best_pos = None
        best_score = -1.0

        # Muestrea 8 posiciones candidatas en un radio de ~10
        for _ in range(8):
            angle = np.random.uniform(0, 2 * np.pi)
            dist = np.random.uniform(3, 10)
            cx = float(np.clip(pos[0] + dist * np.cos(angle), 0, grid_size - 1))
            cy = float(np.clip(pos[1] + dist * np.sin(angle), 0, grid_size - 1))
            candidate = (cx, cy)

            ifng = env.sample_cytokine(candidate, CytokineType.IFNG.value)
            vegf = env.sample_cytokine(candidate, CytokineType.VEGF.value)
            # Preferir VEGF alto, IFN-γ bajo
            score = vegf - 2.0 * ifng

            if score > best_score:
                from simulation.environment import _distance

                cell = env._to_cell(candidate)
                if cell not in env._occupancy:
                    best_score = score
                    best_pos = candidate

        return best_pos or env.find_free_adjacent(pos)

    async def _handle_proliferate(
        self,
        env: "Environment",
    ) -> list[BaseAgent]:
        """Crea una nueva TumorCell en posición adyacente si hay espacio."""
        new_pos = env.find_free_adjacent(self.state.position)
        if new_pos is None:
            env.log_event(
                f"TumorCell {self.state.agent_id} quiso proliferar pero no hay espacio. "
                "→ QUIESCE"
            )
            self.state.energy = min(1.0, self.state.energy + 0.02)
            return []

        self.state.metadata["division_count"] = (
            self.state.metadata.get("division_count", 0) + 1
        )
        self.state.energy = max(0.0, self.state.energy - 0.3)

        daughter = TumorCell(
            position=new_pos,
            memory_store=self.memory,
            energy=0.5,
            mutation=self.state.metadata.get("mutation", "KRAS_G12D"),
        )
        env.log_event(
            f"TumorCell {self.state.agent_id} proliferó → {daughter.state.agent_id}"
        )
        return [daughter]

    async def _handle_signal(self, decision, env: "Environment") -> list[BaseAgent]:
        """El tumor emite IL-6 (inmunosupresión) o VEGF (angiogénesis)."""
        from config import get_config

        cfg = get_config()
        # Señal por defecto: IL-6 para suprimir inmunidad
        cytokine = decision.signal_type or CytokineType.IL6.value
        if cytokine not in (ct.value for ct in CytokineType):
            cytokine = CytokineType.IL6.value

        env.emit_cytokine(self.state.position, cytokine, cfg.cytokine_emit_amount)
        self.state.energy = max(0.0, self.state.energy - 0.05)
        return []
