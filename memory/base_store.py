from __future__ import annotations

from abc import ABC, abstractmethod


class MemoryStore(ABC):
    """Interfaz de memoria persistente por agente.

    Todas las operaciones son síncronas. El wrapping async se realiza
    en BaseAgent mediante asyncio.to_thread().
    """

    @abstractmethod
    def add(self, content: str, user_id: str) -> None:
        """Almacena una entrada de memoria para el agente."""

    @abstractmethod
    def get_recent(self, user_id: str, limit: int = 5) -> list[str]:
        """Retorna las últimas `limit` entradas de memoria del agente."""

    @abstractmethod
    def search(self, query: str, user_id: str, limit: int = 3) -> list[str]:
        """Busca entradas de memoria relevantes para una consulta."""
