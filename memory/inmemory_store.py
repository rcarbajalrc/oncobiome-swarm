from __future__ import annotations

from collections import defaultdict, deque

from .base_store import MemoryStore

_MAX_ENTRIES = 50  # entradas por agente


class InMemoryStore(MemoryStore):
    """Memoria in-memory como fallback cuando mem0 no está disponible.

    Usa una deque circular de capacidad fija por agente.
    La búsqueda es por substring (case-insensitive).
    """

    def __init__(self) -> None:
        self._store: dict[str, deque[str]] = defaultdict(lambda: deque(maxlen=_MAX_ENTRIES))

    def add(self, content: str, user_id: str) -> None:
        self._store[user_id].append(content)

    def get_recent(self, user_id: str, limit: int = 5) -> list[str]:
        entries = list(self._store[user_id])
        return entries[-limit:] if entries else []

    def search(self, query: str, user_id: str, limit: int = 3) -> list[str]:
        entries = list(self._store[user_id])
        query_lower = query.lower()
        matches = [e for e in entries if query_lower in e.lower()]
        # Devuelve los más recientes primero
        return matches[-limit:][::-1] if matches else self.get_recent(user_id, limit)
