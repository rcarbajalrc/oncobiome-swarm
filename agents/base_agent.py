"""BaseAgent — clase abstracta para todos los agentes con LLM.

Responsabilidades:
- Mantiene AgentState
- reason_and_decide(): llama Haiku con contexto local + memoria
- execute_decision(): aplica la acción al mundo (retorna nuevos agentes si prolifera)
- Parsing JSON robusto con 3 niveles de fallback
- Wrapping async de operaciones mem0 síncronas

Optimizaciones mem0:
- Solo guarda memoria en decisiones significativas (no QUIESCE rutinario)
- Recupera máximo 2 memorias recientes (no 5) para controlar tokens input
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from llm.client import LLMClient, LLMError
from llm.prompts import build_system_prompt, build_user_prompt
from models.agent_state import AgentAction, AgentDecision, AgentState, LocalContext

if TYPE_CHECKING:
    from memory.base_store import MemoryStore
    from simulation.environment import Environment

logger = logging.getLogger(__name__)

# Acciones que vale la pena recordar — excluye QUIESCE rutinario
_MEMORABLE_ACTIONS = {AgentAction.SIGNAL, AgentAction.MIGRATE, AgentAction.PROLIFERATE, AgentAction.DIE}


class BaseAgent(ABC):
    def __init__(self, state: AgentState, memory_store: "MemoryStore") -> None:
        self.state = state
        self.memory = memory_store

    async def reason_and_decide(self, context: LocalContext, llm_client: LLMClient) -> AgentDecision:
        if not self.state.alive:
            return AgentDecision(action=AgentAction.DIE, reasoning="already dead")

        if self._should_skip_llm(context):
            return AgentDecision(action=self._default_action(), confidence=0.8, reasoning="routine")

        system_prompt = build_system_prompt(self.state.agent_type)
        user_prompt = build_user_prompt(context)

        try:
            raw = await llm_client.call_haiku(system=system_prompt, user=user_prompt)
            decision = self._parse_response(raw)

            # Solo guarda en mem0 si la acción es significativa
            if decision.action in _MEMORABLE_ACTIONS:
                memory_entry = (
                    f"C{context.cycle}:{decision.action.value}({decision.reasoning[:20]})"
                )
                await asyncio.to_thread(
                    self.memory.add,
                    memory_entry,
                    self.state.memory_user_id(),
                )
        except LLMError as exc:
            logger.warning(
                "LLM falló para %s %s: %s. Usando acción por defecto.",
                self.state.agent_type.value, self.state.agent_id, exc,
            )
            decision = AgentDecision(action=self._default_action(), confidence=0.0)

        return decision

    async def execute_decision(self, decision: AgentDecision, env: "Environment") -> list["BaseAgent"]:
        action = decision.action

        if action == AgentAction.DIE:
            self.state.alive = False
            return []
        if action == AgentAction.QUIESCE:
            self.state.energy = min(1.0, self.state.energy + 0.02)
            return []
        if action == AgentAction.MIGRATE:
            return await self._handle_migrate(decision, env)
        if action == AgentAction.SIGNAL:
            return await self._handle_signal(decision, env)
        if action == AgentAction.PROLIFERATE:
            return await self._handle_proliferate(env)
        if action == AgentAction.DIFFUSE:
            return await self._handle_diffuse(env)
        return []

    async def _handle_migrate(self, decision: AgentDecision, env: "Environment") -> list["BaseAgent"]:
        target = decision.target_position or self._choose_migration_target(env)
        if target and env.move_agent(self.state.agent_id, target):
            self.state.energy = max(0.0, self.state.energy - 0.02)
        return []

    async def _handle_signal(self, decision: AgentDecision, env: "Environment") -> list["BaseAgent"]:
        from config import get_config
        cytokine = decision.signal_type or self._default_signal()
        if cytokine:
            env.emit_cytokine(self.state.position, cytokine, get_config().cytokine_emit_amount)
            self.state.energy = max(0.0, self.state.energy - 0.05)
        return []

    async def _handle_proliferate(self, env: "Environment") -> list["BaseAgent"]:
        return []

    async def _handle_diffuse(self, env: "Environment") -> list["BaseAgent"]:
        self.state.energy = min(1.0, self.state.energy + 0.01)
        return []

    def _should_skip_llm(self, context: LocalContext) -> bool:
        from config import get_config
        cfg = get_config()
        if not cfg.llm_skip_enabled:
            return False
        if context.cycle < cfg.llm_bootstrap_cycles:
            return False
        has_neighbors = len(context.nearby_agents) > 0
        energy_critical = context.energy < cfg.llm_skip_energy_min or context.energy > cfg.llm_skip_energy_max
        has_cytokines = any(v > 0.01 for v in context.cytokine_levels.values())
        return not has_neighbors and not energy_critical and not has_cytokines

    @abstractmethod
    def _default_action(self) -> AgentAction:
        pass

    @abstractmethod
    def _default_signal(self) -> str | None:
        pass

    def _choose_migration_target(self, env: "Environment") -> tuple[float, float] | None:
        return env.find_free_adjacent(self.state.position)

    def _parse_response(self, raw: str) -> AgentDecision:
        text = raw.strip()
        try:
            return self._build_decision(json.loads(text))
        except (json.JSONDecodeError, ValueError):
            pass
        m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if m:
            try:
                return self._build_decision(json.loads(m.group(1)))
            except (json.JSONDecodeError, ValueError):
                pass
        m = re.search(r"\{[^{}]+\}", text, re.DOTALL)
        if m:
            try:
                return self._build_decision(json.loads(m.group(0)))
            except (json.JSONDecodeError, ValueError):
                pass
        logger.warning("No se pudo parsear JSON de: %s", text[:80])
        return AgentDecision(action=self._default_action(), confidence=0.0)

    def _build_decision(self, data: dict) -> AgentDecision:
        action_str = data.get("action", "").upper()
        try:
            action = AgentAction(action_str)
        except ValueError:
            action = self._default_action()
        return AgentDecision(
            action=action,
            reasoning=data.get("reasoning", ""),
            confidence=float(data.get("confidence", 0.8)),
            signal_type=data.get("signal_type"),
            target_position=data.get("target_position"),
        )
