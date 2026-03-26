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

# Sprint 7B: umbral de densidad tumoral para apoptosis hipóxica
# Si hay más de N tumores en radio R, la célula central entra en hipoxia
HYPOXIA_DENSITY_THRESHOLD = 6   # vecinas tumorales
HYPOXIA_RADIUS = 8.0            # radio de búsqueda
HYPOXIA_DEATH_PROB = 0.15       # probabilidad de apoptosis por hipoxia


class TumorCell(BaseAgent):
    """Célula tumoral con mutación KRAS_G12D.

    Drives: proliferación, evasión inmune, señalización angiogénica (VEGF).
    Amenazas: ImmuneCell, MacrophageAgent M1, PhytochemicalAgent, IFN-γ alto.

    Sprint 7B: apoptosis hipóxica — muerte por densidad local alta
    (simula competencia por O₂/nutrientes sin PDE explícita).
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
                "hypoxic": False,      # Sprint 7B: flag hipoxia
            },
        )
        super().__init__(state, memory_store)

    def _default_action(self) -> AgentAction:
        return AgentAction.QUIESCE

    def _default_signal(self) -> str | None:
        return CytokineType.IL6.value

    def tick(self) -> None:
        """Sprint 7B: evalúa hipoxia en cada ciclo.

        Una célula tumoral rodeada de HYPOXIA_DENSITY_THRESHOLD o más
        vecinas tumorales en radio HYPOXIA_RADIUS entra en estado hipóxico
        y puede morir por apoptosis. Esto reemplaza el cap artifact:
        el plateau tumoral emerge de limitaciones de oxígeno, no de un techo arbitrario.
        """
        super().tick() if hasattr(super(), 'tick') else None
        self.state.metadata["hypoxic"] = False  # reset cada ciclo

    def check_hypoxia(self, env: "Environment") -> bool:
        """Evalúa si esta célula está en zona hipóxica (demasiadas vecinas tumorales).

        Returns True si muere por hipoxia este ciclo.
        """
        nearby = env.get_agents_in_radius(self.state.position, HYPOXIA_RADIUS)
        tumor_neighbors = sum(
            1 for a in nearby
            if isinstance(a, TumorCell) and a.state.alive and a.state.agent_id != self.state.agent_id
        )
        if tumor_neighbors >= HYPOXIA_DENSITY_THRESHOLD:
            self.state.metadata["hypoxic"] = True
            # Energía reducida en zona hipóxica
            self.state.energy = max(0.0, self.state.energy - 0.05)
            if np.random.random() < HYPOXIA_DEATH_PROB:
                env.log_event(
                    f"[Hipoxia] TumorCell {self.state.agent_id} apoptosis "
                    f"(vecinas={tumor_neighbors}, radio={HYPOXIA_RADIUS})"
                )
                return True
        return False

    def _choose_migration_target(
        self,
        env: "Environment",
    ) -> tuple[float, float] | None:
        """El tumor huye de zonas con alto IFN-γ y alta densidad (hipoxia)
        hacia zonas con alto VEGF y menos competencia.

        Sprint 7B: añade penalización por densidad tumoral local.
        """
        pos = self.state.position
        grid_size = env.grid_size
        best_pos = None
        best_score = -1.0

        for _ in range(8):
            angle = np.random.uniform(0, 2 * np.pi)
            dist = np.random.uniform(3, 10)
            cx = float(np.clip(pos[0] + dist * np.cos(angle), 0, grid_size - 1))
            cy = float(np.clip(pos[1] + dist * np.sin(angle), 0, grid_size - 1))
            candidate = (cx, cy)

            ifng = env.sample_cytokine(candidate, CytokineType.IFNG.value)
            vegf = env.sample_cytokine(candidate, CytokineType.VEGF.value)

            # Sprint 7B: penalizar zonas densas (simula búsqueda de oxígeno)
            nearby_tumors = sum(
                1 for a in env.get_agents_in_radius(candidate, HYPOXIA_RADIUS / 2)
                if isinstance(a, TumorCell) and a.state.alive
            )
            density_penalty = nearby_tumors * 0.05

            score = vegf - 2.0 * ifng - density_penalty

            if score > best_score:
                cell = env._to_cell(candidate)
                if cell not in env._occupancy:
                    best_score = score
                    best_pos = candidate

        return best_pos or env.find_free_adjacent(pos)

    async def _handle_proliferate(
        self,
        env: "Environment",
    ) -> list[BaseAgent]:
        """Crea una nueva TumorCell en posición adyacente si hay espacio.

        Sprint 7B: suprime proliferación en zonas hipóxicas.
        """
        # Sprint 7B: no proliferar si está en zona hipóxica
        if self.state.metadata.get("hypoxic", False):
            env.log_event(
                f"TumorCell {self.state.agent_id} suprimió proliferación por hipoxia"
            )
            self.state.energy = min(1.0, self.state.energy + 0.01)
            return []

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
        """El tumor emite IL-6 (inmunosupresión) o VEGF (angiogénesis).

        Sprint 7B: en hipoxia emite más VEGF (respuesta angiogénica real).
        """
        from config import get_config

        cfg = get_config()
        cytokine = decision.signal_type or CytokineType.IL6.value
        if cytokine not in (ct.value for ct in CytokineType):
            cytokine = CytokineType.IL6.value

        # Sprint 7B: hipoxia → VEGF adicional (HIF-1α pathway)
        if self.state.metadata.get("hypoxic", False):
            env.emit_cytokine(
                self.state.position,
                CytokineType.VEGF.value,
                cfg.cytokine_emit_amount * 1.5  # HIF-1α upregula VEGF
            )

        env.emit_cytokine(self.state.position, cytokine, cfg.cytokine_emit_amount)
        self.state.energy = max(0.0, self.state.energy - 0.05)
        return []
