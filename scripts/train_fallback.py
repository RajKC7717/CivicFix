"""Train the offline complaint classifier.

This model is what lets NagarNetra run with ``LLM_PROVIDER=none`` - no API key,
no network, no GPU. It is a character + word TF-IDF feature union feeding a
logistic regression, defined once in ``app.pipeline.fallback_clf.build_pipeline``
so that training and serving can never drift apart.

Training data
-------------
* ``data/synthetic_complaints.csv`` (train split only) - multilingual, and the
  only source that contains Devanagari or Hinglish.
* ``data/nyc311_sample.csv`` - real English civic descriptors, down-weighted.

The weighting matters. The NYC rows outnumber our Marathi and Hindi examples,
and an unweighted fit would quietly become an English classifier that happens to
guess on Devanagari. Synthetic rows therefore carry ``SYNTHETIC_WEIGHT`` and NYC
rows ``NYC_WEIGHT``; the ratio is reported at the end of training so the trade-off
is visible rather than buried.

The held-out test split is never touched here. It belongs to scripts/evaluate.py.

Run:  python scripts/train_fallback.py
"""

from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
from sklearn.metrics import classification_report, f1_score
from sklearn.model_selection import cross_val_score

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.config.settings import DATA_DIR, settings  # noqa: E402
from app.pipeline.fallback_clf import MODEL_FILENAME, build_pipeline, featurise  # noqa: E402

SYNTHETIC_CSV = DATA_DIR / "synthetic_complaints.csv"
NYC_CSV = DATA_DIR / "nyc311_sample.csv"

#: Our multilingual rows are the point of the model; NYC rows are vocabulary.
SYNTHETIC_WEIGHT = 3.0
NYC_WEIGHT = 1.0


def load_synthetic() -> tuple[list[str], list[str], list[str]]:
    """Return (texts, labels, languages) for the TRAIN split only."""
    if not SYNTHETIC_CSV.exists():
        raise SystemExit(
            f"{SYNTHETIC_CSV} not found. Run: python scripts/generate_synthetic.py"
        )
    texts: list[str] = []
    labels: list[str] = []
    languages: list[str] = []
    with SYNTHETIC_CSV.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if row.get("split") != "train":
                continue
            texts.append(row["text"])
            labels.append(row["category"])
            languages.append(row["language"])
    return texts, labels, languages


def load_nyc() -> tuple[list[str], list[str]]:
    """Return (texts, labels) from the NYC 311 sample, or empty lists."""
    if not NYC_CSV.exists():
        print("  note: data/nyc311_sample.csv not found - training on synthetic data only")
        print("        (run scripts/fetch_nyc311.py when online to broaden English coverage)")
        return [], []
    texts: list[str] = []
    labels: list[str] = []
    with NYC_CSV.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            texts.append(row["text"])
            labels.append(row["category"])
    return texts, labels


def main() -> None:
    print("Loading training data...")
    synthetic_texts, synthetic_labels, synthetic_languages = load_synthetic()
    nyc_texts, nyc_labels = load_nyc()

    texts = synthetic_texts + nyc_texts
    labels = synthetic_labels + nyc_labels
    weights = np.array(
        [SYNTHETIC_WEIGHT] * len(synthetic_texts) + [NYC_WEIGHT] * len(nyc_texts)
    )

    print(f"  synthetic (train split): {len(synthetic_texts)} rows  weight {SYNTHETIC_WEIGHT}")
    print(f"  NYC 311 descriptors    : {len(nyc_texts)} rows  weight {NYC_WEIGHT}")
    synthetic_mass = SYNTHETIC_WEIGHT * len(synthetic_texts)
    total_mass = synthetic_mass + NYC_WEIGHT * len(nyc_texts)
    print(f"  effective share from our multilingual corpus: {synthetic_mass / total_mass:.0%}")
    print(f"  language mix (synthetic): {dict(Counter(synthetic_languages))}")

    label_counts = Counter(labels)
    if len(label_counts) < 2:
        raise SystemExit("Need at least two categories to train")

    print("\nBuilding features (raw text + canonical English expansion)...")
    features = [featurise(text) for text in texts]

    print("Fitting TF-IDF (char 2-5 + word 1-2) -> logistic regression...")
    estimator = build_pipeline()
    estimator.fit(features, labels, clf__sample_weight=weights)

    # Cross-validation on the training data only. This is a sanity check that
    # the model learned something, NOT the headline metric - that comes from the
    # held-out split in scripts/evaluate.py.
    print("\nCross-validating (5-fold, training data only)...")
    try:
        scores = cross_val_score(
            build_pipeline(), features, labels, cv=5, scoring="f1_macro", n_jobs=1
        )
        cv_mean, cv_std = float(scores.mean()), float(scores.std())
        print(f"  macro-F1: {cv_mean:.3f} (+/- {cv_std:.3f})")
    except Exception as exc:  # noqa: BLE001 - CV is diagnostic, not required
        cv_mean, cv_std = float("nan"), float("nan")
        print(f"  cross-validation skipped ({exc})")

    in_sample = estimator.predict(features)
    print("\nIn-sample report (optimistic by construction - see EVALUATION.md):")
    print(
        classification_report(
            labels, in_sample, zero_division=0, digits=3, sample_weight=weights
        )
    )

    metadata = {
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "synthetic_rows": len(synthetic_texts),
        "nyc_rows": len(nyc_texts),
        "synthetic_weight": SYNTHETIC_WEIGHT,
        "nyc_weight": NYC_WEIGHT,
        "classes": sorted(label_counts),
        "class_counts": dict(label_counts),
        "language_mix": dict(Counter(synthetic_languages)),
        "cv_macro_f1": None if cv_mean != cv_mean else round(cv_mean, 4),
        "cv_macro_f1_std": None if cv_std != cv_std else round(cv_std, 4),
        "in_sample_macro_f1": round(
            float(f1_score(labels, in_sample, average="macro", zero_division=0)), 4
        ),
        "feature_pipeline": "tfidf(char_wb 2-5) + tfidf(word 1-2) -> LogisticRegression",
    }

    target = settings.resolved_model_dir / MODEL_FILENAME
    joblib.dump({"estimator": estimator, "metadata": metadata}, target, compress=3)
    size_kb = target.stat().st_size / 1024
    print(f"\nSaved {target} ({size_kb:.0f} KB)")

    metadata_path = settings.resolved_model_dir / "fallback_clf_metadata.json"
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(f"Saved {metadata_path}")


if __name__ == "__main__":
    main()
