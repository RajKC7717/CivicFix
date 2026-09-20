"""Google Gemini provider via the REST API (no extra SDK dependency)."""

from __future__ import annotations

import json
from typing import Any

import httpx

from app.pipeline.llm.base import LLMProvider, LLMRequest, LLMUnavailable

_BASE = "https://generativelanguage.googleapis.com/v1beta/models"


def _strip_unsupported(schema: dict[str, Any]) -> dict[str, Any]:
    """Gemini rejects ``additionalProperties``; drop it recursively."""
    if not isinstance(schema, dict):
        return schema
    cleaned = {k: v for k, v in schema.items() if k != "additionalProperties"}
    if "properties" in cleaned:
        cleaned["properties"] = {
            k: _strip_unsupported(v) for k, v in cleaned["properties"].items()
        }
    if "items" in cleaned:
        cleaned["items"] = _strip_unsupported(cleaned["items"])
    return cleaned


class GeminiProvider(LLMProvider):
    key = "gemini"

    def extract(self, request: LLMRequest) -> dict[str, Any]:
        if not self.available:
            raise LLMUnavailable("GEMINI_API_KEY is not set")

        parts: list[dict[str, Any]] = []
        if request.image_b64 and request.image_media_type:
            parts.append(
                {"inline_data": {"mime_type": request.image_media_type, "data": request.image_b64}}
            )
        parts.append({"text": request.user})

        body = {
            "systemInstruction": {"parts": [{"text": request.system}]},
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseSchema": _strip_unsupported(request.schema),
                "maxOutputTokens": request.max_tokens,
                "temperature": 0.0,
            },
        }
        url = f"{_BASE}/{self.model}:generateContent"
        try:
            response = httpx.post(
                url,
                params={"key": self.api_key},
                json=body,
                timeout=request.timeout,
            )
            response.raise_for_status()
            payload = response.json()
            text = payload["candidates"][0]["content"]["parts"][0]["text"]
            return json.loads(text)
        except Exception as exc:  # noqa: BLE001
            raise LLMUnavailable(f"Gemini call failed: {exc}") from exc
