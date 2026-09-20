"""OpenAI provider via the REST API using strict structured outputs."""

from __future__ import annotations

import json
from typing import Any

import httpx

from app.pipeline.llm.base import LLMProvider, LLMRequest, LLMUnavailable

_URL = "https://api.openai.com/v1/chat/completions"


class OpenAIProvider(LLMProvider):
    key = "openai"

    def extract(self, request: LLMRequest) -> dict[str, Any]:
        if not self.available:
            raise LLMUnavailable("OPENAI_API_KEY is not set")

        content: list[dict[str, Any]] = [{"type": "text", "text": request.user}]
        if request.image_b64 and request.image_media_type:
            data_uri = f"data:{request.image_media_type};base64,{request.image_b64}"
            content.append({"type": "image_url", "image_url": {"url": data_uri}})

        body = {
            "model": self.model,
            "temperature": 0,
            "max_tokens": request.max_tokens,
            "messages": [
                {"role": "system", "content": request.system},
                {"role": "user", "content": content},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": request.tool_name,
                    "strict": True,
                    "schema": request.schema,
                },
            },
        }
        try:
            response = httpx.post(
                _URL,
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=body,
                timeout=request.timeout,
            )
            response.raise_for_status()
            text = response.json()["choices"][0]["message"]["content"]
            return json.loads(text)
        except Exception as exc:  # noqa: BLE001
            raise LLMUnavailable(f"OpenAI call failed: {exc}") from exc
