"""Tests de difusión de citoquinas, comportamiento del macrófago y memory factory.

Sin LLM, sin tokens. Ejecutar:
    python3 -m pytest tests/test_diffusion_memory.py -v
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import numpy as np
from unittest.mock import patch


# ── Tests de difusión ────────────────────────────────────────────────────────

class TestCytokineFieldManager:
    """Valida difusión, decay y emisión de citoquinas."""

    def _make_field(self, grid_size=50, decay=0.04, sigma=1.8):
        from simulation.diffusion import CytokineFieldManager
        return CytokineFieldManager(grid_size=grid_size, decay=decay, sigma=sigma)

    def test_initial_fields_are_zero(self):
        mgr = self._make_field()
        for field in mgr.fields.values():
            assert field.sum() == 0.0

    def test_emit_adds_concentration(self):
        mgr = self._make_field()
        mgr.emit("IL-6", (25.0, 25.0), 1.0)
        assert mgr.sample("IL-6", (25.0, 25.0)) > 0.0

    def test_sample_returns_zero_empty_field(self):
        mgr = self._make_field()
        assert mgr.sample("VEGF", (10.0, 10.0)) == 0.0

    def test_step_applies_decay(self):
        mgr = self._make_field(decay=0.04)
        mgr.emit("IL-6", (25.0, 25.0), 1.0)
        total_before = mgr.fields["IL-6"].sum()
        mgr.step()
        assert mgr.fields["IL-6"].sum() < total_before

    def test_step_diffuses_concentration(self):
        mgr = self._make_field(sigma=1.8)
        mgr.emit("IL-6", (25.0, 25.0), 10.0)
        mgr.step()
        assert mgr.sample("IL-6", (26.0, 25.0)) > 0.0

    def test_decay_rate_calibrated(self):
        """decay=0.04 calibrado TME PDAC."""
        mgr = self._make_field(decay=0.04)
        mgr.emit("IL-6", (25.0, 25.0), 1.0)
        mgr.step()
        assert mgr.sample("IL-6", (25.0, 25.0)) < 1.0

    def test_multiple_steps_converge_to_zero(self):
        mgr = self._make_field(decay=0.10)
        mgr.emit("IL-6", (25.0, 25.0), 1.0)
        for _ in range(50):
            mgr.step()
        assert mgr.fields["IL-6"].sum() < 0.01

    def test_no_negative_concentrations(self):
        mgr = self._make_field()
        mgr.emit("IFN-γ", (10.0, 10.0), 0.5)
        for _ in range(20):
            mgr.step()
        for field in mgr.fields.values():
            assert field.min() >= 0.0

    def test_summary_returns_correct_structure(self):
        mgr = self._make_field()
        mgr.emit("VEGF", (25.0, 25.0), 1.0)
        summary = mgr.summary()
        for key in ("IL-6", "VEGF", "IFN-γ"):
            assert key in summary
        for stats in summary.values():
            assert "mean" in stats and "max" in stats and "total" in stats

    def test_vegf_summary_total_positive_after_emit(self):
        mgr = self._make_field()
        mgr.emit("VEGF", (25.0, 25.0), 0.25)
        summary = mgr.summary()
        assert summary["VEGF"]["total"] > 0.0
        assert summary["IL-6"]["total"] == 0.0

    def test_independent_fields(self):
        mgr = self._make_field()
        mgr.emit("IL-6", (25.0, 25.0), 1.0)
        mgr.step()
        assert mgr.fields["VEGF"].sum() == 0.0
        assert mgr.fields["IFN-γ"].sum() == 0.0


# ── Tests del MacrophageAgent ─────────────────────────────────────────────────

class TestMacrophageAgent:
    """Valida comportamiento completo del macrófago incluyendo polarización."""

    def _make_macro(self, position=(50.0, 50.0), polarization="M0"):
        from agents.macrophage_agent import MacrophageAgent
        from memory.inmemory_store import InMemoryStore
        from config import get_config
        get_config.cache_clear()
        macro = MacrophageAgent(position=position, memory_store=InMemoryStore(), energy=0.80)
        macro.state.metadata["polarization"] = polarization
        return macro

    def test_default_action_m0_is_migrate(self):
        """M0 explora migrando (patrulla el TME en búsqueda de señales).

        _default_action() devuelve MIGRATE para M0 y M1 — exploración/caza.
        Solo M2 señaliza IL-6 por defecto (comportamiento pro-tumoral).
        """
        from models.agent_state import AgentAction
        macro = self._make_macro(polarization="M0")
        assert macro._default_action() == AgentAction.MIGRATE

    def test_default_action_m1_is_migrate(self):
        """M1 migra hacia el tumor por defecto."""
        from models.agent_state import AgentAction
        macro = self._make_macro(polarization="M1")
        assert macro._default_action() == AgentAction.MIGRATE

    def test_default_action_m2_is_signal(self):
        """M2 señaliza IL-6 por defecto (pro-tumoral, inmunosupresor)."""
        from models.agent_state import AgentAction
        macro = self._make_macro(polarization="M2")
        assert macro._default_action() == AgentAction.SIGNAL

    def test_initial_polarization_is_m0(self):
        macro = self._make_macro()
        assert macro.state.metadata.get("polarization") == "M0"

    def test_initial_energy_calibrated(self):
        """Energía inicial 0.80 calibrado KRAS G12D."""
        from config import get_config
        get_config.cache_clear()
        assert get_config().macrophage_initial_energy == 0.80

    def test_m1_macro_has_correct_signal(self):
        """M1 señaliza IFN-γ (pro-inflamatorio)."""
        macro = self._make_macro(polarization="M1")
        assert macro._default_signal() == "IFN-γ"

    def test_m2_macro_has_correct_signal(self):
        """M2 señaliza IL-6 (anti-inflamatorio, favorece tumor)."""
        macro = self._make_macro(polarization="M2")
        assert macro._default_signal() == "IL-6"

    def test_macrophage_alive_on_init(self):
        macro = self._make_macro()
        assert macro.state.alive is True

    def test_macrophage_agent_type(self):
        from models.agent_state import AgentType
        macro = self._make_macro()
        assert macro.state.agent_type == AgentType.MACROPHAGE


# ── Tests del Memory Factory ──────────────────────────────────────────────────

class TestMemoryFactory:
    """Valida que el factory crea el store correcto según configuración."""

    def test_no_api_key_returns_inmemory(self):
        from memory.factory import MemoryFactory
        from memory.inmemory_store import InMemoryStore
        store = MemoryFactory.create(mem0_api_key="")
        assert isinstance(store, InMemoryStore)

    def test_invalid_api_key_falls_back_to_inmemory(self):
        from memory.factory import MemoryFactory
        from memory.inmemory_store import InMemoryStore
        store = MemoryFactory.create(mem0_api_key="invalid-key-that-will-fail")
        assert isinstance(store, InMemoryStore)

    def test_inmemory_store_add_and_retrieve(self):
        from memory.inmemory_store import InMemoryStore
        store = InMemoryStore()
        store.add("C5:PROLIFERATE(safe niche)", user_id="agent_abc123")
        memories = store.get_recent("agent_abc123", limit=5)
        assert len(memories) == 1
        assert "PROLIFERATE" in memories[0]

    def test_inmemory_store_respects_limit(self):
        from memory.inmemory_store import InMemoryStore
        store = InMemoryStore()
        for i in range(10):
            store.add(f"memoria_{i}", user_id="agent_test")
        memories = store.get_recent("agent_test", limit=3)
        assert len(memories) <= 3

    def test_inmemory_store_different_agents_isolated(self):
        from memory.inmemory_store import InMemoryStore
        store = InMemoryStore()
        store.add("memoria_agente_1", user_id="agent_001")
        store.add("memoria_agente_2", user_id="agent_002")
        mems_1 = store.get_recent("agent_001", limit=5)
        mems_2 = store.get_recent("agent_002", limit=5)
        assert all("agente_1" in m for m in mems_1)
        assert all("agente_2" in m for m in mems_2)

    def test_inmemory_store_empty_returns_empty(self):
        from memory.inmemory_store import InMemoryStore
        store = InMemoryStore()
        assert store.get_recent("agent_nuevo", limit=5) == []

    def test_factory_uses_env_key_when_available(self):
        from memory.factory import MemoryFactory
        from memory.inmemory_store import InMemoryStore
        with patch.dict("os.environ", {"MEM0_API_KEY": "fake-key"}):
            store = MemoryFactory.create(mem0_api_key="fake-key")
        assert isinstance(store, InMemoryStore)
