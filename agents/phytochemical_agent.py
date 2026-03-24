"""PhytochemicalAgent — compuesto natural (curcumina por defecto).

NO usa LLM. Comportamiento completamente determinista:
- DIFFUSE mientras concentration > threshold
- DIE cuando concentration ≤ 0 o ttl = 0
"""
from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from models.agent_state import AgentAction, AgentDecision, AgentState, AgentType, LocalContext
from models.cytokine_state import CytokineType

if TYPE_CHECKING:
    from llm.client import LLMClient
    from memory.base_store import MemoryStore
    from simulation.environment import Environment

logger = logging.getLogger(__name__)

_DIFFUSE_THRESHOLD = 0.05


class PhytochemicalAgent:
    """Agente determinista — no hereda BaseAgent para evitar llamadas LLM innecesarias."""

    def __init__(
        self,
        position: tuple[float, float],
        memory_store: "MemoryStore",
        compound: str = "curcumina",
        concentration: float | None = None,
        ttl: int | None = None,
    ) -> None:
        from config import get_config

        cfg = get_config()
        self.state = AgentState(
            agent_type=AgentType.PHYTOCHEMICAL,
            position=position,
            energy=concentration if concentration is not None else cfg.phytochemical_initial_concentration,
            metadata={
                "compound": compound,
                "concentration": concentration if concentration is not None else cfg.phytochemical_initial_concentration,
                "ttl": ttl if ttl is not None else cfg.phytochemical_ttl,
            },
        )
        self.memory = memory_store

    async def reason_and_decide(
        self,
        context: LocalContext,
        llm_client: "LLMClient",
    ) -> AgentDecision:
        """Decisión determinista: DIFFUSE o DIE."""
        conc = self.state.metadata.get("concentration", 0.0)
        ttl = self.state.metadata.get("ttl", 0)

        if conc <= _DIFFUSE_THRESHOLD or ttl <= 0:
            return AgentDecision(
                action=AgentAction.DIE,
                reasoning="concentration depleted or TTL expired",
                confidence=1.0,
            )
        return AgentDecision(
            action=AgentAction.DIFFUSE,
            reasoning="diffusing active compound",
            confidence=1.0,
        )

    async def execute_decision(
        self,
        decision: AgentDecision,
        env: "Environment",
    ) -> list:
        if decision.action == AgentAction.DIE:
            self.state.alive = False
            return []

        # DIFFUSE: emite al campo de citoquinas y consume concentración
        from config import get_config

        cfg = get_config()
        # La curcumina no es una citoquina estándar, pero modela su difusión
        # emitiendo una señal negativa de IL-6 (efecto anti-inflamatorio)
        conc = self.state.metadata.get("concentration", 0.0)
        emit = min(conc * 0.1, cfg.cytokine_emit_amount)
        # Reduce IL-6 ambiental consumiendo parte del campo (efecto anti-inflamatorio)
        current_il6 = env.sample_cytokine(self.state.position, CytokineType.IL6.value)
        reduction = min(current_il6, emit * 2)
        env.cytokines.fields[CytokineType.IL6.value][
            env.cytokines._pos_to_rc(self.state.position)
        ] -= reduction

        # Consume concentración y TTL
        self.state.metadata["concentration"] = max(0.0, conc - 0.05)
        self.state.metadata["ttl"] = self.state.metadata.get("ttl", 0) - 1
        self.state.energy = self.state.metadata["concentration"]

        return []

    def tick(self) -> None:
        self.state.age += 1
