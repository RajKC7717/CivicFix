"""LLM provider interface and registry.

Every provider takes the same request (system prompt, redacted user text, a JSON
schema, optionally an image) and returns a plain ``dict`` that the caller
validates with Pydantic. Providers never see raw citizen text - only the
redacted copy produced by :mod:`app.pipeline.redact`.

A provider that cannot answer raises :class:`LLMUnavailable`. It is the caller's
job to fall back to the offline classifier, and it always does.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


class LLMUnavailable(Exception):
    """No usable answer from the provider: not configured, timed out, or malformed."""


@dataclass
class LLMRequest:
    """One structured-extraction call."""

    system: str
    user: str
    schema: dict[str, Any]
    tool_name: str = "record_complaint"
    tool_description: str = "Record the structured reading of a civic complaint."
    image_b64: str | None = None
    image_media_type: str | None = None
    max_tokens: int = 1024
    timeout: float = 20.0
    extra: dict[str, Any] = field(default_factory=dict)


class LLMProvider(ABC):
    """Base class for every provider."""

    key: str = "none"

    def __init__(self, api_key: str | None, model: str) -> None:
        self.api_key = api_key
        self.model = model

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    @abstractmethod
    def extract(self, request: LLMRequest) -> dict[str, Any]:
        """Return parsed JSON matching ``request.schema`` or raise LLMUnavailable."""

    def describe(self) -> str:
        return f"{self.key}:{self.model}"


def get_provider() -> LLMProvider:
    """Build the provider named by ``LLM_PROVIDER``.

    Import of a provider module is deferred so that a missing optional SDK can
    never break startup - it simply degrades to the offline path.
    """
    from app.config.settings import settings

    choice = settings.llm_provider
    try:
        if choice == "anthropic":
            from app.pipeline.llm.anthropic_provider import AnthropicProvider

            return AnthropicProvider(settings.anthropic_api_key, settings.anthropic_model)
        if choice == "gemini":
            from app.pipeline.llm.gemini_provider import GeminiProvider

            return GeminiProvider(settings.gemini_api_key, settings.gemini_model)
        if choice == "openai":
            from app.pipeline.llm.openai_provider import OpenAIProvider

            return OpenAIProvider(settings.openai_api_key, settings.openai_model)
    except Exception:  # noqa: BLE001 - any import/construction failure -> offline
        from app.pipeline.llm.none_provider import NoneProvider

        return NoneProvider(None, "")

    from app.pipeline.llm.none_provider import NoneProvider

    return NoneProvider(None, "")
