"""Claude provider. Uses tool-calling so the JSON is schema-valid by construction.

Asking a model to "reply with JSON" and hoping is a common source of demo-day
failure. Forcing a single tool call whose ``input_schema`` *is* our schema means
the provider itself rejects a malformed answer before we ever see it.
"""

from __future__ import annotations

from typing import Any

from app.pipeline.llm.base import LLMProvider, LLMRequest, LLMUnavailable


class AnthropicProvider(LLMProvider):
    key = "anthropic"

    def extract(self, request: LLMRequest) -> dict[str, Any]:
        if not self.available:
            raise LLMUnavailable("ANTHROPIC_API_KEY is not set")
        try:
            import anthropic
        except ImportError as exc:  # pragma: no cover
            raise LLMUnavailable("anthropic SDK not installed") from exc

        content: list[dict[str, Any]] = []
        if request.image_b64 and request.image_media_type:
            content.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": request.image_media_type,
                        "data": request.image_b64,
                    },
                }
            )
        content.append({"type": "text", "text": request.user})

        try:
            client = anthropic.Anthropic(api_key=self.api_key, timeout=request.timeout)
            message = client.messages.create(
                model=self.model,
                max_tokens=request.max_tokens,
                system=request.system,
                tools=[
                    {
                        "name": request.tool_name,
                        "description": request.tool_description,
                        "input_schema": request.schema,
                    }
                ],
                tool_choice={"type": "tool", "name": request.tool_name},
                messages=[{"role": "user", "content": content}],
            )
        except Exception as exc:  # noqa: BLE001 - network, auth, rate limit, overload
            raise LLMUnavailable(f"Claude call failed: {exc}") from exc

        for block in message.content:
            if getattr(block, "type", None) == "tool_use":
                payload = getattr(block, "input", None)
                if isinstance(payload, dict):
                    return payload
        raise LLMUnavailable("Claude returned no tool_use block")
