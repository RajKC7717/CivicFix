"""The contract every understanding backend must satisfy.

The LLM path and the offline path produce the *same* validated object, so the
rest of the pipeline never branches on which one ran. Only ``source`` and
``model`` differ, and those are surfaced to the citizen and the officer so the
provenance of every field is visible.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.config.categories import CATEGORY_KEYS, HAZARD_KEYS, LANGUAGES


class Understanding(BaseModel):
    """Structured reading of one complaint. This is the LLM's required JSON schema."""

    category: str = Field(description="One of the fixed NagarNetra category keys")
    sub_issue: str = Field(default="", max_length=120)
    severity_1to5: int = Field(default=3, ge=1, le=5)
    hazard_flags: list[str] = Field(default_factory=list)
    location_text: str = Field(default="", max_length=300)
    landmarks: list[str] = Field(default_factory=list)
    language: str = Field(default="unknown")
    summary_en: str = Field(default="", max_length=400)
    confidence_0to1: float = Field(default=0.0, ge=0.0, le=1.0)

    # --- provenance (never asked of the model; set by the pipeline) ---
    source: Literal["llm", "offline_classifier", "officer", "unresolved"] = "offline_classifier"
    model: str = ""
    explanation: str = ""
    matched_terms: list[str] = Field(default_factory=list)
    #: Similarity key for deduplication. Never shown to anyone; see
    #: ``lexicon.build_match_text`` for why it differs from ``summary_en``.
    match_text: str = ""

    @field_validator("category")
    @classmethod
    def _known_category(cls, value: str) -> str:
        cleaned = (value or "").strip().lower().replace(" ", "_").replace("-", "_")
        if cleaned not in CATEGORY_KEYS:
            raise ValueError(f"unknown category {value!r}")
        return cleaned

    @field_validator("hazard_flags")
    @classmethod
    def _known_hazards(cls, value: list[str]) -> list[str]:
        """Silently drop hazards outside the taxonomy rather than reject the read.

        A model inventing 'traffic_jam' should not cost the citizen their whole
        classification - we keep the valid flags and move on.
        """
        cleaned: list[str] = []
        for flag in value or []:
            key = str(flag).strip().lower().replace(" ", "_").replace("-", "_")
            if key in HAZARD_KEYS and key not in cleaned:
                cleaned.append(key)
        return cleaned

    @field_validator("language")
    @classmethod
    def _known_language(cls, value: str) -> str:
        cleaned = (value or "unknown").strip().lower()
        aliases = {
            "english": "en", "hindi": "hi", "marathi": "mr",
            "en-in": "en", "hi-in": "hi", "mr-in": "mr",
            "romanised_hindi": "hinglish", "hinglish": "hinglish",
        }
        cleaned = aliases.get(cleaned, cleaned)
        return cleaned if cleaned in LANGUAGES else "unknown"

    @field_validator("landmarks")
    @classmethod
    def _trim_landmarks(cls, value: list[str]) -> list[str]:
        return [str(v).strip()[:80] for v in (value or []) if str(v).strip()][:6]


#: The JSON Schema handed to the LLM. Generated from the model so the prompt can
#: never drift away from what Pydantic will actually accept.
LLM_RESPONSE_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "category": {"type": "string", "enum": list(CATEGORY_KEYS)},
        "sub_issue": {"type": "string", "description": "Short specific phrase, English"},
        "severity_1to5": {"type": "integer", "minimum": 1, "maximum": 5},
        "hazard_flags": {
            "type": "array",
            "items": {"type": "string", "enum": list(HAZARD_KEYS)},
        },
        "location_text": {"type": "string", "description": "Location exactly as written"},
        "landmarks": {"type": "array", "items": {"type": "string"}},
        "language": {"type": "string", "enum": ["en", "hi", "mr", "hinglish", "unknown"]},
        "summary_en": {
            "type": "string",
            "description": "One neutral English sentence. Always English regardless of input.",
        },
        "confidence_0to1": {"type": "number", "minimum": 0, "maximum": 1},
    },
    "required": [
        "category",
        "severity_1to5",
        "hazard_flags",
        "language",
        "summary_en",
        "confidence_0to1",
    ],
    "additionalProperties": False,
}
