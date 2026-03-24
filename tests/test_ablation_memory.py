"""Tests para el ablation study de memoria episódica (Sprint 5).

Valida que NullMemoryStore funciona correctamente y que el experimento
ablation_no_memory_llm está bien configurado.

Propósito científico:
    Responde a la crítica del revisor: los fenómenos emergentes identificados
    en Sprint 4 ¿dependen de la memoria episódica o emergen sin ella?
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import os
import pytest


# ── NullMemoryStore ──────────────────────────────────────────────────────────

class TestNullMemoryStore:
    def _make_store(self):
        from memory.null_store import NullMemoryStore
        return NullMemoryStore()

    def test_add_does_not_raise(self):
        store = self._make_store()
        store.add("decision: PROLIFERATE", user_id="agent_001")  # debe ser silencioso

    def test_get_recent_always_empty(self):
        store = self._make_store()
        store.add("decision: MIGRATE", user_id="agent_001")
        store.add("decision: SIGNAL", user_id="agent_001")
        result = store.get_recent("agent_001", limit=10)
        assert result == [], f"NullStore debe devolver lista vacía, got: {result}"

    def test_search_always_empty(self):
        store = self._make_store()
        store.add("CD8+ interaction detected", user_id="nk_001")
        result = store.search("CD8", user_id="nk_001", limit=5)
        assert result == []

    def test_multiple_agents_all_empty(self):
        store = self._make_store()
        for i in range(10):
            store.add(f"agent_{i} decision", user_id=f"agent_{i:03d}")
        for i in range(10):
            assert store.get_recent(f"agent_{i:03d}") == []

    def test_unknown_agent_empty(self):
        store = self._make_store()
        assert store.get_recent("never_seen_agent") == []
        assert store.search("any query", user_id="never_seen_agent") == []

    def test_is_memory_store_subclass(self):
        from memory.base_store import MemoryStore
        from memory.null_store import NullMemoryStore
        assert issubclass(NullMemoryStore, MemoryStore)


# ── MemoryFactory con MEMORY_MODE=null ───────────────────────────────────────

class TestMemoryFactoryAblation:
    def test_factory_returns_null_store_when_mode_null(self):
        from memory.null_store import NullMemoryStore
        from memory.factory import MemoryFactory
        os.environ["MEMORY_MODE"] = "null"
        try:
            store = MemoryFactory.create(mem0_api_key="")
            assert isinstance(store, NullMemoryStore), \
                f"Esperaba NullMemoryStore, got {type(store)}"
        finally:
            del os.environ["MEMORY_MODE"]

    def test_factory_returns_inmemory_by_default(self):
        from memory.inmemory_store import InMemoryStore
        from memory.factory import MemoryFactory
        os.environ.pop("MEMORY_MODE", None)
        store = MemoryFactory.create(mem0_api_key="")
        assert isinstance(store, InMemoryStore)

    def test_factory_null_overrides_api_key(self):
        """MEMORY_MODE=null debe tener prioridad sobre mem0_api_key."""
        from memory.null_store import NullMemoryStore
        from memory.factory import MemoryFactory
        os.environ["MEMORY_MODE"] = "null"
        try:
            # Aunque haya api_key, null mode tiene prioridad
            store = MemoryFactory.create(mem0_api_key="fake-key-for-test")
            assert isinstance(store, NullMemoryStore)
        finally:
            del os.environ["MEMORY_MODE"]


# ── Experiment loader: ablation experiments ───────────────────────────────────

class TestAblationExperiments:
    def test_ablation_experiments_exist_in_yaml(self):
        import yaml
        experiments_file = Path(__file__).parent.parent / "experiments.yaml"
        with open(experiments_file) as f:
            data = yaml.safe_load(f)
        experiments = data.get("experiments", {})
        required = [
            "ablation_no_memory_llm",
            "ablation_no_memory_rule",
            "ablation_no_memory_baseline_llm",
        ]
        for exp in required:
            assert exp in experiments, f"Experimento '{exp}' no encontrado en experiments.yaml"

    def test_ablation_llm_has_memory_mode_null(self):
        import yaml
        experiments_file = Path(__file__).parent.parent / "experiments.yaml"
        with open(experiments_file) as f:
            data = yaml.safe_load(f)
        exp = data["experiments"]["ablation_no_memory_llm"]
        assert exp.get("memory_mode") == "null"
        assert exp.get("llm_provider") == "anthropic"

    def test_ablation_same_biology_as_bridge(self):
        """El ablation debe tener la misma configuración biológica que el bridge."""
        import yaml
        experiments_file = Path(__file__).parent.parent / "experiments.yaml"
        with open(experiments_file) as f:
            data = yaml.safe_load(f)
        bridge = data["experiments"]["innate_adaptive_bridge_llm"]
        ablation = data["experiments"]["ablation_no_memory_llm"]
        bio_params = ["n_tumor_cells", "n_immune_cells", "n_macrophages",
                      "n_phytochemicals", "n_nk_cells", "n_dendritic_cells",
                      "total_cycles"]
        for p in bio_params:
            assert bridge.get(p) == ablation.get(p), \
                f"Parámetro '{p}' difiere: bridge={bridge.get(p)}, ablation={ablation.get(p)}"

    def test_apply_experiment_sets_memory_mode_env(self):
        from simulation.experiment_loader import load_experiment, apply_experiment_to_env
        os.environ.pop("MEMORY_MODE", None)
        try:
            params = load_experiment("ablation_no_memory_llm")
            apply_experiment_to_env(params)
            assert os.environ.get("MEMORY_MODE") == "null", \
                "apply_experiment_to_env debe setear MEMORY_MODE=null"
        finally:
            os.environ.pop("MEMORY_MODE", None)

    def test_apply_experiment_does_not_set_memory_mode_for_normal_exp(self):
        from simulation.experiment_loader import load_experiment, apply_experiment_to_env
        os.environ.pop("MEMORY_MODE", None)
        try:
            params = load_experiment("innate_adaptive_bridge_llm")
            apply_experiment_to_env(params)
            assert "MEMORY_MODE" not in os.environ or os.environ.get("MEMORY_MODE") != "null"
        finally:
            os.environ.pop("MEMORY_MODE", None)
