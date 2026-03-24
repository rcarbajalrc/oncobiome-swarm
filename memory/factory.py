from __future__ import annotations

import logging

from .base_store import MemoryStore

logger = logging.getLogger(__name__)


class MemoryFactory:
    @staticmethod
    def create(mem0_api_key: str = "") -> MemoryStore:
        """Crea el store apropiado según disponibilidad de mem0."""
        if mem0_api_key:
            try:
                from .mem0_store import Mem0Store

                store = Mem0Store(api_key=mem0_api_key)
                logger.info("Usando Mem0Store (memoria persistente).")
                return store
            except Exception as exc:
                logger.warning("Mem0Store no disponible (%s). Usando InMemoryStore.", exc)

        from .inmemory_store import InMemoryStore

        logger.info("Usando InMemoryStore (memoria in-process).")
        return InMemoryStore()
