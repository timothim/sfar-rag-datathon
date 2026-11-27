"""Run-time generator (transport) settings for the demo chatbot.

The demo page lets the operator point the served pipeline at any OpenAI-compatible endpoint
(base URL, model, optional API key). Only the transport changes: the prompt, the context and the
call options come from the `PRODUCTION` serving profile and are built by the engine as before.
Optional overrides of the token cap and temperature are kept as explicit, displayed deviations
from the evaluated profile (default: none).

The API key lives only in server memory: no endpoint returns it, it is never logged, and error
messages returned to the page are reduced to the exception class and HTTP status (provider error
bodies can echo part of a key).
"""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from typing import Any

from rag_sfar.generation.client import OpenAICompatibleLLM

LOCK_ENV = "RAG_SFAR_DEMO_LOCK_SETTINGS"


def settings_locked() -> bool:
    """True when the deployment forbids changing the generator from the page."""
    return os.environ.get(LOCK_ENV, "").strip().lower() in {"1", "true", "yes", "on"}


def safe_error(exc: BaseException) -> str:
    """Error description safe to show on the page: class name and HTTP status only."""
    status = getattr(exc, "status_code", None)
    name = type(exc).__name__
    return f"{name} (HTTP {status})" if status else name


class RuntimeOpenAILLM(OpenAICompatibleLLM):
    """OpenAI-compatible client with optional transport-level overrides.

    `send_thinking_flag=False` drops `chat_template_kwargs` for servers that reject unknown
    fields; by default the client sends `enable_thinking=False` as in the evaluation."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        timeout: float = 120.0,
        max_tokens_override: int | None = None,
        temperature_override: float | None = None,
        send_thinking_flag: bool = True,
    ) -> None:
        super().__init__(base_url=base_url, api_key=api_key, model=model, timeout=timeout)
        # One quick retry only: an unreachable endpoint must fall back to passages fast.
        self._client = self._client.with_options(max_retries=1)
        self.max_tokens_override = max_tokens_override
        self.temperature_override = temperature_override
        self.send_thinking_flag = send_thinking_flag
        # Answer calls already carry enable_thinking=False from the profile; this default makes
        # the question-normalisation call (robustness option, no option of its own) thinking-free
        # too, so that its 200-token budget is not spent on reasoning.
        if send_thinking_flag:
            self.options["enable_thinking"] = False

    def _request_kwargs(self, temperature, max_tokens, opts: dict[str, Any]) -> dict[str, Any]:
        kw = super()._request_kwargs(temperature, max_tokens, opts)
        # The token-cap override targets answers; short auxiliary calls (normalisation: 200
        # tokens) keep their own cap.
        if self.max_tokens_override and (max_tokens is None or max_tokens > 200):
            kw["max_tokens"] = int(self.max_tokens_override)
        if self.temperature_override is not None:
            kw["temperature"] = float(self.temperature_override)
        if not self.send_thinking_flag and "extra_body" in kw:
            kw["extra_body"].pop("chat_template_kwargs", None)
            if not kw["extra_body"]:
                kw.pop("extra_body")
        return kw


@dataclass
class GeneratorSettings:
    base_url: str
    model: str
    api_key: str = ""
    max_tokens_override: int | None = None
    temperature_override: float | None = None
    send_thinking_flag: bool = True

    def public(self) -> dict[str, Any]:
        """Everything except the key (only whether one is set)."""
        return {
            "base_url": self.base_url,
            "model": self.model,
            "api_key_set": bool(self.api_key),
            "max_tokens_override": self.max_tokens_override,
            "temperature_override": self.temperature_override,
            "send_thinking_flag": self.send_thinking_flag,
        }

    def build(self, timeout: float) -> RuntimeOpenAILLM:
        return RuntimeOpenAILLM(
            base_url=self.base_url, api_key=self.api_key, model=self.model, timeout=timeout,
            max_tokens_override=self.max_tokens_override,
            temperature_override=self.temperature_override,
            send_thinking_flag=self.send_thinking_flag,
        )


def list_models(base_url: str, api_key: str, timeout: float = 8.0) -> dict[str, Any]:
    """Call `<base_url>/models`; returns {ok, models} or {ok: False, error} (sanitized)."""
    from openai import OpenAI

    try:
        client = OpenAI(base_url=base_url, api_key=api_key or "none", timeout=timeout, max_retries=0)
        models = sorted(m.id for m in client.models.list())
        return {"ok": True, "models": models}
    except Exception as exc:  # noqa: BLE001 - every failure is reported, sanitized
        return {"ok": False, "models": [], "error": safe_error(exc)}


class GeneratorState:
    """Current generator settings of the app, swapped atomically into the engine."""

    def __init__(self, settings: GeneratorSettings | None, timeout: float) -> None:
        self.settings = settings
        self.timeout = timeout
        self.lock = threading.Lock()
        self.last_status: dict[str, Any] = {"state": "unknown"}

    def apply(self, engine, new: GeneratorSettings) -> None:
        llm = new.build(self.timeout)
        with self.lock:
            self.settings = new
            engine.llm = llm
            self.last_status = {"state": "unknown"}
