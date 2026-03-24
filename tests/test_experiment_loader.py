"""Tests del Experiment Loader — valida que los 7 experimentos del YAML
son coherentes y se cargan correctamente.

Sin LLM, sin tokens. Ejecutar:
    python3 -m pytest tests/test_experiment_loader.py -v
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from simulation.experiment_loader import load_experiment, list_experiments


VALID_EXPERIMENTS = [
    "cap80_baseline",
    "cap150_batch",
    "quick_validate",
    "full_rule_engine",
    "stress_cap200",
    "high_immune",
    "no_immune",
]


class TestExperimentLoader:
    """Valida carga y coherencia de experimentos."""

    def test_all_experiments_load(self):
        """Todos los experimentos deben cargarse sin error."""
        for name in VALID_EXPERIMENTS:
            params = load_experiment(name)
            assert isinstance(params, dict), f"Experimento {name} no devolvió dict"
            assert len(params) > 0, f"Experimento {name} está vacío"

    def test_description_stripped_from_params(self):
        """'description' no debe aparecer en los parámetros devueltos."""
        for name in VALID_EXPERIMENTS:
            params = load_experiment(name)
            assert "description" not in params, (
                f"Experimento {name} incluye 'description' en params"
            )

    def test_invalid_experiment_raises_systemexit(self):
        """Experimento inexistente debe provocar SystemExit."""
        with pytest.raises(SystemExit):
            load_experiment("experimento_que_no_existe")

    def test_rule_engine_experiments_have_no_llm(self):
        """Experimentos con rule engine deben tener llm_provider=rule_engine."""
        rule_engine_experiments = ["quick_validate", "full_rule_engine",
                                   "stress_cap200", "no_immune"]
        for name in rule_engine_experiments:
            params = load_experiment(name)
            assert params.get("llm_provider") == "rule_engine", (
                f"Experimento {name} debería usar rule_engine"
            )

    def test_llm_experiments_use_anthropic(self):
        """Experimentos con LLM real deben usar anthropic."""
        llm_experiments = ["cap80_baseline", "cap150_batch", "high_immune"]
        for name in llm_experiments:
            params = load_experiment(name)
            assert params.get("llm_provider") == "anthropic", (
                f"Experimento {name} debería usar anthropic"
            )

    def test_cap_values_are_positive(self):
        """max_agents debe ser positivo en todos los experimentos que lo definen."""
        for name in VALID_EXPERIMENTS:
            params = load_experiment(name)
            if "max_agents" in params:
                assert params["max_agents"] > 0, (
                    f"max_agents debe ser positivo en {name}"
                )

    def test_cycles_are_positive(self):
        """total_cycles debe ser positivo en todos los experimentos que lo definen."""
        for name in VALID_EXPERIMENTS:
            params = load_experiment(name)
            if "total_cycles" in params:
                assert params["total_cycles"] > 0, (
                    f"total_cycles debe ser positivo en {name}"
                )

    def test_quick_validate_is_zero_cost(self):
        """quick_validate debe usar rule_engine y tener ciclos cortos."""
        params = load_experiment("quick_validate")
        assert params["llm_provider"] == "rule_engine"
        assert params["total_cycles"] <= 30, (
            "quick_validate debe tener ≤30 ciclos para validación rápida"
        )

    def test_stress_cap_is_larger_than_baseline(self):
        """stress_cap200 debe tener max_agents > cap80_baseline."""
        stress = load_experiment("stress_cap200")
        baseline = load_experiment("cap80_baseline")
        assert stress["max_agents"] > baseline["max_agents"], (
            "stress_cap200 debe tener más agentes que cap80_baseline"
        )
