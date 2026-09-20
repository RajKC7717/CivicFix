"""The default provider: there isn't one.

``LLM_PROVIDER=none`` is a first-class, fully supported configuration, not a
degraded mode. This class exists so the rest of the code has exactly one path.
"""

from __future__ import annotations

from typing import Any

from app.pipeline.llm.base import LLMProvider, LLMRequest, LLMUnavailable


class NoneProvider(LLMProvider):
    key = "none"

    @property
    def available(self) -> bool:
        return False

    def extract(self, request: LLMRequest) -> dict[str, Any]:
        raise LLMUnavailable("No LLM provider configured (LLM_PROVIDER=none)")

    def describe(self) -> str:
        return "offline"
