"""Understanding stage: redacted complaint text (+ optional photo) -> structured fields.

Order of attempts:

1. The configured LLM, forced to emit JSON matching :data:`LLM_RESPONSE_SCHEMA`.
   One retry with a corrective instruction if Pydantic rejects the first answer.
2. The offline classifier (:mod:`app.pipeline.fallback_clf`).

The second is not an error path - with ``LLM_PROVIDER=none`` it is the *only*
path, and the product is designed to be fully usable that way.

A small on-disk response cache keyed by the redacted text makes repeat runs of
the scripted demo free and network-independent (``DEMO_MODE``).
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.config.categories import CATEGORY_KEYS, HAZARD_KEYS
from app.config.settings import DATA_DIR, settings
from app.pipeline import lexicon
from app.pipeline.fallback_clf import understand_offline
from app.pipeline.llm.base import LLMRequest, LLMUnavailable, get_provider
from app.pipeline.types import LLM_RESPONSE_SCHEMA, Understanding

logger = logging.getLogger(__name__)

CACHE_PATH = DATA_DIR / "llm_cache.json"
_cache_lock = threading.Lock()

SYSTEM_PROMPT = f"""You are the triage assistant for NagarNetra, a municipal grievance system in Pune, India.

You read one citizen complaint and extract structured fields. You do NOT decide priority, you do NOT reject complaints, and you do NOT talk to the citizen. A municipal officer makes every decision; your output is evidence for them.

Rules:
- The complaint may be in English, Hindi (Devanagari), Marathi (Devanagari) or romanised Hinglish. Handle all of them.
- `category` MUST be exactly one of: {', '.join(CATEGORY_KEYS)}.
- `hazard_flags` may only contain: {', '.join(HAZARD_KEYS)}. Include a flag only if the complaint gives real evidence for it. An empty list is correct and normal.
- `summary_en` MUST be in English regardless of the input language, one neutral sentence, no speculation, no invented detail. It is used to detect that two complaints describe the same problem, so name the issue and the place plainly.
- `location_text` must quote the location as the citizen wrote it. Do not guess coordinates or invent a place.
- `severity_1to5`: 1 = cosmetic, 3 = normal civic problem, 5 = immediate danger to life.
- `confidence_0to1` is your own honest confidence in `category`. If the text is vague, say so with a LOW number. A low number sends the complaint to a human, which is the correct outcome - it is never penalised.
- Personal identifiers have already been replaced with tokens like [PHONE]. Ignore them.

Return only the structured record."""


def _user_prompt(text: str, location_hint: str = "", has_image: bool = False) -> str:
    parts = [f"Complaint text:\n{text or '(no text provided)'}"]
    if location_hint:
        parts.append(f"\nLocation supplied by the app: {location_hint}")
    if has_image:
        parts.append(
            "\nA photo is attached. Use it to confirm the category and to judge severity. "
            "Describe only what is visible."
        )
    return "\n".join(parts)


# ---------------------------------------------------------------------------
#  Response cache
# ---------------------------------------------------------------------------
def _cache_key(text: str, model: str, has_image: bool) -> str:
    raw = f"{model}|{int(has_image)}|{(text or '').strip().lower()}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _load_cache() -> dict[str, Any]:
    if not CACHE_PATH.exists():
        return {}
    try:
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _cache_get(key: str) -> dict[str, Any] | None:
    with _cache_lock:
        return _load_cache().get(key)


def _cache_put(key: str, payload: dict[str, Any]) -> None:
    with _cache_lock:
        cache = _load_cache()
        cache[key] = payload
        try:
            CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
            CACHE_PATH.write_text(
                json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8"
            )
        except OSError as exc:  # pragma: no cover - cache is best-effort
            logger.debug("Could not write LLM cache: %s", exc)


# ---------------------------------------------------------------------------
#  Merge lexicon evidence into an LLM reading
# ---------------------------------------------------------------------------
def _enrich(reading: Understanding, text: str) -> Understanding:
    """Fill gaps in an LLM reading from deterministic lexical evidence.

    Hazards are *unioned*, not overwritten. Missing a live wire because the
    model was terse is a safety failure; a spurious flag is a two-second
    dismissal for an officer. The explanation records which flags came from
    keywords so the officer can tell them apart.
    """
    analysis = lexicon.analyse(text or "")
    notes: list[str] = []

    if reading.language == "unknown" and analysis.language != "unknown":
        reading.language = analysis.language

    extra_hazards = [h for h in analysis.hazards if h not in reading.hazard_flags]
    if extra_hazards:
        reading.hazard_flags = [*reading.hazard_flags, *extra_hazards]
        notes.append("keyword-detected hazard: " + ", ".join(extra_hazards))

    for landmark in analysis.landmarks:
        if landmark not in reading.landmarks:
            reading.landmarks.append(landmark)

    if not reading.summary_en.strip():
        reading.summary_en = analysis.summary_en

    reading.matched_terms = analysis.matched_terms
    if notes:
        reading.explanation = "; ".join(filter(None, [reading.explanation, *notes]))
    return reading


# ---------------------------------------------------------------------------
#  Public entry point
# ---------------------------------------------------------------------------
def understand(
    text: str,
    *,
    location_hint: str = "",
    image_b64: str | None = None,
    image_media_type: str | None = None,
) -> Understanding:
    """Read one complaint. Never raises - always returns a valid Understanding."""
    provider = get_provider()
    if not (settings.llm_active and provider.available):
        return understand_offline(text)

    has_image = bool(image_b64 and image_media_type)
    key = _cache_key(text, provider.describe(), has_image)
    cached = _cache_get(key)
    if cached is not None:
        try:
            reading = Understanding(**cached)
            reading.source = "llm"
            reading.model = provider.describe()
            reading.explanation = (reading.explanation or "") + " (cached response)"
            return _enrich(reading, text)
        except ValidationError:
            logger.debug("Discarding invalid cached LLM response for %s", key)

    request = LLMRequest(
        system=SYSTEM_PROMPT,
        user=_user_prompt(text, location_hint, has_image),
        schema=LLM_RESPONSE_SCHEMA,
        image_b64=image_b64,
        image_media_type=image_media_type,
        max_tokens=settings.llm_max_tokens,
        timeout=settings.llm_timeout_seconds,
    )

    last_error = ""
    for attempt in (1, 2):
        try:
            payload = provider.extract(request)
        except LLMUnavailable as exc:
            logger.warning("LLM unavailable (%s); using offline classifier", exc)
            fallback = understand_offline(text)
            fallback.explanation = f"{fallback.explanation} (LLM unavailable: {exc})"
            return fallback

        try:
            reading = Understanding(**payload)
        except ValidationError as exc:
            last_error = str(exc)[:300]
            logger.warning("LLM returned invalid JSON (attempt %s): %s", attempt, last_error)
            if attempt == 1:
                request.user += (
                    "\n\nYour previous answer did not match the required schema:\n"
                    f"{last_error}\nReturn a corrected record that satisfies every constraint."
                )
                continue
            break

        reading.source = "llm"
        reading.model = provider.describe()
        if not reading.explanation:
            reading.explanation = f"Classified by {provider.describe()}"
        _cache_put(key, reading.model_dump(exclude={"source", "model", "explanation"}))
        return _enrich(reading, text)

    fallback = understand_offline(text)
    fallback.explanation = (
        f"{fallback.explanation} (LLM output failed validation twice, used offline classifier)"
    )
    return fallback


def cache_stats() -> dict[str, int]:
    """Used by the AI Health page to show how much of the demo is pre-cached."""
    return {"entries": len(_load_cache())}


def preload_cache(entries: dict[str, Any]) -> None:
    """Seed the response cache (used by the demo pre-warm script)."""
    with _cache_lock:
        cache = _load_cache()
        cache.update(entries)
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")


def cache_path() -> Path:
    return CACHE_PATH
