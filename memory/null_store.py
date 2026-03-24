"""NullMemoryStore — memoria desactivada para ablation study.

Propósito científico:
    Responde a la crítica del revisor: "¿los fenómenos emergentes dependen
    de la memoria episódica o son robustos sin ella?"

    Si los fenómenos persisten con NullMemoryStore → son robustos.
    Si desaparecen → la memoria era el mecanismo real (también interesante).

Uso:
    Activado automáticamente cuando MEMORY_MODE=null en .env,
    o via --experiment ablation_no_memory*.
"""
from __future__ import annotations

from .base_store import MemoryStore


class NullMemoryStore(MemoryStore):
    """Store que descarta toda la memoria — equivale a agentes sin historia."""

    def add(self, content: str, user_id: str) -> None:
        pass  # descarta silenciosamente

    def get_recent(self, user_id: str, limit: int = 5) -> list[str]:
        return []  # siempre vacío

    def search(self, query: str, user_id: str, limit: int = 3) -> list[str]:
        return []  # siempre vacío
