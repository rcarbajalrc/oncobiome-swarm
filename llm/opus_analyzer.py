"""Análisis emergente del enjambre completo con Claude Opus.

Cada OPUS_INTERVAL ciclos, Opus recibe el SwarmSnapshot y analiza:
- Patrones emergentes observados
- Balance inmune vs tumor
- Predicción para los próximos ciclos
- Puntos de inflexión detectados
"""
from __future__ import annotations

import logging

from llm.client import LLMClient, LLMError
from models.swarm_snapshot import SwarmSnapshot

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "Expert oncologist analyzing KRAS_G12D TME multi-agent simulation (MiroFish paradigm). "
    "Write 3 sentences only: (1) tumor vs immunity balance + emergent patterns, "
    "(2) cytokine profile interpretation, (3) prediction next 25 cycles + one non-obvious insight. "
    "Clinical language. No headers. No lists."
)


class OpusAnalyzer:
    def __init__(self, llm_client: LLMClient) -> None:
        self._client = llm_client

    async def analyze(self, snapshot: SwarmSnapshot) -> str:
        # call_opus acepta un único 'prompt' str — concatenamos system + user
        combined_prompt = f"{_SYSTEM_PROMPT}\n\n{snapshot.to_prompt_text()}"
        try:
            analysis = await self._client.call_opus(prompt=combined_prompt)
            logger.info("Análisis Opus (ciclo %d): %d chars", snapshot.cycle, len(analysis))
            return analysis
        except LLMError as exc:
            logger.error("OpusAnalyzer falló en ciclo %d: %s", snapshot.cycle, exc)
            return f"[Análisis no disponible en ciclo {snapshot.cycle}: {exc}]"
