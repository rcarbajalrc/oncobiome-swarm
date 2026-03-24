from __future__ import annotations

import logging

from .base_store import MemoryStore

logger = logging.getLogger(__name__)


class Mem0Store(MemoryStore):
    """Memoria persistente usando la API de mem0.

    Se inicializa sólo si MEM0_API_KEY está disponible.
    Cualquier fallo de API se loguea y se maneja silenciosamente
    para no interrumpir la simulación.
    """

    def __init__(self, api_key: str) -> None:
        try:
            from mem0 import MemoryClient

            self._client = MemoryClient(api_key=api_key)
            logger.info("Mem0Store inicializado correctamente.")
        except ImportError as e:
            raise RuntimeError("mem0ai no está instalado. Ejecuta: pip install mem0ai") from e

    def add(self, content: str, user_id: str) -> None:
        try:
            messages = [{"role": "user", "content": content}]
            self._client.add(messages, user_id=user_id)
        except Exception as exc:
            logger.warning("mem0.add falló para %s: %s", user_id, exc)

    def get_recent(self, user_id: str, limit: int = 5) -> list[str]:
        try:
            results = self._client.get_all(user_id=user_id)
            memories = [r.get("memory", str(r)) for r in (results or [])]
            return memories[-limit:]
        except Exception as exc:
            logger.warning("mem0.get_all falló para %s: %s", user_id, exc)
            return []

    def search(self, query: str, user_id: str, limit: int = 3) -> list[str]:
        try:
            results = self._client.search(query, user_id=user_id, limit=limit)
            return [r.get("memory", str(r)) for r in (results or [])]
        except Exception as exc:
            logger.warning("mem0.search falló para %s: %s", user_id, exc)
            return []
