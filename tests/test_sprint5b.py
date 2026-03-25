"""Tests para Sprint 5B — ablation semántico y diseño n=10.

Valida:
1. prompts_abstract.py — mapeo correcto de entidades y señales
2. experiments.yaml — experimentos 5B presentes y configurados
3. experiment_loader — PROMPT_MODE se propaga correctamente
4. Pre-registro criterios H1/H0 documentados en experimentos
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import os
import pytest


# ── Tests prompts abstractos ─────────────────────────────────────────────────

class TestAbstractPrompts:
    def test_module_importable(self):
        from llm.prompts_abstract import build_abstract_system_prompt, build_abstract_user_prompt
        assert callable(build_abstract_system_prompt)
        assert callable(build_abstract_user_prompt)

    def test_abstract_prompt_nk_has_no_biomedical_terms(self):
        from models.agent_state import AgentType
        from llm.prompts_abstract import build_abstract_system_prompt
        prompt = build_abstract_system_prompt(AgentType.NK_CELL)
        forbidden = ["NK", "Natural Killer", "CD8", "IFN-γ", "IL-6",
                     "T cell", "lymphocyte", "cytokine"]
        for term in forbidden:
            assert term not in prompt, f"Término biomédico '{term}' en prompt abstracto NK"

    def test_abstract_prompt_cd8_has_no_biomedical_terms(self):
        from models.agent_state import AgentType
        from llm.prompts_abstract import build_abstract_system_prompt
        prompt = build_abstract_system_prompt(AgentType.IMMUNE_CELL)
        forbidden = ["NK", "Natural Killer", "CD8", "T cell", "lymphocyte",
                     "IFN-γ", "interferon", "cytokine"]
        for term in forbidden:
            assert term not in prompt, f"Término biomédico '{term}' en prompt abstracto CD8"

    def test_abstract_prompt_nk_preserves_causal_topology(self):
        """CRÍTICO: topología causal preservada sin nombres biomédicos."""
        from models.agent_state import AgentType
        from llm.prompts_abstract import build_abstract_system_prompt
        prompt = build_abstract_system_prompt(AgentType.NK_CELL)
        assert "Agent_A" in prompt
        assert "Agent_B" in prompt or "Agent_D" in prompt
        assert "Signal_X" in prompt
        assert "Signal_Y" in prompt
        assert "0.04" in prompt  # threshold supresión Signal_Y

    def test_abstract_prompt_dc_preserves_bridge_role(self):
        """DC es el puente innata-adaptativa — debe preservarse en abstracto."""
        from models.agent_state import AgentType
        from llm.prompts_abstract import build_abstract_system_prompt
        prompt = build_abstract_system_prompt(AgentType.DENDRITIC_CELL)
        assert "Agent_D" in prompt
        assert "Agent_B" in prompt
        assert "Signal_X" in prompt
        assert "tolerogenic" in prompt.lower() or "default" in prompt.lower()

    def test_build_abstract_user_prompt(self):
        """User prompt debe mapear entidades y señales correctamente."""
        from models.agent_state import AgentType, LocalContext
        from llm.prompts_abstract import build_abstract_user_prompt

        # LocalContext requiere agent_id y position (campos pydantic obligatorios)
        ctx = LocalContext(
            agent_id="test_nk_001",
            agent_type=AgentType.NK_CELL,
            position=(25.0, 25.0),
            cycle=10,
            energy=0.7,
            age=5,
            nearby_agents=[],
            cytokine_levels={"IFN-γ": 0.05, "IL-6": 0.03, "VEGF": 0.1},
            recent_memories=[],
            metadata={}
        )
        prompt = build_abstract_user_prompt(ctx)
        assert "Signal_X" in prompt   # IFN-γ → Signal_X
        assert "Signal_Y" in prompt   # IL-6  → Signal_Y
        assert "Signal_Z" in prompt   # VEGF  → Signal_Z
        assert "IFN-γ" not in prompt
        assert "IL-6" not in prompt

    def test_is_memory_store_subclass(self):
        from memory.base_store import MemoryStore
        from memory.null_store import NullMemoryStore
        assert issubclass(NullMemoryStore, MemoryStore)


# ── Tests experimentos Sprint 5B ─────────────────────────────────────────────

class TestSprint5BExperiments:
    def _load_yaml(self):
        import yaml
        f = Path(__file__).parent.parent / "experiments.yaml"
        with open(f) as fh:
            return yaml.safe_load(fh)["experiments"]

    def test_abstract_semantics_experiment_exists(self):
        exps = self._load_yaml()
        assert "ablation_abstract_semantics_llm" in exps

    def test_abstract_semantics_has_prompt_mode(self):
        exps = self._load_yaml()
        assert exps["ablation_abstract_semantics_llm"].get("prompt_mode") == "abstract"

    def test_abstract_semantics_same_biology_as_bridge(self):
        """El ablation semántico debe tener idéntica configuración biológica."""
        exps = self._load_yaml()
        bridge = exps["innate_adaptive_bridge_llm"]
        abstract = exps["ablation_abstract_semantics_llm"]
        bio_params = ["n_tumor_cells", "n_immune_cells", "n_macrophages",
                      "n_phytochemicals", "n_nk_cells", "n_dendritic_cells",
                      "total_cycles", "max_agents"]
        for p in bio_params:
            assert bridge.get(p) == abstract.get(p), \
                f"'{p}' difiere: bridge={bridge.get(p)}, abstract={abstract.get(p)}"

    def test_double_ablation_has_both_modes(self):
        exps = self._load_yaml()
        double = exps["ablation_abstract_semantics_no_memory_llm"]
        assert double.get("memory_mode") == "null"
        assert double.get("prompt_mode") == "abstract"

    def test_n10_experiments_exist(self):
        exps = self._load_yaml()
        assert "bridge_n10_llm" in exps
        assert "ablation_abstract_n10_llm" in exps

    def test_n10_abstract_has_prompt_mode(self):
        exps = self._load_yaml()
        assert exps["ablation_abstract_n10_llm"].get("prompt_mode") == "abstract"


# ── Tests experiment_loader con prompt_mode ───────────────────────────────────

class TestExperimentLoaderSprint5B:
    def test_apply_sets_prompt_mode_env(self):
        from simulation.experiment_loader import load_experiment, apply_experiment_to_env
        os.environ.pop("PROMPT_MODE", None)
        try:
            params = load_experiment("ablation_abstract_semantics_llm")
            apply_experiment_to_env(params)
            assert os.environ.get("PROMPT_MODE") == "abstract"
        finally:
            os.environ.pop("PROMPT_MODE", None)

    def test_normal_experiment_does_not_set_prompt_mode(self):
        from simulation.experiment_loader import load_experiment, apply_experiment_to_env
        os.environ.pop("PROMPT_MODE", None)
        try:
            params = load_experiment("innate_adaptive_bridge_llm")
            apply_experiment_to_env(params)
            assert os.environ.get("PROMPT_MODE") is None
        finally:
            os.environ.pop("PROMPT_MODE", None)

    def test_double_ablation_sets_both_env_vars(self):
        from simulation.experiment_loader import load_experiment, apply_experiment_to_env
        os.environ.pop("PROMPT_MODE", None)
        os.environ.pop("MEMORY_MODE", None)
        try:
            params = load_experiment("ablation_abstract_semantics_no_memory_llm")
            apply_experiment_to_env(params)
            assert os.environ.get("PROMPT_MODE") == "abstract"
            assert os.environ.get("MEMORY_MODE") == "null"
        finally:
            os.environ.pop("PROMPT_MODE", None)
            os.environ.pop("MEMORY_MODE", None)


# ── Pre-registro criterios H1/H0 ─────────────────────────────────────────────

class TestPreregisteredCriteria:
    def test_bridge_n10_description_mentions_wilcoxon(self):
        f = Path(__file__).parent.parent / "experiments.yaml"
        content = f.read_text()
        assert "Wilcoxon" in content or "wilcoxon" in content

    def test_abstract_experiment_description_meaningful(self):
        import yaml
        f = Path(__file__).parent.parent / "experiments.yaml"
        with open(f) as fh:
            data = yaml.safe_load(fh)
        exp = data["experiments"]["ablation_abstract_semantics_llm"]
        desc = exp.get("description", "")
        assert len(desc) > 20
        assert "abstract" in desc.lower() or "Agent" in desc or "semántica" in desc.lower()
