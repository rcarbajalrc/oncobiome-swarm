"""Cliente LLM centralizado con soporte Anthropic API y Ollama local.

Arquitectura híbrida:
  - Agentes (call_haiku / call_haiku_batch) → Ollama o Anthropic según provider
  - Análisis emergente (call_opus) → SIEMPRE Anthropic API

SMART BATCHING:
  call_haiku_batch() agrupa N agentes del mismo tipo en una sola llamada LLM.
  Si el batch falla o el parse no devuelve N respuestas exactas, lanza BatchError.
  El engine captura BatchError y aplica rule engine como fallback — NUNCA llamadas
  individuales. Esto garantiza coste controlado bajo cualquier condición de fallo.

SECURITY FIXES:
  - _parse_batch_response: límite de 100KB antes de json.loads (OOM prevention)
  - _OllamaClient: verify_ssl=True por defecto, desactivable via OLLAMA_VERIFY_SSL=false
"""
from __future__ import annotations

import asyncio
import collections
import json
import logging
import os
import re
import time
from typing import Any

import anthropic
import httpx

from config import get_config

logger = logging.getLogger(__name__)

# Límite de tamaño de respuesta LLM antes de intentar parse JSON
# Previene OOM ante respuestas inesperadamente largas
_MAX_RESPONSE_BYTES = 100_000


class LLMError(Exception):
    pass


class BatchError(LLMError):
    """Error específico de batch — el engine lo captura y aplica rule engine."""
    pass


class _SlidingWindowRateLimiter:
    def __init__(self, max_calls: int, window_seconds: float) -> None:
        self._max = max_calls
        self._window = window_seconds
        self._timestamps: collections.deque[float] = collections.deque()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        if self._max <= 0:
            return
        async with self._lock:
            while True:
                now = time.monotonic()
                while self._timestamps and now - self._timestamps[0] > self._window:
                    self._timestamps.popleft()
                if len(self._timestamps) < self._max:
                    self._timestamps.append(now)
                    return
                wait = self._window - (now - self._timestamps[0]) + 0.01
                await asyncio.sleep(wait)


class _OllamaClient:
    def __init__(self, base_url: str, model: str, max_retries: int) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._max_retries = max_retries
        # SECURITY: verificar SSL por defecto para conexiones HTTPS.
        # Solo desactivar si OLLAMA_VERIFY_SSL=false en .env (desarrollo local).
        verify_ssl = os.getenv("OLLAMA_VERIFY_SSL", "true").lower() != "false"
        self._http = httpx.AsyncClient(timeout=120.0, verify=verify_ssl)

    async def generate(self, system: str, user: str, max_tokens: int) -> str:
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
            "options": {"num_predict": max_tokens, "temperature": 0.1},
        }
        for attempt in range(1, self._max_retries + 1):
            try:
                resp = await self._http.post(f"{self._base_url}/api/chat", json=payload)
                resp.raise_for_status()
                return resp.json()["message"]["content"]
            except httpx.ConnectError as exc:
                raise LLMError(f"No se puede conectar a Ollama en {self._base_url}.") from exc
            except Exception as exc:
                if attempt == self._max_retries:
                    raise LLMError(f"Ollama error: {exc}") from exc
                await asyncio.sleep(1)
        raise LLMError("Ollama agotó reintentos")

    async def aclose(self) -> None:
        await self._http.aclose()


class LLMClient:
    _instance: "LLMClient | None" = None

    def __new__(cls) -> "LLMClient":
        # Sprint 7A: resetear singleton si AGENT_MODEL cambió (multi-LLM support)
        current_agent_model = os.environ.get("AGENT_MODEL", "")
        if cls._instance is not None and hasattr(cls._instance, "_agent_model"):
            if cls._instance._agent_model != current_agent_model and current_agent_model:
                cls._instance = None  # forzar reinicialización
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        cfg = get_config()

        self._anthropic = anthropic.AsyncAnthropic(api_key=cfg.anthropic_api_key)

        self._use_ollama = cfg.use_ollama
        if self._use_ollama:
            self._ollama = _OllamaClient(
                base_url=cfg.ollama_base_url,
                model=cfg.ollama_agent_model,
                max_retries=cfg.llm_max_retries,
            )
            concurrency = min(cfg.llm_concurrency * 2, 8)
        else:
            self._ollama = None
            concurrency = cfg.llm_concurrency

        self._semaphore = asyncio.Semaphore(concurrency)
        rps_max = 0 if self._use_ollama else cfg.llm_rps_max
        self._rate_limiter = _SlidingWindowRateLimiter(
            max_calls=rps_max,
            window_seconds=cfg.llm_rps_window,
        )
        self._inter_call_delay: float = 0.0 if self._use_ollama else cfg.llm_inter_call_delay
        self._max_retries = cfg.llm_max_retries
        self._haiku_model = cfg.haiku_model
        self._opus_model = cfg.opus_model
        # Sprint 7A: modelo de agente configurable (haiku o sonnet según experimento)
        # Sprint 7A: agent_model se lee en cada llamada para soportar cambios de entorno
        self._agent_model = os.environ.get("AGENT_MODEL", cfg.haiku_model)
        self._haiku_max_tokens = min(cfg.haiku_max_tokens, 50)
        self._opus_max_tokens = cfg.opus_max_tokens
        self._cycle_tokens: dict = {
            "input": 0, "output": 0, "calls": 0,
            "cache_hits": 0, "cache_writes": 0,
            "batch_fallbacks": 0,
            "llm_decisions": 0,
            "rule_engine_decisions": 0,
        }
        self._initialized = True

        logger.debug(
            "LLMClient init: provider=%s haiku=%s max_tokens=%d opus=%s batching=ON",
            "ollama" if self._use_ollama else "anthropic",
            self._haiku_model, self._haiku_max_tokens, self._opus_model,
        )

    def provider_info(self) -> str:
        if self._use_ollama:
            return f"ollama/{self._ollama._model}"
        return f"anthropic/{self._agent_model}"

    # ── API pública ────────────────────────────────────────────────────────

    async def call_haiku(self, system: str, user: str, max_tokens: int | None = None) -> str:
        mt = min(max_tokens or self._haiku_max_tokens, self._haiku_max_tokens)
        if self._use_ollama:
            return await self._call_ollama(system=system, user=user, max_tokens=mt)
        # Sprint 7A: leer en tiempo de ejecución para soportar multi-LLM
        runtime_model = os.environ.get("AGENT_MODEL", self._agent_model)
        return await self._call_anthropic_cached(
            model=runtime_model, system=system, user=user, max_tokens=mt
        )

    async def call_haiku_batch(
        self, system: str, user_prompts: list[str], max_tokens_per_agent: int = 50
    ) -> list[str]:
        """SMART BATCHING: N agentes → 1 llamada LLM → N respuestas JSON."""
        if not user_prompts:
            return []

        if len(user_prompts) == 1:
            result = await self.call_haiku(system=system, user=user_prompts[0])
            return [result]

        n = len(user_prompts)
        batch_user = f"Respond with a JSON array of exactly {n} decisions, one per agent.\n\n"
        for i, up in enumerate(user_prompts):
            batch_user += f"AGENT_{i}:\n{up}\n\n"
        batch_user += f"Return ONLY a JSON array with exactly {n} objects. No explanation."

        batch_max_tokens = min(n * max_tokens_per_agent, 4096)

        if self._use_ollama:
            raw = await self._call_ollama(system=system, user=batch_user, max_tokens=batch_max_tokens)
        else:
            runtime_model = os.environ.get("AGENT_MODEL", self._agent_model)
            raw = await self._call_anthropic_cached(
                model=runtime_model,
                system=system,
                user=batch_user,
                max_tokens=batch_max_tokens,
            )

        results = self._parse_batch_response(raw, expected_count=n)
        if results is None:
            self._cycle_tokens["batch_fallbacks"] += 1
            logger.warning(
                "Batch parse falló para %d agentes — BatchError → rule engine ($0)", n
            )
            raise BatchError(f"Batch parse falló: respuesta no tiene {n} elementos JSON")

        logger.debug("Batch OK: %d agentes → 1 llamada", n)
        return results

    def _parse_batch_response(self, raw: str, expected_count: int) -> list[str] | None:
        # SECURITY: límite de tamaño antes de json.loads — previene OOM
        if len(raw) > _MAX_RESPONSE_BYTES:
            logger.warning(
                "Respuesta LLM demasiado grande (%d bytes > %d) — descartada",
                len(raw), _MAX_RESPONSE_BYTES,
            )
            return None

        text = raw.strip()
        try:
            arr = json.loads(text)
            if isinstance(arr, list) and len(arr) == expected_count:
                return [json.dumps(item) for item in arr]
        except json.JSONDecodeError:
            pass

        # Fallback: buscar array JSON dentro del texto
        m = re.search(r"\[.*\]", text, re.DOTALL)
        if m:
            try:
                arr = json.loads(m.group())
                if isinstance(arr, list) and len(arr) == expected_count:
                    return [json.dumps(item) for item in arr]
            except json.JSONDecodeError:
                pass

        return None

    async def call_opus(self, prompt: str) -> str:
        """Análisis emergente — siempre Anthropic, nunca Ollama."""
        async with self._semaphore:
            await self._rate_limiter.acquire()
            for attempt in range(1, self._max_retries + 1):
                try:
                    msg = await self._anthropic.messages.create(
                        model=self._opus_model,
                        max_tokens=self._opus_max_tokens,
                        messages=[{"role": "user", "content": prompt}],
                    )
                    text = msg.content[0].text if msg.content else ""
                    self._cycle_tokens["input"]  += msg.usage.input_tokens
                    self._cycle_tokens["output"] += msg.usage.output_tokens
                    self._cycle_tokens["calls"]  += 1
                    return text
                except Exception as exc:
                    if attempt == self._max_retries:
                        raise LLMError(f"Opus error: {exc}") from exc
                    await asyncio.sleep(2 ** attempt)
        raise LLMError("Opus agotó reintentos")

    async def _call_anthropic_cached(
        self, model: str, system: str, user: str, max_tokens: int
    ) -> str:
        async with self._semaphore:
            await self._rate_limiter.acquire()
            if self._inter_call_delay > 0:
                await asyncio.sleep(self._inter_call_delay)
            for attempt in range(1, self._max_retries + 1):
                try:
                    msg = await self._anthropic.messages.create(
                        model=model,
                        max_tokens=max_tokens,
                        system=system,
                        messages=[{"role": "user", "content": user}],
                    )
                    text = msg.content[0].text if msg.content else ""
                    usage = msg.usage
                    self._cycle_tokens["input"]  += usage.input_tokens
                    self._cycle_tokens["output"] += usage.output_tokens
                    self._cycle_tokens["calls"]  += 1
                    if hasattr(usage, "cache_read_input_tokens"):
                        self._cycle_tokens["cache_hits"] += usage.cache_read_input_tokens or 0
                    if hasattr(usage, "cache_creation_input_tokens"):
                        self._cycle_tokens["cache_writes"] += usage.cache_creation_input_tokens or 0
                    return text
                except anthropic.RateLimitError:
                    wait = 2 ** attempt
                    logger.warning("Rate limit hit — esperando %ds (intento %d)", wait, attempt)
                    await asyncio.sleep(wait)
                except anthropic.APIError as exc:
                    if attempt == self._max_retries:
                        raise LLMError(f"Anthropic API error: {exc}") from exc
                    await asyncio.sleep(1)
        raise LLMError("Anthropic agotó reintentos")

    async def _call_ollama(self, system: str, user: str, max_tokens: int) -> str:
        if self._ollama is None:
            raise LLMError("Ollama no inicializado")
        async with self._semaphore:
            result = await self._ollama.generate(system=system, user=user, max_tokens=max_tokens)
            self._cycle_tokens["calls"] += 1
            return result

    def get_and_reset_cycle_stats(self) -> dict:
        stats = dict(self._cycle_tokens)
        total = stats.get("llm_decisions", 0) + stats.get("rule_engine_decisions", 0)
        stats["llm_pct"] = round(
            stats.get("llm_decisions", 0) / total * 100, 1
        ) if total > 0 else 0.0
        self._cycle_tokens = {k: 0 for k in self._cycle_tokens}
        return stats
