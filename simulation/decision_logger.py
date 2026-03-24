"""DecisionLogger — registra decisiones de agentes por ciclo en CSV.

Permite analizar la calidad de decisiones sin lanzar más runs.
El CSV se escribe en logs/decisions.csv y se puede abrir en Excel.

Columnas:
    run_id, cycle, agent_id, agent_type, action, signal_type,
    reasoning, confidence, energy, age, nearby_count,
    il6, vegf, ifng, kills_count, polarization

USO: se activa automáticamente cuando LOG_DECISIONS=true en .env

SECURITY: reasoning se sanitiza (strip de comas y saltos de línea) y se usa
QUOTE_ALL para prevenir CSV injection desde respuestas LLM inesperadas.
"""
from __future__ import annotations

import csv
import os
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from models.agent_state import AgentDecision, AgentState, LocalContext

_PROJECT_DIR = Path(__file__).parent.parent
_DECISIONS_LOG = _PROJECT_DIR / "logs" / "decisions.csv"

_FIELDNAMES = [
    "run_id", "cycle", "agent_id", "agent_type",
    "action", "signal_type", "reasoning", "confidence",
    "energy", "age", "nearby_count",
    "il6", "vegf", "ifng",
    "kills_count", "polarization",
]


def _sanitize(text: str, max_len: int = 40) -> str:
    """Elimina caracteres que podrían corromper el CSV."""
    return text.replace(",", " ").replace("\n", " ").replace("\r", " ")[:max_len]


class DecisionLogger:
    """Escribe decisiones de agentes en CSV para análisis post-run."""

    def __init__(self, enabled: bool = False) -> None:
        self._enabled = enabled
        self._run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._file = None
        self._writer = None

        if self._enabled:
            _DECISIONS_LOG.parent.mkdir(parents=True, exist_ok=True)
            file_exists = _DECISIONS_LOG.exists()
            self._file = open(_DECISIONS_LOG, "a", newline="", encoding="utf-8")
            # QUOTE_ALL previene CSV injection desde contenido LLM arbitrario
            self._writer = csv.DictWriter(
                self._file,
                fieldnames=_FIELDNAMES,
                quoting=csv.QUOTE_ALL,
            )
            if not file_exists:
                self._writer.writeheader()

    def log(
        self,
        cycle: int,
        agent_id: str,
        agent_type: str,
        decision: "AgentDecision",
        ctx: "LocalContext",
    ) -> None:
        if not self._enabled or self._writer is None:
            return

        self._writer.writerow({
            "run_id":       self._run_id,
            "cycle":        cycle,
            "agent_id":     agent_id[:8],
            "agent_type":   agent_type,
            "action":       decision.action.value,
            "signal_type":  decision.signal_type or "",
            "reasoning":    _sanitize(decision.reasoning or ""),
            "confidence":   round(decision.confidence, 3),
            "energy":       round(ctx.energy, 3),
            "age":          ctx.age,
            "nearby_count": len(ctx.nearby_agents),
            "il6":          round(ctx.cytokine_levels.get("IL-6", 0.0), 4),
            "vegf":         round(ctx.cytokine_levels.get("VEGF", 0.0), 4),
            "ifng":         round(ctx.cytokine_levels.get("IFN-γ", 0.0), 4),
            "kills_count":  ctx.metadata.get("kills_count", 0),
            "polarization": ctx.metadata.get("polarization", ""),
        })

    def flush(self) -> None:
        if self._file:
            self._file.flush()

    def close(self) -> None:
        if self._file:
            self._file.close()
            self._file = None
            self._writer = None


# Singleton global — se inicializa en engine.py
_logger: DecisionLogger | None = None


def get_decision_logger() -> DecisionLogger:
    global _logger
    if _logger is None:
        enabled = os.getenv("LOG_DECISIONS", "false").lower() == "true"
        _logger = DecisionLogger(enabled=enabled)
    return _logger


def reset_logger() -> None:
    """Resetea el logger entre runs."""
    global _logger
    if _logger:
        _logger.close()
    _logger = None
