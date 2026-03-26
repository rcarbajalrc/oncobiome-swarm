"""SimulationEngine — orquestador del ciclo de simulación.

Orden de operaciones por ciclo:
1. Recopilar LocalContext de cada agente (sync)
2. SMART BATCH o RULE ENGINE según modo
3. tick()
4. InteractionResolver.resolve()
5. Aplicar decisiones: DIE → SIGNAL → MIGRATE → PROLIFERATE
6. Limpiar muertos, añadir nuevos
7. CytokineFieldManager.step()
8. Cada OPUS_INTERVAL ciclos: análisis Opus → guardado en live_state + opus_history.json
9. Registrar historia, loguear decisiones CSV, avanzar ciclo

FIXES aplicados:
  - Opus se guarda en logs/opus_history.json (persistente entre lecturas)
  - live_state["last_opus_analysis"] se escribe DESPUÉS del análisis, no antes
  - token_usage incluye llm_decisions y rule_engine_decisions por ciclo
  - Contador de decisiones LLM vs rule engine por ciclo en token log
"""
from __future__ import annotations

import asyncio
import fcntl
import json
import logging
import os
from collections import defaultdict
from pathlib import Path
from typing import Union

from config import get_config
from llm.client import LLMClient
from llm.opus_analyzer import OpusAnalyzer
from llm.prompts import build_system_prompt, build_user_prompt
from llm.prompts_abstract import build_abstract_system_prompt, build_abstract_user_prompt
from llm.rule_engine import rule_engine_decide
from models.agent_state import AgentAction, AgentDecision, AgentType
from simulation.decision_logger import get_decision_logger, reset_logger
from simulation.environment import Environment
from simulation.interactions import InteractionResolver
from simulation.report_collector import ReportCollector

from agents.base_agent import BaseAgent
from agents.phytochemical_agent import PhytochemicalAgent
from agents.cytokine_agent import CytokineAgent

AnyAgent = Union[BaseAgent, PhytochemicalAgent, CytokineAgent]

logger = logging.getLogger(__name__)

_PROJECT_DIR = Path(__file__).parent.parent
_TOKEN_LOG = _PROJECT_DIR / "logs" / "token_usage.json"
_OPUS_LOG = _PROJECT_DIR / "logs" / "opus_history.json"
_STATE_DIR = _PROJECT_DIR / "state"


class SimulationEngine:
    def __init__(self, env: Environment, no_llm: bool = False, report_at: int = 10) -> None:
        self.env = env
        self.llm = LLMClient()
        self.analyzer = OpusAnalyzer(self.llm)
        self.interactions = InteractionResolver()
        self._cfg = get_config()
        self._no_llm = no_llm
        self.collector = ReportCollector(report_at_cycle=report_at)
        reset_logger()
        self._decision_logger = get_decision_logger()
        # Contadores de decisiones LLM vs rule engine por ciclo
        self._cycle_llm_decisions = 0
        self._cycle_rule_decisions = 0

    async def run(self, cycles: int | None = None, seed: int | None = None) -> None:
        """Ejecuta la simulación.

        Args:
            cycles: Número de ciclos. Si None, usa config.total_cycles.
            seed: Semilla aleatoria para reproducibilidad exacta.
                  Si None, usa SIMULATION_SEED del entorno o None (no determinista).
                  Pasar seed=42 garantiza runs idénticos con los mismos parámetros.
        """
        import numpy as np
        import random

        # Sprint 7B: seed fijo para reproducibilidad
        _seed = seed if seed is not None else int(os.environ.get("SIMULATION_SEED", "0")) or None
        if _seed is not None:
            np.random.seed(_seed)
            random.seed(_seed)
            logger.info("Seed aleatorio fijado: %d (reproducibilidad garantizada)", _seed)
        else:
            logger.info("Seed aleatorio: no fijado (stochastic mode)")

        total = cycles or self._cfg.total_cycles
        _model_short = self.llm._agent_model.split("-")[2] if hasattr(self.llm, "_agent_model") else "haiku"
        mode = "rule-engine ($0)" if self._no_llm else f"smart-batch ({_model_short})"
        logger.info("Iniciando simulación: %d ciclos, %d agentes, modo=%s", total, len(self.env.agents), mode)
        self.collector.record_initial_params(self.env)

        for _ in range(total):
            await self._run_cycle()
            if not self.env.agents:
                logger.info("Todos los agentes han muerto. Simulación terminada en ciclo %d.", self.env.cycle)
                break

        logger.info("Simulación completada. Ciclos: %d", self.env.cycle)
        self._decision_logger.close()
        _mark_simulation_stopped(self.env)

    def _enforce_population_cap(self, env: Environment) -> None:
        cap = self._cfg.max_agents
        total = len(env.agents)
        if total <= cap:
            return
        excess = total - cap
        candidates = sorted(env.agents.values(), key=lambda a: a.state.energy)
        killed = 0
        for agent in candidates:
            if killed >= excess:
                break
            agent.state.alive = False
            env.log_event(
                f"[Apoptosis] {agent.state.agent_type.value} {agent.state.agent_id} "
                f"e={agent.state.energy:.2f} (cap={cap}, total={total})"
            )
            killed += 1
        dead_ids = [aid for aid, a in env.agents.items() if not a.state.alive]
        for aid in dead_ids:
            env.remove_agent(aid)
        logger.info("Apoptosis: %d agentes eliminados (cap=%d)", killed, cap)

    async def _run_cycle(self) -> None:
        env = self.env
        agents = list(env.agents.values())
        self._cycle_llm_decisions = 0
        self._cycle_rule_decisions = 0

        # 1. Contextos
        contexts = {}
        for agent in agents:
            if isinstance(agent, BaseAgent) and agent.state.alive:
                ctx = env.get_local_context(agent.state.agent_id, agent.memory)
                contexts[agent.state.agent_id] = ctx

        # 2. Decisiones
        decisions: dict[str, AgentDecision] = {}
        if contexts:
            if self._no_llm:
                decisions = _rule_engine_decisions(contexts, env)
                self._cycle_rule_decisions = len(decisions)
            else:
                decisions = await self._batch_decisions(contexts, env)
                # contadores ya se actualizan en _batch_decisions

        for agent in agents:
            if not isinstance(agent, BaseAgent) and agent.state.alive:
                if hasattr(agent, "_default_action"):
                    decisions[agent.state.agent_id] = AgentDecision(
                        action=agent._default_action(), confidence=1.0
                    )

        # LOG decisiones
        for agent_id, decision in decisions.items():
            if agent_id in contexts:
                agent = env.agents.get(agent_id)
                if agent:
                    self._decision_logger.log(
                        cycle=env.cycle,
                        agent_id=agent_id,
                        agent_type=agent.state.agent_type.value,
                        decision=decision,
                        ctx=contexts[agent_id],
                    )
        self._decision_logger.flush()

        # 3. Tick
        for agent in agents:
            if hasattr(agent, "tick"):
                agent.tick()

        # 4. Interacciones
        self.interactions.resolve(env)

        # 5. Aplicar decisiones en orden causal
        new_agents: list = []
        for agent_id, decision in decisions.items():
            agent = env.agents.get(agent_id)
            if agent and decision.action == AgentAction.DIE:
                agent.state.alive = False

        for agent_id, decision in decisions.items():
            agent = env.agents.get(agent_id)
            if agent and agent.state.alive and decision.action == AgentAction.SIGNAL:
                born = await agent.execute_decision(decision, env)
                new_agents.extend(born)

        for agent_id, decision in decisions.items():
            agent = env.agents.get(agent_id)
            if agent and agent.state.alive and decision.action in (
                AgentAction.MIGRATE, AgentAction.QUIESCE, AgentAction.DIFFUSE,
            ):
                born = await agent.execute_decision(decision, env)
                new_agents.extend(born)

        for agent_id, decision in decisions.items():
            agent = env.agents.get(agent_id)
            if agent and agent.state.alive and decision.action == AgentAction.PROLIFERATE:
                born = await agent.execute_decision(decision, env)
                new_agents.extend(born)

        # 6. Limpiar muertos y añadir nuevos
        dead_ids = [aid for aid, a in env.agents.items() if not a.state.alive]
        for aid in dead_ids:
            env.remove_agent(aid)
        for new_agent in new_agents:
            if not env.add_agent(new_agent):
                logger.debug("No se pudo añadir agente nuevo: posición ocupada")

        self._enforce_population_cap(env)

        # 7. Difusión
        env.diffuse_cytokines()

        # 8. Opus — FIX: guardar en env Y en archivo ANTES de _write_live_state
        if not self._no_llm and env.cycle > 0 and env.cycle % self._cfg.opus_analysis_interval == 0:
            snapshot = env.snapshot()
            analysis = await self.analyzer.analyze(snapshot)
            env.last_opus_analysis = analysis
            self.collector.set_opus_prediction(analysis)
            _save_opus_analysis(analysis, env.cycle)
            logger.info("Opus ciclo %d guardado (%d chars)", env.cycle, len(analysis))

        # 9. Avanzar ciclo y registrar
        env.cycle += 1
        env.history.append(_population_counts(env))
        self.collector.record_cycle(env, decisions)

        if env.cycle == self.collector.report_at_cycle:
            self.collector.generate_report(env)

        _write_token_log(self.llm, env.cycle,
                         self._cycle_llm_decisions, self._cycle_rule_decisions)
        _write_live_state(env)

    async def _batch_decisions(
        self,
        contexts: dict,
        env: Environment,
    ) -> dict[str, AgentDecision]:
        """SMART BATCH: 1 llamada Haiku por tipo de agente.
        Fallback ante BatchError: rule engine ($0), nunca llamadas individuales.
        """
        from llm.client import BatchError
        decisions: dict[str, AgentDecision] = {}

        groups: dict[AgentType, list[str]] = defaultdict(list)
        for agent_id, ctx in contexts.items():
            agent = env.agents.get(agent_id)
            if agent and isinstance(agent, BaseAgent):
                if agent._should_skip_llm(ctx):
                    decisions[agent_id] = AgentDecision(
                        action=agent._default_action(), confidence=0.8, reasoning="routine"
                    )
                    self._cycle_rule_decisions += 1
                else:
                    groups[agent.state.agent_type].append(agent_id)

        for agent_type, agent_ids in groups.items():
            if not agent_ids:
                continue

            _prompt_mode = os.environ.get("PROMPT_MODE", "full").lower()
            if _prompt_mode == "abstract":
                system_prompt = build_abstract_system_prompt(agent_type)
            elif _prompt_mode == "minimal":
                system_prompt = (
                    "Autonomous agent. Output ONLY one JSON line. "
                    "Format: {action:X, reasoning:Y, confidence:0.9}. "
                    "Actions available: PROLIFERATE MIGRATE SIGNAL QUIESCE DIE. "
                    "Choose the most rational action given the context."
                )
            else:
                system_prompt = build_system_prompt(agent_type)
            user_prompts = [build_user_prompt(contexts[aid]) for aid in agent_ids]

            logger.debug("Batch %s: %d agentes → 1 llamada LLM", agent_type.value, len(agent_ids))

            try:
                raw_responses = await self.llm.call_haiku_batch(
                    system=system_prompt,
                    user_prompts=user_prompts,
                    max_tokens_per_agent=50,
                )
                for agent_id, raw in zip(agent_ids, raw_responses):
                    agent = env.agents.get(agent_id)
                    if not agent or not isinstance(agent, BaseAgent):
                        continue
                    decision = agent._parse_response(raw)
                    if decision.action in {AgentAction.SIGNAL, AgentAction.MIGRATE,
                                           AgentAction.PROLIFERATE, AgentAction.DIE}:
                        ctx = contexts[agent_id]
                        memory_entry = f"C{ctx.cycle}:{decision.action.value}({decision.reasoning[:20]})"
                        await asyncio.to_thread(
                            agent.memory.add, memory_entry, agent.state.memory_user_id()
                        )
                    decisions[agent_id] = decision
                    self._cycle_llm_decisions += 1

            except Exception as exc:
                logger.warning(
                    "Batch %s falló (%s) → rule engine fallback para %d agentes ($0)",
                    agent_type.value, type(exc).__name__, len(agent_ids)
                )
                for agent_id in agent_ids:
                    ctx = contexts[agent_id]
                    agent = env.agents.get(agent_id)
                    if agent and isinstance(agent, BaseAgent):
                        decisions[agent_id] = rule_engine_decide(agent.state.agent_type, ctx)
                        self._cycle_rule_decisions += 1

        return decisions


# ── Helpers ───────────────────────────────────────────────────────────────────

def _rule_engine_decisions(contexts: dict, env: Environment) -> dict[str, AgentDecision]:
    decisions: dict[str, AgentDecision] = {}
    for agent_id, ctx in contexts.items():
        agent = env.agents.get(agent_id)
        if agent and isinstance(agent, BaseAgent):
            decisions[agent_id] = rule_engine_decide(agent.state.agent_type, ctx)
    return decisions


def _population_counts(env: Environment) -> dict[str, int]:
    counts: dict[str, int] = {}
    for agent in env.agents.values():
        k = agent.state.agent_type.value
        counts[k] = counts.get(k, 0) + 1
    return counts


def _save_opus_analysis(analysis: str, cycle: int) -> None:
    """Guarda el análisis Opus en logs/opus_history.json — persistente entre sesiones MCP."""
    _OPUS_LOG.parent.mkdir(parents=True, exist_ok=True)
    try:
        if _OPUS_LOG.exists():
            try:
                history = json.loads(_OPUS_LOG.read_text())
            except (json.JSONDecodeError, OSError):
                history = []
        else:
            history = []

        # Evitar duplicados del mismo ciclo
        history = [e for e in history if e.get("cycle") != cycle]
        history.append({
            "cycle": cycle,
            "pid": os.getpid(),
            "analysis": analysis,
        })
        # Mantener solo los últimos 20 análisis
        history = history[-20:]
        _OPUS_LOG.write_text(json.dumps(history, indent=2, ensure_ascii=False))
    except Exception as exc:
        logger.warning("No se pudo guardar Opus en archivo: %s", exc)


def _write_token_log(llm: LLMClient, cycle: int,
                     llm_decisions: int = 0, rule_decisions: int = 0) -> None:
    stats = llm.get_and_reset_cycle_stats()
    stats["cycle"] = cycle
    stats["pid"] = os.getpid()
    stats["llm_decisions"] = llm_decisions
    stats["rule_engine_decisions"] = rule_decisions
    total = llm_decisions + rule_decisions
    stats["llm_pct"] = round(llm_decisions / total * 100, 1) if total > 0 else 0.0

    _TOKEN_LOG.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(_TOKEN_LOG, "r+") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                data = []
            pid = os.getpid()
            data = [e for e in data if e.get("pid") != pid or e.get("cycle") != cycle]
            data.append(stats)
            f.seek(0)
            f.truncate()
            json.dump(data, f, indent=2)
            fcntl.flock(f, fcntl.LOCK_UN)
    except FileNotFoundError:
        with open(_TOKEN_LOG, "w") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            json.dump([stats], f, indent=2)
            fcntl.flock(f, fcntl.LOCK_UN)


def _write_live_state(env: Environment) -> None:
    _STATE_DIR.mkdir(parents=True, exist_ok=True)
    state_path = _STATE_DIR / "live_state.json"
    snapshot = env.snapshot()

    population = _population_counts(env)
    agents_data = []
    for agent in env.agents.values():
        agents_data.append({
            "id": agent.state.agent_id,
            "type": agent.state.agent_type.value,
            "x": round(agent.state.position[0], 1),
            "y": round(agent.state.position[1], 1),
            "energy": round(agent.state.energy, 3),
            "age": agent.state.age,
        })

    state = {
        "cycle": env.cycle,
        "running": True,
        "pid": os.getpid(),
        "timestamp": __import__("datetime").datetime.now().isoformat(),
        "population": population,
        "total_agents": len(env.agents),
        "agents": agents_data,
        "cytokines": {
            k: {"mean": round(v.mean, 6), "max": round(v.max, 6), "total": round(v.total, 4)}
            for k, v in snapshot.cytokine_summary.items()
        },
        # FIX: last_opus_analysis ya está actualizado cuando llegamos aquí
        "last_opus_analysis": env.last_opus_analysis,
        "recent_events": list(env.events)[-20:],
        "population_history": env.history[-52:],
        "stopped_reason": None,
    }

    tmp = state_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2))
    tmp.replace(state_path)


def _mark_simulation_stopped(env: Environment) -> None:
    state_path = _STATE_DIR / "live_state.json"
    if state_path.exists():
        try:
            data = json.loads(state_path.read_text())
            data["running"] = False
            data["pid"] = None
            data["stopped_reason"] = "completed"
            state_path.write_text(json.dumps(data, indent=2))
        except Exception:
            pass


async def _decide(agent: BaseAgent, ctx: object, llm: LLMClient) -> AgentDecision:
    return await agent.reason_and_decide(ctx, llm)
