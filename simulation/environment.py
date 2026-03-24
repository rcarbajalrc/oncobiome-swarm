"""Contenedor del estado del mundo 2D."""
from __future__ import annotations

import logging
import math
from collections import deque
from typing import TYPE_CHECKING

import numpy as np

from config import get_config
from models.agent_state import AgentType, LocalContext, NearbyAgentInfo
from models.cytokine_state import CytokineType
from models.swarm_snapshot import AgentSummary, CytokineSummary, SwarmSnapshot
from simulation.diffusion import CytokineFieldManager

if TYPE_CHECKING:
    from agents.base_agent import BaseAgent
    from memory.base_store import MemoryStore

logger = logging.getLogger(__name__)

_MAX_EVENTS = 500
_NEARBY_MAX = 5
_MEMORY_MAX = 2          # reducido de 5 a 2 — controla tokens input con mem0 activo
_SNAPSHOT_AGENTS_MAX = 12


class Environment:
    def __init__(self, grid_size: int | None = None) -> None:
        cfg = get_config()
        self.grid_size: int = grid_size or cfg.grid_size
        self.interaction_radius: float = cfg.interaction_radius
        self.agents: dict[str, "BaseAgent"] = {}
        self._occupancy: set[tuple[int, int]] = set()
        self.cytokines = CytokineFieldManager(
            self.grid_size,
            decay=cfg.cytokine_decay,
            sigma=cfg.cytokine_diffusion_sigma,
        )
        self.cycle: int = 0
        self.events: deque[str] = deque(maxlen=_MAX_EVENTS)
        self.last_opus_analysis: str = "(sin análisis aún)"
        self.history: list[dict[str, int]] = []

    def add_agent(self, agent: "BaseAgent") -> bool:
        cell = self._to_cell(agent.state.position)
        if cell in self._occupancy:
            return False
        self.agents[agent.state.agent_id] = agent
        self._occupancy.add(cell)
        return True

    def remove_agent(self, agent_id: str) -> None:
        agent = self.agents.pop(agent_id, None)
        if agent:
            self._occupancy.discard(self._to_cell(agent.state.position))
            self.log_event(f"[{agent.state.agent_type.value}] {agent_id} ha muerto.")

    def move_agent(self, agent_id: str, new_pos: tuple[float, float]) -> bool:
        agent = self.agents.get(agent_id)
        if not agent:
            return False
        new_cell = self._to_cell(new_pos)
        old_cell = self._to_cell(agent.state.position)
        if new_cell == old_cell:
            return True
        if new_cell in self._occupancy:
            return False
        self._occupancy.discard(old_cell)
        self._occupancy.add(new_cell)
        agent.state.position = new_pos
        return True

    def find_free_adjacent(self, pos: tuple[float, float], step: float = 3.0) -> tuple[float, float] | None:
        x, y = pos
        directions = [
            (step, 0), (-step, 0), (0, step), (0, -step),
            (step, step), (-step, step), (step, -step), (-step, -step),
        ]
        np.random.shuffle(directions)
        for dx, dy in directions:
            candidate = (
                float(np.clip(x + dx, 0, self.grid_size - 1)),
                float(np.clip(y + dy, 0, self.grid_size - 1)),
            )
            if self._to_cell(candidate) not in self._occupancy:
                return candidate
        return None

    def find_free_random_position(self) -> tuple[float, float] | None:
        for _ in range(200):
            pos = (
                float(np.random.uniform(0, self.grid_size)),
                float(np.random.uniform(0, self.grid_size)),
            )
            if self._to_cell(pos) not in self._occupancy:
                return pos
        return None

    def get_agents_in_radius(self, pos: tuple[float, float], radius: float, exclude_id: str = "") -> list["BaseAgent"]:
        return [
            a for a in self.agents.values()
            if a.state.agent_id != exclude_id and _distance(pos, a.state.position) <= radius
        ]

    def get_local_context(self, agent_id: str, memory_store: "MemoryStore") -> LocalContext:
        agent = self.agents[agent_id]
        pos = agent.state.position

        nearby_raw = sorted(
            self.get_agents_in_radius(pos, get_config().llm_context_radius, exclude_id=agent_id),
            key=lambda a: _distance(pos, a.state.position),
        )
        nearby = [
            NearbyAgentInfo(
                agent_id=a.state.agent_id,
                agent_type=a.state.agent_type,
                distance=round(_distance(pos, a.state.position), 2),
                energy=round(a.state.energy, 3),
            )
            for a in nearby_raw[:_NEARBY_MAX]
        ]

        cytokine_levels = {
            ct.value: round(self.cytokines.sample(ct.value, pos), 4)
            for ct in CytokineType
        }

        recent_memories = memory_store.get_recent(agent.state.memory_user_id(), _MEMORY_MAX)

        return LocalContext(
            agent_id=agent_id,
            agent_type=agent.state.agent_type,
            position=pos,
            energy=round(agent.state.energy, 3),
            age=agent.state.age,
            metadata=agent.state.metadata,
            nearby_agents=nearby,
            cytokine_levels=cytokine_levels,
            recent_memories=recent_memories,
            cycle=self.cycle,
        )

    def emit_cytokine(self, pos: tuple[float, float], cytokine: str, amount: float) -> None:
        self.cytokines.emit(cytokine, pos, amount)

    def sample_cytokine(self, pos: tuple[float, float], cytokine: str) -> float:
        return self.cytokines.sample(cytokine, pos)

    def diffuse_cytokines(self) -> None:
        self.cytokines.step()

    def snapshot(self) -> SwarmSnapshot:
        counts: dict[str, int] = {}
        for agent in self.agents.values():
            k = agent.state.agent_type.value
            counts[k] = counts.get(k, 0) + 1

        cyt_summary = {
            key: CytokineSummary(**vals)
            for key, vals in self.cytokines.summary().items()
        }

        sorted_agents = sorted(self.agents.values(), key=lambda a: a.state.energy)
        top_agents = sorted_agents[:_SNAPSHOT_AGENTS_MAX]
        agent_summaries = [
            AgentSummary(
                agent_id=a.state.agent_id,
                agent_type=a.state.agent_type.value,
                energy=round(a.state.energy, 3),
                age=a.state.age,
                position=a.state.position,
                metadata_summary=_meta_summary(a.state.metadata),
            )
            for a in top_agents
        ]

        return SwarmSnapshot(
            cycle=self.cycle,
            population_counts=counts,
            cytokine_summary=cyt_summary,
            agent_summaries=agent_summaries,
            recent_events=list(self.events)[-20:],
            last_opus_analysis=self.last_opus_analysis,
        )

    def log_event(self, event: str) -> None:
        tagged = f"[C{self.cycle:04d}] {event}"
        self.events.append(tagged)
        logger.debug(tagged)

    def _to_cell(self, pos: tuple[float, float]) -> tuple[int, int]:
        return (int(pos[0]), int(pos[1]))

    @property
    def grid_size(self) -> int:
        return self._grid_size

    @grid_size.setter
    def grid_size(self, value: int) -> None:
        self._grid_size = value


def _distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2)


def _meta_summary(meta: dict) -> str:
    return " ".join(f"{k}={v}" for k, v in list(meta.items())[:3])
