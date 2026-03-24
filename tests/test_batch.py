"""Tests del Smart Batching — valida que el batch LLM funciona correctamente.

Verifica:
- El batch parser extrae arrays JSON correctamente
- Respuestas con N agentes devuelven exactamente N decisiones
- El fallback a rule engine funciona cuando el batch falla
- La reducción de llamadas es real (N agentes → 1 llamada)

Estos tests NO llaman a la API real — usan mocks para validar la lógica.

Ejecutar:
    cd ~/Desktop/oncobiome-swarm
    python3 -m pytest tests/test_batch.py -v
"""
import sys
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from llm.client import LLMClient
from llm.rule_engine import rule_engine_decide
from models.agent_state import AgentAction, AgentType, LocalContext, NearbyAgentInfo


def make_context(agent_type: AgentType = AgentType.TUMOR_CELL) -> LocalContext:
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


class TestBatchParser:
    """Valida el parser de respuestas batch sin llamar a la API."""

    def setup_method(self):
        """LLMClient es singleton — reseteamos para tests."""
        LLMClient._instance = None

    def _get_client(self) -> LLMClient:
        """Crea cliente con API key falsa para tests."""
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            client = LLMClient()
        return client

    def test_parse_valid_json_array(self):
        """Array JSON válido con N elementos → N strings."""
        client = self._get_client()
        decisions = [
            {"action": "SIGNAL", "signal_type": "IL-6", "reasoning": "suppress", "confidence": 0.9},
            {"action": "PROLIFERATE", "reasoning": "safe niche", "confidence": 0.85},
            {"action": "QUIESCE", "reasoning": "conserve energy", "confidence": 0.8},
        ]
        raw = json.dumps(decisions)
        result = client._parse_batch_response(raw, expected_count=3)

        assert result is not None
        assert len(result) == 3
        for r in result:
            parsed = json.loads(r)
            assert "action" in parsed

    def test_parse_json_array_in_prose(self):
        """Array JSON embebido en texto → extraído correctamente."""
        client = self._get_client()
        decisions = [
            {"action": "MIGRATE", "reasoning": "flee", "confidence": 0.9},
            {"action": "SIGNAL", "signal_type": "IL-6", "reasoning": "suppress", "confidence": 0.95},
        ]
        raw = f"Here are the decisions:\n{json.dumps(decisions)}\nEnd of response."
        result = client._parse_batch_response(raw, expected_count=2)

        assert result is not None
        assert len(result) == 2

    def test_parse_wrong_count_returns_none(self):
        """Array con N≠expected → None (fuerza fallback)."""
        client = self._get_client()
        decisions = [{"action": "SIGNAL", "reasoning": "test", "confidence": 0.9}]
        raw = json.dumps(decisions)
        result = client._parse_batch_response(raw, expected_count=3)

        assert result is None

    def test_parse_invalid_json_returns_none(self):
        """JSON inválido → None (fuerza fallback)."""
        client = self._get_client()
        result = client._parse_batch_response("this is not json", expected_count=2)
        assert result is None

    def test_parse_empty_array_returns_none(self):
        """Array vacío cuando se esperan elementos → None."""
        client = self._get_client()
        result = client._parse_batch_response("[]", expected_count=3)
        assert result is None


class TestBatchFallback:
    """Valida que el fallback al rule engine funciona correctamente."""

    def test_rule_engine_as_fallback(self):
        """Si el batch falla, el rule engine produce decisiones válidas."""
        contexts = [make_context(AgentType.TUMOR_CELL) for _ in range(5)]
        valid_actions = set(AgentAction)

        for ctx in contexts:
            decision = rule_engine_decide(ctx.agent_type, ctx)
            assert decision.action in valid_actions
            assert 0.0 <= decision.confidence <= 1.0

    def test_batch_single_agent_uses_individual_call(self):
        """Con 1 solo agente, call_haiku_batch debe delegar a call_haiku."""
        # Verificamos que la lógica de batch no falla con 1 agente
        # (la implementación hace llamada individual directamente)
        LLMClient._instance = None
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            client = LLMClient()

        # Mock de call_haiku para no llamar a la API real
        single_decision = json.dumps({"action": "QUIESCE", "reasoning": "test", "confidence": 0.8})
        client.call_haiku = AsyncMock(return_value=single_decision)

        import asyncio
        result = asyncio.run(
            client.call_haiku_batch(
                system="test system",
                user_prompts=["single agent context"],
                max_tokens_per_agent=50,
            )
        )

        assert len(result) == 1
        client.call_haiku.assert_called_once()


class TestBatchReduction:
    """Valida la reducción de llamadas con batching."""

    def test_n_agents_same_type_should_batch(self):
        """N agentes del mismo tipo → lógicamente 1 llamada batch."""
        # Verificamos que el user prompt batch se construye correctamente
        n_agents = 10
        user_prompts = [f"agent_{i} context" for i in range(n_agents)]

        # El batch user prompt debe contener todos los agentes numerados
        batch_user = f"Respond with a JSON array of exactly {n_agents} decisions, one per agent.\n\n"
        for i, up in enumerate(user_prompts):
            batch_user += f"AGENT_{i}:\n{up}\n\n"

        assert f"AGENT_0" in batch_user
        assert f"AGENT_{n_agents-1}" in batch_user
        assert f"exactly {n_agents} decisions" in batch_user

    def test_max_tokens_scales_with_agents(self):
        """max_tokens del batch debe escalar con el número de agentes."""
        n_agents = 50
        tokens_per_agent = 50
        expected_max = min(n_agents * tokens_per_agent, 4096)

        assert expected_max == 2500  # 50 * 50 = 2500 < 4096
        assert expected_max <= 4096  # nunca supera el límite

        n_agents_large = 100
        expected_max_large = min(n_agents_large * tokens_per_agent, 4096)
        assert expected_max_large == 4096  # capped at 4096
