"""Tests de los 3 fixes de plataforma:
  1. Opus se guarda en logs/opus_history.json
  2. token_usage incluye llm_decisions y rule_engine_decisions
  3. compare_runs.py extrae métricas correctamente del CSV

Sin LLM, sin tokens. Ejecutar:
    python3 -m pytest tests/test_platform_fixes.py -v
"""
import sys
import csv
import json
import asyncio
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from simulation.engine import SimulationEngine, _save_opus_analysis
from simulation.environment import Environment
from agents.tumor_cell import TumorCell
from agents.immune_cell import ImmuneCell
from memory.inmemory_store import InMemoryStore
from llm.client import LLMClient


def make_env(n_tumor=3, n_immune=2) -> Environment:
    from config import get_config
    get_config.cache_clear()
    env = Environment(grid_size=100)
    store = InMemoryStore()
    for i in range(n_tumor):
        env.add_agent(TumorCell(position=(20.0 + i*10, 50.0), memory_store=store, energy=0.8))
    for i in range(n_immune):
        env.add_agent(ImmuneCell(position=(70.0 + i*8, 50.0), memory_store=store, energy=0.85))
    return env


class TestOpusPersistence:
    """Fix 1: Opus se guarda en logs/opus_history.json."""

    def test_save_opus_creates_file(self, tmp_path):
        import simulation.engine as eng_module
        original = eng_module._OPUS_LOG
        eng_module._OPUS_LOG = tmp_path / "opus_history.json"
        try:
            _save_opus_analysis("Test analysis ciclo 25", 25)
            assert (tmp_path / "opus_history.json").exists()
        finally:
            eng_module._OPUS_LOG = original

    def test_save_opus_content_correct(self, tmp_path):
        import simulation.engine as eng_module
        original = eng_module._OPUS_LOG
        eng_module._OPUS_LOG = tmp_path / "opus_history.json"
        try:
            _save_opus_analysis("Tumor dominance detected.", 25)
            history = json.loads((tmp_path / "opus_history.json").read_text())
            assert len(history) == 1
            assert history[0]["cycle"] == 25
            assert history[0]["analysis"] == "Tumor dominance detected."
            assert "pid" in history[0]
        finally:
            eng_module._OPUS_LOG = original

    def test_save_opus_multiple_cycles(self, tmp_path):
        import simulation.engine as eng_module
        original = eng_module._OPUS_LOG
        eng_module._OPUS_LOG = tmp_path / "opus_history.json"
        try:
            _save_opus_analysis("Analysis ciclo 25", 25)
            _save_opus_analysis("Analysis ciclo 50", 50)
            _save_opus_analysis("Analysis ciclo 75", 75)
            history = json.loads((tmp_path / "opus_history.json").read_text())
            assert len(history) == 3
            cycles = [e["cycle"] for e in history]
            assert 25 in cycles and 50 in cycles and 75 in cycles
        finally:
            eng_module._OPUS_LOG = original

    def test_save_opus_no_duplicates_same_cycle(self, tmp_path):
        import simulation.engine as eng_module
        original = eng_module._OPUS_LOG
        eng_module._OPUS_LOG = tmp_path / "opus_history.json"
        try:
            _save_opus_analysis("Primera version", 25)
            _save_opus_analysis("Segunda version", 25)
            history = json.loads((tmp_path / "opus_history.json").read_text())
            cycle_25 = [e for e in history if e["cycle"] == 25]
            assert len(cycle_25) == 1
            assert cycle_25[0]["analysis"] == "Segunda version"
        finally:
            eng_module._OPUS_LOG = original


class TestDecisionCounters:
    """Fix 2: token_usage incluye llm_decisions y rule_engine_decisions."""

    def test_rule_engine_decisions_counted(self, tmp_path):
        import simulation.engine as eng_module
        original_token_log = eng_module._TOKEN_LOG
        eng_module._TOKEN_LOG = tmp_path / "token_usage.json"

        LLMClient._instance = None
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            env = make_env(n_tumor=5, n_immune=2)
            engine = SimulationEngine(env=env, no_llm=True)
            asyncio.run(engine.run(cycles=3))

        eng_module._TOKEN_LOG = original_token_log

        log = json.loads((tmp_path / "token_usage.json").read_text())
        assert len(log) == 3
        for entry in log:
            assert "llm_decisions" in entry
            assert "rule_engine_decisions" in entry
            assert "llm_pct" in entry
            assert entry["llm_decisions"] == 0
            assert entry["rule_engine_decisions"] > 0
            assert entry["llm_pct"] == 0.0

    def test_llm_pct_field_present(self, tmp_path):
        import simulation.engine as eng_module
        original_token_log = eng_module._TOKEN_LOG
        eng_module._TOKEN_LOG = tmp_path / "token_usage.json"

        LLMClient._instance = None
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            env = make_env()
            engine = SimulationEngine(env=env, no_llm=True)
            asyncio.run(engine.run(cycles=2))

        eng_module._TOKEN_LOG = original_token_log

        log = json.loads((tmp_path / "token_usage.json").read_text())
        for entry in log:
            assert 0.0 <= entry["llm_pct"] <= 100.0


class TestCompareRuns:
    """Fix 3: compare_runs extrae métricas correctamente del CSV."""

    def _make_csv(self, tmp_path: Path, run_id: str, n_cycles: int,
                  immune_collapse_at: int = None, n_immune: int = 5) -> Path:
        """Genera un CSV sintético con n_immune ImmuneCells por ciclo.

        n_immune debe ser >= 3 para que extract_metrics active el cálculo
        de colapso inmune (requiere immune_peak >= 3, igual que la run real).
        Default 5 — igual que el seed KRAS G12D calibrado.
        """
        csv_file = tmp_path / f"decisions_{run_id}.csv"
        headers = ["run_id", "cycle", "agent_id", "agent_type", "action",
                   "signal_type", "reasoning", "confidence", "energy", "age",
                   "nearby_count", "il6", "vegf", "ifng", "kills_count", "polarization"]
        rows = []
        for c in range(n_cycles):
            rows.append({
                "run_id": run_id, "cycle": c, "agent_id": "t001",
                "agent_type": "TumorCell", "action": "PROLIFERATE",
                "signal_type": "", "reasoning": "expand", "confidence": 0.85,
                "energy": 0.75, "age": c, "nearby_count": 3,
                "il6": 0.05, "vegf": 0.0, "ifng": 0.0,
                "kills_count": 0, "polarization": ""
            })
            if immune_collapse_at is None or c < immune_collapse_at:
                for idx in range(n_immune):
                    rows.append({
                        "run_id": run_id, "cycle": c,
                        "agent_id": f"i{idx:03d}",
                        "agent_type": "ImmuneCell", "action": "MIGRATE",
                        "signal_type": "", "reasoning": "patrol", "confidence": 0.8,
                        "energy": 0.85, "age": c, "nearby_count": 0,
                        "il6": 0.0, "vegf": 0.0, "ifng": 0.0,
                        "kills_count": 0, "polarization": ""
                    })

        with open(csv_file, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            writer.writerows(rows)
        return csv_file

    def test_extract_metrics_immune_collapse(self, tmp_path):
        """extract_metrics detecta el colapso cuando immune_peak >= 3.

        Con n_immune=5 (igual que el seed KRAS G12D calibrado), el pico
        es 5 >= 3 y el colapso se detecta en ciclo 20.
        """
        from scripts.compare_runs import extract_metrics, load_all_runs

        csv_file = self._make_csv(
            tmp_path, "test_run_001", n_cycles=50,
            immune_collapse_at=20, n_immune=5
        )
        all_runs = load_all_runs(csv_file)
        assert "test_run_001" in all_runs

        metrics = extract_metrics(all_runs["test_run_001"])
        assert metrics["immune_collapse_cycle"] is not None, (
            "Con 5 ImmuneCells que desaparecen en c20, immune_peak=5 >= 3 → colapso detectable"
        )
        assert metrics["immune_collapse_cycle"] <= 22

    def test_extract_metrics_tumor_peak(self, tmp_path):
        csv_file = self._make_csv(tmp_path, "test_run_002", n_cycles=30)
        from scripts.compare_runs import extract_metrics, load_all_runs
        all_runs = load_all_runs(csv_file)
        metrics = extract_metrics(all_runs["test_run_002"])
        assert metrics["tumor_peak"] >= 1

    def test_biological_days_conversion(self, tmp_path):
        """Conversión a días biológicos: 1 ciclo = 52h/24 = 2.17 días (PANC-1)."""
        from scripts.compare_runs import extract_metrics, load_all_runs, BIOLOGICAL_DAYS_PER_CYCLE

        assert abs(BIOLOGICAL_DAYS_PER_CYCLE - 52/24) < 0.01

        csv_file = self._make_csv(
            tmp_path, "test_run_003", n_cycles=40,
            immune_collapse_at=15, n_immune=5
        )
        all_runs = load_all_runs(csv_file)
        metrics = extract_metrics(all_runs["test_run_003"])

        if metrics.get("immune_collapse_cycle"):
            expected_days = round(
                metrics["immune_collapse_cycle"] * BIOLOGICAL_DAYS_PER_CYCLE, 1
            )
            assert metrics["immune_collapse_days"] == expected_days

    def test_compare_multiple_runs(self, tmp_path):
        """Immune boost debe retrasar el colapso respecto al baseline."""
        from scripts.compare_runs import extract_metrics, load_all_runs

        csv_a = self._make_csv(
            tmp_path, "run_baseline", n_cycles=50,
            immune_collapse_at=15, n_immune=5
        )
        csv_b = self._make_csv(
            tmp_path, "run_immune_boost", n_cycles=50,
            immune_collapse_at=35, n_immune=5
        )

        combined = tmp_path / "decisions_combined.csv"
        headers = ["run_id", "cycle", "agent_id", "agent_type", "action",
                   "signal_type", "reasoning", "confidence", "energy", "age",
                   "nearby_count", "il6", "vegf", "ifng", "kills_count", "polarization"]
        rows_a = list(csv.DictReader(open(csv_a)))
        rows_b = list(csv.DictReader(open(csv_b)))
        with open(combined, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            writer.writerows(rows_a + rows_b)

        all_runs = load_all_runs(combined)
        assert len(all_runs) == 2

        m_baseline = extract_metrics(all_runs["run_baseline"])
        m_boost = extract_metrics(all_runs["run_immune_boost"])

        if m_baseline.get("immune_collapse_cycle") and m_boost.get("immune_collapse_cycle"):
            assert m_boost["immune_collapse_cycle"] > m_baseline["immune_collapse_cycle"]
