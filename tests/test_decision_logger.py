"""Tests del Decision Logger — valida que el CSV se genera correctamente.

Sin LLM, sin tokens. Ejecutar:
    python3 -m pytest tests/test_decision_logger.py -v
"""
import sys
import csv
import asyncio
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from unittest.mock import patch

from models.agent_state import AgentAction, AgentDecision, AgentType, LocalContext


def make_ctx(agent_type: AgentType = AgentType.TUMOR_CELL) -> LocalContext:
    return LocalContext(
        agent_id="test-agent-001",
        agent_type=agent_type,
        position=(50.0, 50.0),
        energy=0.75,
        age=10,
        metadata={"kills_count": 2, "polarization": "M0"},
        nearby_agents=[],
        cytokine_levels={"IL-6": 0.05, "VEGF": 0.02, "IFN-γ": 0.0},
        recent_memories=[],
        cycle=5,
    )


def make_decision(action: AgentAction = AgentAction.PROLIFERATE) -> AgentDecision:
    return AgentDecision(
        action=action,
        signal_type="IL-6" if action == AgentAction.SIGNAL else None,
        reasoning="expand uncontested",
        confidence=0.85,
    )


def make_logger(log_file: Path, enabled: bool = True):
    """Crea un DecisionLogger apuntando a log_file en lugar del path por defecto."""
    import simulation.decision_logger as dl_module
    original = dl_module._DECISIONS_LOG
    dl_module._DECISIONS_LOG = log_file
    from simulation.decision_logger import DecisionLogger
    logger = DecisionLogger(enabled=enabled)
    dl_module._DECISIONS_LOG = original
    return logger


class TestDecisionLoggerCSV:
    """Valida que el CSV se genera con las columnas y valores correctos."""

    def test_logger_creates_csv_file(self, tmp_path):
        """El logger debe crear el fichero CSV al inicializarse."""
        log_file = tmp_path / "decisions.csv"
        logger = make_logger(log_file)
        logger.close()
        assert log_file.exists()

    def test_logger_writes_header(self, tmp_path):
        """El CSV debe tener los headers correctos."""
        log_file = tmp_path / "decisions.csv"
        logger = make_logger(log_file)
        logger.close()

        with open(log_file) as f:
            reader = csv.DictReader(f)
            headers = reader.fieldnames

        expected = [
            "run_id", "cycle", "agent_id", "agent_type", "action",
            "signal_type", "reasoning", "confidence", "energy", "age",
            "nearby_count", "il6", "vegf", "ifng", "kills_count", "polarization"
        ]
        assert headers == expected

    def test_logger_writes_decision_row(self, tmp_path):
        """Cada decisión debe generar una fila con los valores correctos."""
        log_file = tmp_path / "decisions.csv"
        logger = make_logger(log_file)
        ctx = make_ctx(AgentType.TUMOR_CELL)
        decision = make_decision(AgentAction.PROLIFERATE)
        logger.log(cycle=5, agent_id="test-agent-001",
                  agent_type="TumorCell", decision=decision, ctx=ctx)
        logger.close()

        with open(log_file) as f:
            rows = list(csv.DictReader(f))

        assert len(rows) == 1
        row = rows[0]
        assert row["action"] == "PROLIFERATE"
        assert row["agent_type"] == "TumorCell"
        assert float(row["energy"]) == pytest.approx(0.75)
        assert int(row["age"]) == 10
        assert float(row["il6"]) == pytest.approx(0.05)
        assert row["reasoning"] == "expand uncontested"
        assert float(row["confidence"]) == pytest.approx(0.85)

    def test_logger_disabled_writes_nothing(self, tmp_path):
        """Con enabled=False, no se debe crear ni escribir nada."""
        log_file = tmp_path / "decisions.csv"
        logger = make_logger(log_file, enabled=False)
        ctx = make_ctx()
        decision = make_decision()
        logger.log(cycle=1, agent_id="test", agent_type="TumorCell",
                  decision=decision, ctx=ctx)
        logger.close()
        assert not log_file.exists()

    def test_logger_writes_multiple_cycles(self, tmp_path):
        """Múltiples ciclos deben generar múltiples filas."""
        log_file = tmp_path / "decisions.csv"
        logger = make_logger(log_file)
        ctx = make_ctx()
        for cycle in range(5):
            decision = make_decision(AgentAction.QUIESCE)
            logger.log(cycle=cycle, agent_id=f"agent-{cycle}",
                      agent_type="TumorCell", decision=decision, ctx=ctx)
        logger.close()

        with open(log_file) as f:
            rows = list(csv.DictReader(f))

        assert len(rows) == 5
        for i, row in enumerate(rows):
            assert int(row["cycle"]) == i

    def test_signal_type_recorded_correctly(self, tmp_path):
        """Para acciones SIGNAL, signal_type debe registrarse."""
        log_file = tmp_path / "decisions.csv"
        logger = make_logger(log_file)
        ctx = make_ctx()
        decision = make_decision(AgentAction.SIGNAL)
        logger.log(cycle=1, agent_id="test", agent_type="TumorCell",
                  decision=decision, ctx=ctx)
        logger.close()

        with open(log_file) as f:
            rows = list(csv.DictReader(f))

        assert rows[0]["signal_type"] == "IL-6"

    def test_logger_integration_with_simulation(self, tmp_path):
        """El logger debe capturar decisiones durante una run --no-llm."""
        from simulation.engine import SimulationEngine
        from simulation.environment import Environment
        from agents.tumor_cell import TumorCell
        from memory.inmemory_store import InMemoryStore
        from llm.client import LLMClient
        import simulation.decision_logger as dl_module

        log_file = tmp_path / "decisions.csv"

        env = Environment(grid_size=100)
        s = InMemoryStore()
        for i in range(3):
            env.add_agent(TumorCell(
                position=(20.0 + i * 5, 50.0),
                memory_store=s,
                energy=0.8
            ))

        LLMClient._instance = None

        # Patch _DECISIONS_LOG antes de que SimulationEngine cree el logger
        original_path = dl_module._DECISIONS_LOG
        original_logger = dl_module._logger
        dl_module._DECISIONS_LOG = log_file
        dl_module._logger = None

        try:
            with patch.dict("os.environ", {"LOG_DECISIONS": "true",
                                           "ANTHROPIC_API_KEY": "test-key"}):
                engine = SimulationEngine(env=env, no_llm=True)
                asyncio.run(engine.run(cycles=3))
        finally:
            dl_module._DECISIONS_LOG = original_path
            dl_module._logger = original_logger

        assert log_file.exists(), "El CSV debe existir tras la run"
        with open(log_file) as f:
            rows = list(csv.DictReader(f))
        # 3 agentes × 3 ciclos = 9 filas mínimo
        assert len(rows) >= 9, f"Se esperaban ≥9 filas, hay {len(rows)}"
