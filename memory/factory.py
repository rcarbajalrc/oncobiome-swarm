from __future__ import annotations

import logging
import os

from .base_store import MemoryStore

logger = logging.getLogger(__name__)


class MemoryFactory:
    @staticmethod
    def create(mem0_api_key: str = "") -> MemoryStore:
        """Crea el store apropiado según configuración.

        MEMORY_MODE env var controla el store:
            null     → NullMemoryStore (ablation study — sin memoria)
            mem0     → Mem0Store (si api_key disponible, else fallback)
            <vacío>  → InMemoryStore (default)
        """
        memory_mode = os.getenv("MEMORY_MODE", "").lower().strip()

        # ── Ablation study: memoria desactivada ───────────────────────────
        if memory_mode == "null":
            from .null_store import NullMemoryStore
            logger.info("ABLATION MODE: NullMemoryStore — memoria desactivada.")
            return NullMemoryStore()

        # ── mem0 persistente (si api_key disponible) ──────────────────────
        if mem0_api_key:
            try:
                from .mem0_store import Mem0Store
                store = Mem0Store(api_key=mem0_api_key)
                logger.info("Usando Mem0Store (memoria persistente).")
                return store
            except Exception as exc:
                logger.warning("Mem0Store no disponible (%s). Usando InMemoryStore.", exc)

        # ── Default: memoria in-process ───────────────────────────────────
        from .inmemory_store import InMemoryStore
        logger.info("Usando InMemoryStore (memoria in-process).")
        return InMemoryStore()
