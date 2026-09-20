"""Offline complaint classifier - the fallback that makes the LLM optional.

Two layers, in order of preference:

1. A TF-IDF (character + word n-grams) plus logistic-regression model trained by
   ``scripts/train_fallback.py`` on our synthetic multilingual corpus and a
   mapped sample of NYC 311.
2. The rule-based lexicon in :mod:`app.pipeline.lexicon`, which needs no
   training at all.

The two are combined rather than chained: when the model and the lexicon agree,
confidence goes up; when they disagree, it goes *down* and the complaint is
routed to a human. Disagreement between two independent methods is exactly the
signal that a person should look.

Character n-grams are used because they handle Devanagari and romanised Hinglish
without tokenisation, and they degrade gracefully on spelling variation.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import FeatureUnion, Pipeline

from app.config.settings import settings
from app.pipeline import lexicon
from app.pipeline.types import Understanding

logger = logging.getLogger(__name__)

MODEL_FILENAME = "fallback_clf.joblib"
#: Separator between the raw complaint and its canonical English expansion.
#: Both halves are fed to the vectoriser so the model can learn from the
#: original script *and* from the language-neutral terms.
FEATURE_SEPARATOR = " || "


def featurise(text: str) -> str:
    """Build the model input string. MUST be identical at train and predict time."""
    analysis = lexicon.analyse(text or "")
    canonical = " ".join(analysis.english_tokens)
    return f"{(text or '').strip()}{FEATURE_SEPARATOR}{canonical}"


def build_pipeline() -> Pipeline:
    """The sklearn estimator. Defined here so training and serving cannot drift."""
    return Pipeline(
        [
            (
                "features",
                FeatureUnion(
                    [
                        (
                            "char",
                            TfidfVectorizer(
                                analyzer="char_wb",
                                ngram_range=(2, 5),
                                min_df=2,
                                sublinear_tf=True,
                                max_features=60000,
                            ),
                        ),
                        (
                            "word",
                            TfidfVectorizer(
                                analyzer="word",
                                ngram_range=(1, 2),
                                min_df=1,
                                sublinear_tf=True,
                                max_features=40000,
                            ),
                        ),
                    ]
                ),
            ),
            (
                "clf",
                LogisticRegression(
                    max_iter=2000,
                    C=4.0,
                    class_weight="balanced",
                    random_state=42,
                ),
            ),
        ]
    )


@dataclass
class ModelBundle:
    estimator: Pipeline
    metadata: dict[str, Any]


def model_path() -> Path:
    return settings.resolved_model_dir / MODEL_FILENAME


_bundle: ModelBundle | None = None
_load_attempted = False


def load_model() -> ModelBundle | None:
    """Load the trained model once. Returns ``None`` when it has not been trained."""
    global _bundle, _load_attempted
    if _load_attempted:
        return _bundle
    _load_attempted = True
    path = model_path()
    if not path.exists():
        logger.info("No trained fallback model at %s; using lexicon rules only", path)
        return None
    try:
        payload = joblib.load(path)
        _bundle = ModelBundle(estimator=payload["estimator"], metadata=payload.get("metadata", {}))
        logger.info("Loaded fallback classifier (%s)", _bundle.metadata.get("trained_at", "?"))
    except Exception as exc:  # noqa: BLE001 - a corrupt model must not break intake
        logger.warning("Could not load fallback model (%s); using lexicon rules only", exc)
        _bundle = None
    return _bundle


def reset_model_cache() -> None:
    """Test/retrain hook."""
    global _bundle, _load_attempted
    _bundle = None
    _load_attempted = False


def _lexicon_confidence(analysis: lexicon.Analysis) -> float:
    """Confidence from lexical evidence alone: how much matched, how cleanly."""
    category, share = analysis.best_category
    if category is None:
        return 0.0
    strength = sum(analysis.category_scores.values())
    volume = min(1.0, strength / 4.0)
    return round(min(0.92, 0.30 + 0.45 * volume) * (0.55 + 0.45 * share), 4)


def _derive_severity(analysis: lexicon.Analysis) -> int:
    """Severity from lexical cues, floored by the hazards that are present."""
    severity = analysis.severity_hint or 3
    if {"live_wire", "open_manhole"} & set(analysis.hazards):
        severity = max(severity, 5)
    elif {"flooding", "accident_risk"} & set(analysis.hazards):
        severity = max(severity, 4)
    return max(1, min(5, severity))


def understand_offline(text: str) -> Understanding:
    """Classify a complaint with no network and no LLM.

    Always returns a valid :class:`Understanding`. When nothing at all could be
    recognised it returns category ``other`` with confidence 0, which the
    orchestrator turns into an ``unparsed`` review task - never a rejection.
    """
    analysis = lexicon.analyse(text or "")
    lex_category, lex_share = analysis.best_category
    lex_confidence = _lexicon_confidence(analysis)

    category = lex_category
    confidence = lex_confidence
    reasons: list[str] = []
    bundle = load_model()

    if bundle is not None and (text or "").strip():
        try:
            probabilities = bundle.estimator.predict_proba([featurise(text)])[0]
            classes = list(bundle.estimator.classes_)
            best_index = int(probabilities.argmax())
            model_category = str(classes[best_index])
            model_confidence = float(probabilities[best_index])

            category = model_category
            if lex_category is None:
                confidence = round(model_confidence * 0.90, 4)
                reasons.append(f"statistical model {model_confidence:.0%}, no keyword match")
            elif lex_category == model_category:
                confidence = round(min(0.97, model_confidence + 0.15 * lex_share), 4)
                reasons.append(f"model and keywords agree ({model_confidence:.0%})")
            else:
                # Two independent methods disagree -> deliberately low, so the
                # orchestrator sends this to a human instead of guessing.
                confidence = round(min(model_confidence, lex_confidence) * 0.60, 4)
                reasons.append(
                    f"model says {model_category} ({model_confidence:.0%}) but keywords "
                    f"suggest {lex_category} - flagged for review"
                )
        except Exception as exc:  # noqa: BLE001 - fall back to pure lexicon
            logger.warning("Fallback model inference failed (%s); using lexicon only", exc)

    if category is None:
        return Understanding(
            category="other",
            severity_1to5=3,
            hazard_flags=[],
            language=analysis.language,
            summary_en="",
            confidence_0to1=0.0,
            source="offline_classifier",
            model="lexicon-v1",
            explanation="No known civic keyword matched, and no category could be inferred.",
            matched_terms=[],
        )

    if analysis.matched_surface:
        shown = ", ".join(f"'{s}'" for s in analysis.matched_surface[:4])
        reasons.insert(0, f"matched {shown}")

    return Understanding(
        category=category,
        sub_issue=(analysis.matched_terms[0].replace("_", " ") if analysis.matched_terms else ""),
        severity_1to5=_derive_severity(analysis),
        hazard_flags=analysis.hazards,
        location_text=" ".join(analysis.landmarks + analysis.place_nouns),
        landmarks=analysis.landmarks,
        language=analysis.language,
        summary_en=analysis.summary_en,
        confidence_0to1=confidence,
        source="offline_classifier",
        model=("tfidf-logreg-v1" if bundle is not None else "lexicon-v1"),
        explanation="; ".join(reasons) if reasons else "Classified from civic keyword matches.",
        matched_terms=analysis.matched_terms,
    )
