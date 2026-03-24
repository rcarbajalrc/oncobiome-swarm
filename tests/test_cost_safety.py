"""Tests de seguridad de coste — validan que el sistema nunca cae a
llamadas individuales cuando el batch falla.

CRÍTICO: estos tests deben pasar siempre antes de cualquier run con LLM real.
Ejecutar: python3 -m pytest tests/test_cost_safety.py -v
"""
import sys
import json
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from llm.client import LLMClient, BatchError
from llm.rule_engine import rule_engine_decide
from models.agent_state import AgentType, LocalContext


def make_ctx(agent_type: AgentType = AgentType.TUMOR_CELL) -> LocalContext:
    return LocalContext(
        agent_id="test",
        agent_type=agent_type,
        position=(50.0, 50.0),
        energy=0.8,
        age=5,
        metadata={},
        nearby_agents=[],
        cytokine_levels={"IL-6": 0.0, "VEGF": 0.0, "IFN-γ": 0.0},
        recent_memories=[],
        cycle=10,
    )


class TestBatchErrorOnFailure:
    """Verifica que el batch lanza BatchError en lugar de caer a llamadas individuales."""

    def setup_method(self):
        LLMClient._instance = None

    def _client(self) -> LLMClient:
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            return LLMClient()

    def test_batch_raises_batcherror_on_parse_failure(self):
        """Cuando el parse falla, call_haiku_batch lanza BatchError."""
        client = self._client()
        client._call_anthropic_cached = AsyncMock(return_value="this is not valid json")

        with pytest.raises(BatchError):
            asyncio.run(client.call_haiku_batch(
                system="test system",
                user_prompts=["agent1", "agent2", "agent3"],
                max_tokens_per_agent=50,
            ))

    def test_batch_raises_batcherror_on_wrong_count(self):
        """Cuando el array tiene N≠expected, lanza BatchError."""
        client = self._client()
        wrong_response = json.dumps([
            {"action": "SIGNAL", "reasoning": "test", "confidence": 0.9},
            {"action": "QUIESCE", "reasoning": "test", "confidence": 0.8},
        ])
        client._call_anthropic_cached = AsyncMock(return_value=wrong_response)

        with pytest.raises(BatchError):
            asyncio.run(client.call_haiku_batch(
                system="test system",
                user_prompts=["agent1", "agent2", "agent3"],
                max_tokens_per_agent=50,
            ))

    def test_batch_does_not_call_individually_on_failure(self):
        """Cuando el batch falla, call_haiku NO debe llamarse para cada agente."""
        client = self._client()
        client._call_anthropic_cached = AsyncMock(return_value="invalid json")
        call_haiku_spy = AsyncMock(return_value='{"action":"QUIESCE","reasoning":"test","confidence":0.8}')
        client.call_haiku = call_haiku_spy

        with pytest.raises(BatchError):
            asyncio.run(client.call_haiku_batch(
                system="test system",
                user_prompts=["a1", "a2", "a3", "a4", "a5"],
                max_tokens_per_agent=50,
            ))

        # CRÍTICO: call_haiku no debe haberse llamado en absoluto
        call_haiku_spy.assert_not_called()

    def test_batch_success_with_valid_response(self):
        """Cuando el batch funciona, devuelve N respuestas sin error."""
        client = self._client()
        decisions = [
            {"action": "SIGNAL", "signal_type": "IL-6", "reasoning": "suppress", "confidence": 0.95},
            {"action": "QUIESCE", "reasoning": "conserve energy", "confidence": 0.8},
            {"action": "PROLIFERATE", "reasoning": "safe niche", "confidence": 0.85},
        ]
        client._call_anthropic_cached = AsyncMock(return_value=json.dumps(decisions))

        result = asyncio.run(client.call_haiku_batch(
            system="test system",
            user_prompts=["a1", "a2", "a3"],
            max_tokens_per_agent=50,
        ))

        assert len(result) == 3
        assert json.loads(result[0])["action"] == "SIGNAL"

    def test_batch_fallback_counter_increments(self):
        """batch_fallbacks counter se incrementa cuando el parse falla."""
        client = self._client()
        client._call_anthropic_cached = AsyncMock(return_value="invalid")

        with pytest.raises(BatchError):
            asyncio.run(client.call_haiku_batch(
                system="test",
                user_prompts=["a1", "a2"],
                max_tokens_per_agent=50,
            ))

        assert client._cycle_tokens["batch_fallbacks"] == 1


class TestRuleEngineFallback:
    """Verifica que el rule engine produce decisiones válidas como fallback."""

    def test_rule_engine_costs_zero_tokens(self):
        """El rule engine no incrementa contadores de tokens."""
        LLMClient._instance = None
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            client = LLMClient()

        initial_calls = client._cycle_tokens["calls"]
        initial_input = client._cycle_tokens["input"]

        ctx = make_ctx(AgentType.TUMOR_CELL)
        decision = rule_engine_decide(AgentType.TUMOR_CELL, ctx)

        assert client._cycle_tokens["calls"] == initial_calls
        assert client._cycle_tokens["input"] == initial_input
        assert decision.action is not None

    def test_rule_engine_covers_all_agent_types(self):
        """El rule engine produce decisiones para todos los tipos de agente."""
        from models.agent_state import AgentAction
        valid_actions = set(AgentAction)

        for agent_type in [AgentType.TUMOR_CELL, AgentType.IMMUNE_CELL, AgentType.MACROPHAGE]:
            ctx = make_ctx(agent_type)
            decision = rule_engine_decide(agent_type, ctx)
            assert decision.action in valid_actions
            assert 0.0 <= decision.confidence <= 1.0


class TestCostGuarantees:
    """Garantías de coste — estos invariantes deben mantenerse siempre."""

    def test_batch_makes_exactly_one_api_call_for_n_agents(self):
        """N agentes en batch → _call_anthropic_cached llamado exactamente 1 vez."""
        LLMClient._instance = None
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            client = LLMClient()

        n_agents = 10
        decisions = [{"action": "QUIESCE", "reasoning": "test", "confidence": 0.8}] * n_agents
        mock = AsyncMock(return_value=json.dumps(decisions))
        client._call_anthropic_cached = mock

        asyncio.run(client.call_haiku_batch(
            system="test",
            user_prompts=[f"agent_{i}" for i in range(n_agents)],
            max_tokens_per_agent=50,
        ))

        # La garantía real: 1 llamada al método de API, no N
        mock.assert_called_once()

    def test_no_api_calls_in_no_llm_mode(self):
        """En modo no_llm, el engine no debe hacer ninguna llamada a la API."""
        from simulation.engine import SimulationEngine
        from simulation.environment import Environment
        from agents.tumor_cell import TumorCell
        from memory.inmemory_store import InMemoryStore

        env = Environment(grid_size=100)
        store = InMemoryStore()
        env.add_agent(TumorCell(position=(50.0, 50.0), memory_store=store, energy=0.8))

        LLMClient._instance = None
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            engine = SimulationEngine(env=env, no_llm=True)
            asyncio.run(engine.run(cycles=3))

        assert engine.llm._cycle_tokens["calls"] == 0
        assert engine.llm._cycle_tokens["input"] == 0

    def test_batch_error_never_triggers_individual_calls(self):
        """BatchError nunca debe resultar en llamadas individuales a la API."""
        LLMClient._instance = None
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            client = LLMClient()

        # Simula fallo de parse
        client._call_anthropic_cached = AsyncMock(return_value="bad json")
        call_haiku_mock = AsyncMock()
        client.call_haiku = call_haiku_mock

        with pytest.raises(BatchError):
            asyncio.run(client.call_haiku_batch(
                system="test",
                user_prompts=[f"a{i}" for i in range(20)],
                max_tokens_per_agent=50,
            ))

        # Ninguna llamada individual debe haberse producido
        call_haiku_mock.assert_not_called()
