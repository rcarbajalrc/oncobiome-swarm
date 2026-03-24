"""CytokineAgent — fuente puntual de señal difusiva con TTL.

NO es un agente LLM. Es una fuente emisora temporal que:
- Emite su citoquina al CytokineFieldManager en cada ciclo
- Desaparece cuando TTL = 0

Creado por otros agentes mediante la acción SIGNAL.
La difusión real la maneja CytokineFieldManager.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from models.agent_state import AgentAction, AgentDecision, AgentState, AgentType, LocalContext
from models.cytokine_state import CytokineType

if TYPE_CHECKING:
    from llm.client import LLMClient
    from memory.base_store import MemoryStore
    from simulation.environment import Environment

logger = logging.getLogger(__name__)


class CytokineAgent:
    """Entidad de campo — no hereda BaseAgent."""

    def __init__(
        self,
        position: tuple[float, float],
        cytokine_type: str,
        memory_store: "MemoryStore",
        emit_amount: float | None = None,
        ttl: int | None = None,
    ) -> None:
        from config import get_config

        cfg = get_config()
        self.cytokine_type = cytokine_type
        self._emit_amount = emit_amount if emit_amount is not None else cfg.cytokine_emit_amount
        self.state = AgentState(
            agent_type=AgentType.CYTOKINE,
            position=position,
            energy=1.0,
            metadata={
                "cytokine_type": cytokine_type,
                "ttl": ttl if ttl is not None else cfg.cytokine_ttl,
                "emit_amount": self._emit_amount,
            },
        )
        self.memory = memory_store

    async def reason_and_decide(
        self,
        context: LocalContext,
        llm_client: "LLMClient",
    ) -> AgentDecision:
        ttl = self.state.metadata.get("ttl", 0)
        if ttl <= 0:
            return AgentDecision(action=AgentAction.DIE, reasoning="TTL expired", confidence=1.0)
        return AgentDecision(action=AgentAction.DIFFUSE, reasoning="emitting signal", confidence=1.0)

    async def execute_decision(
        self,
        decision: AgentDecision,
        env: "Environment",
    ) -> list:
        if decision.action == AgentAction.DIE:
            self.state.alive = False
            return []

        # Emite al campo
        env.emit_cytokine(self.state.position, self.cytokine_type, self._emit_amount)
        self.state.metadata["ttl"] -= 1
        return []

    def tick(self) -> None:
        self.state.age += 1
