"""Tests del Rule Engine — valida que las reglas biológicas son correctas.

Estos tests corren sin LLM, sin API key, a $0.
Verifican que rule_engine_decide() produce las decisiones correctas
para cada combinación de estado del agente y contexto.

Ejecutar:
    cd ~/Desktop/oncobiome-swarm
    python3 -m pytest tests/ -v
"""
import sys
from pathlib import Path

# Añadir el directorio raíz al path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from models.agent_state import AgentAction, AgentType, LocalContext, NearbyAgentInfo
from llm.rule_engine import rule_engine_decide


def make_context(
    agent_type: AgentType,
    energy: float = 0.8,
    age: int = 5,
    nearby: list | None = None,
    cytokines: dict | None = None,
    metadata: dict | None = None,
    cycle: int = 10,
) -> LocalContext:
    """Helper para crear contextos de test."""
    return LocalContext(
        agent_id="test-agent",
        agent_type=agent_type,
        position=(50.0, 50.0),
        energy=energy,
        age=age,
        metadata=metadata or {},
        nearby_agents=nearby or [],
        cytokine_levels=cytokines or {"IL-6": 0.0, "VEGF": 0.0, "IFN-γ": 0.0},
        recent_memories=[],
        cycle=cycle,
    )


def nearby_immune(distance: float = 5.0, energy: float = 0.8) -> NearbyAgentInfo:
    return NearbyAgentInfo(
        agent_id="immune-1",
        agent_type=AgentType.IMMUNE_CELL,
        distance=distance,
        energy=energy,
    )


def nearby_tumor(distance: float = 5.0, energy: float = 0.7) -> NearbyAgentInfo:
    return NearbyAgentInfo(
        agent_id="tumor-1",
        agent_type=AgentType.TUMOR_CELL,
        distance=distance,
        energy=energy,
    )


# ── Tests TumorCell ────────────────────────────────────────────────────────────

class TestTumorCellRules:

    def test_signal_when_immune_nearby_high_energy(self):
        """Regla 1: ImmuneCell cerca + energy>0.5 → SIGNAL IL-6."""
        ctx = make_context(
            AgentType.TUMOR_CELL,
            energy=0.8,
            nearby=[nearby_immune()],
        )
        decision = rule_engine_decide(AgentType.TUMOR_CELL, ctx)
        assert decision.action == AgentAction.SIGNAL
        assert decision.signal_type == "IL-6"

    def test_migrate_when_immune_nearby_low_energy(self):
        """Regla 2: ImmuneCell cerca + energy≤0.5 → MIGRATE (huir)."""
        ctx = make_context(
            AgentType.TUMOR_CELL,
            energy=0.4,
            nearby=[nearby_immune()],
        )
        decision = rule_engine_decide(AgentType.TUMOR_CELL, ctx)
        assert decision.action == AgentAction.MIGRATE

    def test_proliferate_with_il6_no_immune(self):
        """Regla 3: IL-6>0.05 + sin inmune → PROLIFERATE."""
        ctx = make_context(
            AgentType.TUMOR_CELL,
            energy=0.6,
            nearby=[],
            cytokines={"IL-6": 0.1, "VEGF": 0.0, "IFN-γ": 0.0},
        )
        decision = rule_engine_decide(AgentType.TUMOR_CELL, ctx)
        assert decision.action == AgentAction.PROLIFERATE

    def test_proliferate_high_energy_no_immune(self):
        """Regla 4: energy>0.7 + sin inmune → PROLIFERATE."""
        ctx = make_context(
            AgentType.TUMOR_CELL,
            energy=0.9,
            nearby=[],
            cytokines={"IL-6": 0.0, "VEGF": 0.0, "IFN-γ": 0.0},
        )
        decision = rule_engine_decide(AgentType.TUMOR_CELL, ctx)
        assert decision.action == AgentAction.PROLIFERATE

    def test_quiesce_default(self):
        """Default: sin vecinos, energía media, sin citoquinas → QUIESCE."""
        ctx = make_context(
            AgentType.TUMOR_CELL,
            energy=0.5,
            nearby=[],
            cytokines={"IL-6": 0.0, "VEGF": 0.0, "IFN-γ": 0.0},
        )
        decision = rule_engine_decide(AgentType.TUMOR_CELL, ctx)
        assert decision.action == AgentAction.QUIESCE

    def test_first_match_signal_over_proliferate(self):
        """First-match: inmune cerca + IL-6 alto → SIGNAL (no PROLIFERATE)."""
        ctx = make_context(
            AgentType.TUMOR_CELL,
            energy=0.8,
            nearby=[nearby_immune()],
            cytokines={"IL-6": 0.2, "VEGF": 0.0, "IFN-γ": 0.0},
        )
        decision = rule_engine_decide(AgentType.TUMOR_CELL, ctx)
        assert decision.action == AgentAction.SIGNAL  # regla 1 gana sobre regla 3


# ── Tests ImmuneCell ───────────────────────────────────────────────────────────

class TestImmuneCellRules:

    def test_quiesce_when_exhausted(self):
        """Regla 1: age>15 + kills>2 → QUIESCE (agotamiento)."""
        ctx = make_context(
            AgentType.IMMUNE_CELL,
            age=20,
            metadata={"kills_count": 3},
        )
        decision = rule_engine_decide(AgentType.IMMUNE_CELL, ctx)
        assert decision.action == AgentAction.QUIESCE
        assert "exhausted" in decision.reasoning

    def test_not_exhausted_below_threshold(self):
        """Sin agotamiento: age<=15 o kills<=2 → no QUIESCE por agotamiento."""
        ctx = make_context(
            AgentType.IMMUNE_CELL,
            age=10,
            metadata={"kills_count": 1},
            nearby=[nearby_tumor()],
        )
        decision = rule_engine_decide(AgentType.IMMUNE_CELL, ctx)
        assert decision.action != AgentAction.QUIESCE

    def test_signal_ifng_when_ifng_high(self):
        """Regla 2: IFN-γ>0.08 → SIGNAL IFN-γ."""
        ctx = make_context(
            AgentType.IMMUNE_CELL,
            cytokines={"IL-6": 0.0, "VEGF": 0.0, "IFN-γ": 0.1},
            metadata={"kills_count": 0},
        )
        decision = rule_engine_decide(AgentType.IMMUNE_CELL, ctx)
        assert decision.action == AgentAction.SIGNAL
        assert decision.signal_type == "IFN-γ"

    def test_migrate_toward_tumor(self):
        """Regla 3: TumorCell cerca + energy>0.4 → MIGRATE."""
        ctx = make_context(
            AgentType.IMMUNE_CELL,
            energy=0.7,
            nearby=[nearby_tumor()],
            metadata={"kills_count": 0},
        )
        decision = rule_engine_decide(AgentType.IMMUNE_CELL, ctx)
        assert decision.action == AgentAction.MIGRATE

    def test_patrol_default(self):
        """Default: sin tumor cerca, sin IFN-γ → MIGRATE (patrol)."""
        ctx = make_context(
            AgentType.IMMUNE_CELL,
            nearby=[],
            metadata={"kills_count": 0},
        )
        decision = rule_engine_decide(AgentType.IMMUNE_CELL, ctx)
        assert decision.action == AgentAction.MIGRATE

    def test_exhaustion_takes_priority_over_ifng(self):
        """First-match: agotado + IFN-γ alto → QUIESCE (regla 1 gana sobre regla 2)."""
        ctx = make_context(
            AgentType.IMMUNE_CELL,
            age=20,
            metadata={"kills_count": 5},
            cytokines={"IL-6": 0.0, "VEGF": 0.0, "IFN-γ": 0.2},
        )
        decision = rule_engine_decide(AgentType.IMMUNE_CELL, ctx)
        assert decision.action == AgentAction.QUIESCE


# ── Tests MacrophageAgent ──────────────────────────────────────────────────────

class TestMacrophageRules:

    def test_m2_signals_il6(self):
        """Regla 1: polarization=M2 → SIGNAL IL-6."""
        ctx = make_context(
            AgentType.MACROPHAGE,
            metadata={"polarization": "M2"},
        )
        decision = rule_engine_decide(AgentType.MACROPHAGE, ctx)
        assert decision.action == AgentAction.SIGNAL
        assert decision.signal_type == "IL-6"

    def test_m1_migrates_toward_tumor(self):
        """Regla 2: polarization=M1 + TumorCell cerca → MIGRATE."""
        ctx = make_context(
            AgentType.MACROPHAGE,
            metadata={"polarization": "M1"},
            nearby=[nearby_tumor()],
        )
        decision = rule_engine_decide(AgentType.MACROPHAGE, ctx)
        assert decision.action == AgentAction.MIGRATE

    def test_m0_activates_with_ifng(self):
        """Regla 3: IFN-γ>0.05 → SIGNAL IFN-γ (activación M1)."""
        ctx = make_context(
            AgentType.MACROPHAGE,
            metadata={"polarization": "M0"},
            cytokines={"IL-6": 0.0, "VEGF": 0.0, "IFN-γ": 0.1},
        )
        decision = rule_engine_decide(AgentType.MACROPHAGE, ctx)
        assert decision.action == AgentAction.SIGNAL
        assert decision.signal_type == "IFN-γ"

    def test_quiesce_default_m0(self):
        """Default: M0 sin señales → QUIESCE."""
        ctx = make_context(
            AgentType.MACROPHAGE,
            metadata={"polarization": "M0"},
            nearby=[],
        )
        decision = rule_engine_decide(AgentType.MACROPHAGE, ctx)
        assert decision.action == AgentAction.QUIESCE

    def test_m2_priority_over_ifng(self):
        """First-match: M2 + IFN-γ alto → SIGNAL IL-6 (regla 1 gana sobre regla 3)."""
        ctx = make_context(
            AgentType.MACROPHAGE,
            metadata={"polarization": "M2"},
            cytokines={"IL-6": 0.0, "VEGF": 0.0, "IFN-γ": 0.2},
        )
        decision = rule_engine_decide(AgentType.MACROPHAGE, ctx)
        assert decision.action == AgentAction.SIGNAL
        assert decision.signal_type == "IL-6"


# ── Tests de confianza y formato ───────────────────────────────────────────────

class TestDecisionFormat:

    def test_all_decisions_have_confidence(self):
        """Todas las decisiones deben tener confidence entre 0 y 1."""
        contexts = [
            make_context(AgentType.TUMOR_CELL, energy=0.8, nearby=[nearby_immune()]),
            make_context(AgentType.TUMOR_CELL, energy=0.4, nearby=[nearby_immune()]),
            make_context(AgentType.TUMOR_CELL, energy=0.9),
            make_context(AgentType.IMMUNE_CELL, age=20, metadata={"kills_count": 5}),
            make_context(AgentType.IMMUNE_CELL, nearby=[nearby_tumor()], metadata={"kills_count": 0}),
            make_context(AgentType.MACROPHAGE, metadata={"polarization": "M2"}),
            make_context(AgentType.MACROPHAGE, metadata={"polarization": "M0"}),
        ]
        for ctx in contexts:
            decision = rule_engine_decide(ctx.agent_type, ctx)
            assert 0.0 <= decision.confidence <= 1.0, f"Confidence inválida: {decision.confidence}"

    def test_all_decisions_have_action(self):
        """Todas las decisiones deben tener una acción válida."""
        valid_actions = set(AgentAction)
        contexts = [
            make_context(AgentType.TUMOR_CELL),
            make_context(AgentType.IMMUNE_CELL, metadata={"kills_count": 0}),
            make_context(AgentType.MACROPHAGE, metadata={"polarization": "M0"}),
        ]
        for ctx in contexts:
            decision = rule_engine_decide(ctx.agent_type, ctx)
            assert decision.action in valid_actions

    def test_signal_decisions_have_signal_type(self):
        """Decisiones SIGNAL deben especificar signal_type."""
        ctx = make_context(
            AgentType.TUMOR_CELL,
            energy=0.8,
            nearby=[nearby_immune()],
        )
        decision = rule_engine_decide(AgentType.TUMOR_CELL, ctx)
        assert decision.action == AgentAction.SIGNAL
        assert decision.signal_type is not None
        assert len(decision.signal_type) > 0
