"""Measure the pipeline on the held-out split and write docs/EVALUATION numbers.

Four things are measured, all on clusters the classifier never trained on:

1. **Classification** - accuracy and macro-F1, broken down by language, for the
   offline path and (when a key is configured) the LLM path.
2. **Deduplication** - pairwise precision / recall / F1 against the planted
   ground-truth cluster ids, plus the share of triage work removed.
3. **Geocoding** - how often a complaint gets a map pin, and from which source.
4. **Latency** - p50 / p95 end to end and per stage.

The deduplication simulation runs against a throwaway SQLite database and
replays the test complaints in chronological order, exactly as they would have
arrived. That is the only honest way to score clustering: scoring it on a
pre-populated database would let the algorithm see the future.

Results are written to data/evaluation_report.json and stored as an EvalRun row
so the dashboard's AI Health page can show them.

Run:  python scripts/evaluate.py [--online-geocode]
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.config.settings import DATA_DIR, settings  # noqa: E402
from app.db import Base, init_db, session_scope  # noqa: E402
from app.models import EvalRun, Report  # noqa: E402
from app.pipeline import geocode as geocode_stage  # noqa: E402
from app.pipeline.fallback_clf import load_model, understand_offline  # noqa: E402
from app.pipeline.lexicon import analyse  # noqa: E402
from app.pipeline.orchestrator import run_pipeline  # noqa: E402
from app.pipeline.understand import understand  # noqa: E402
from app.security import encrypt_text, new_ticket_code  # noqa: E402
from app.services.bootstrap import ensure_reference_data  # noqa: E402

SYNTHETIC_CSV = DATA_DIR / "synthetic_complaints.csv"
REPORT_PATH = DATA_DIR / "evaluation_report.json"
TEMP_DB = settings.resolved_model_dir.parent / "evaluation_tmp.db"


def load_test_rows() -> list[dict]:
    if not SYNTHETIC_CSV.exists():
        raise SystemExit("Run scripts/generate_synthetic.py first")
    with SYNTHETIC_CSV.open(encoding="utf-8", newline="") as handle:
        rows = [row for row in csv.DictReader(handle) if row.get("split") == "test"]
    if not rows:
        raise SystemExit("The test split is empty")
    return sorted(rows, key=lambda row: row["created_at"])


def _macro_f1(true_labels: list[str], predicted: list[str]) -> float:
    labels = sorted(set(true_labels) | set(predicted))
    scores: list[float] = []
    for label in labels:
        true_positive = sum(1 for t, p in zip(true_labels, predicted) if t == label and p == label)
        false_positive = sum(1 for t, p in zip(true_labels, predicted) if t != label and p == label)
        false_negative = sum(1 for t, p in zip(true_labels, predicted) if t == label and p != label)
        precision = true_positive / (true_positive + false_positive) if (true_positive + false_positive) else 0.0
        recall = true_positive / (true_positive + false_negative) if (true_positive + false_negative) else 0.0
        scores.append(
            2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
        )
    return sum(scores) / len(scores) if scores else 0.0


def evaluate_classification(rows: list[dict]) -> dict:
    """Offline classifier, and the LLM path when one is configured."""
    results: dict[str, dict] = {}

    def score(name: str, predictor) -> dict | None:
        true_labels: list[str] = []
        predicted: list[str] = []
        by_language: dict[str, list[tuple[str, str]]] = defaultdict(list)
        latencies: list[float] = []
        low_confidence = 0

        for row in rows:
            started = time.perf_counter()
            try:
                reading = predictor(row["text"])
            except Exception as exc:  # noqa: BLE001
                print(f"  {name}: prediction failed ({exc}); skipping row")
                continue
            latencies.append((time.perf_counter() - started) * 1000)
            true_labels.append(row["category"])
            predicted.append(reading.category)
            by_language[row["language"]].append((row["category"], reading.category))
            if reading.confidence_0to1 < 0.55:
                low_confidence += 1

        if not true_labels:
            return None

        correct = sum(1 for t, p in zip(true_labels, predicted) if t == p)
        per_language = {}
        for language, pairs in sorted(by_language.items()):
            truths = [t for t, _ in pairs]
            predictions = [p for _, p in pairs]
            per_language[language] = {
                "n": len(pairs),
                "accuracy": round(
                    sum(1 for t, p in pairs if t == p) / len(pairs), 4
                ),
                "macro_f1": round(_macro_f1(truths, predictions), 4),
            }

        confusion = Counter(
            (t, p) for t, p in zip(true_labels, predicted) if t != p
        )
        return {
            "n": len(true_labels),
            "accuracy": round(correct / len(true_labels), 4),
            "macro_f1": round(_macro_f1(true_labels, predicted), 4),
            "by_language": per_language,
            "routed_to_human_pct": round(100.0 * low_confidence / len(true_labels), 1),
            "median_latency_ms": round(statistics.median(latencies), 2) if latencies else None,
            "top_confusions": [
                {"true": t, "predicted": p, "count": c} for (t, p), c in confusion.most_common(5)
            ],
        }

    print("Scoring offline classifier...")
    results["offline_classifier"] = score("offline", understand_offline)
    results["offline_classifier"]["model_trained"] = load_model() is not None

    if settings.llm_active:
        print(f"Scoring LLM path ({settings.llm_provider})...")
        results["llm"] = score("llm", lambda text: understand(text))
    else:
        results["llm"] = {
            "evaluated": False,
            "reason": (
                f"LLM_PROVIDER={settings.llm_provider} with no usable key. The offline "
                "classifier is the live path; these are the numbers that matter for the demo."
            ),
        }
    return results


def _pairwise(truth: list[str], predicted: list[str]) -> dict:
    """Pairwise precision / recall / F1 for a clustering."""
    true_positive = false_positive = false_negative = 0
    total = len(truth)
    for i in range(total):
        for j in range(i + 1, total):
            same_truth = truth[i] == truth[j]
            same_predicted = predicted[i] == predicted[j]
            if same_truth and same_predicted:
                true_positive += 1
            elif same_predicted and not same_truth:
                false_positive += 1
            elif same_truth and not same_predicted:
                false_negative += 1
    precision = (
        true_positive / (true_positive + false_positive)
        if (true_positive + false_positive)
        else 1.0
    )
    recall = (
        true_positive / (true_positive + false_negative)
        if (true_positive + false_negative)
        else 1.0
    )
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "true_positive_pairs": true_positive,
        "false_positive_pairs": false_positive,
        "false_negative_pairs": false_negative,
        "issues": len(set(predicted)),
    }


def _apply_review_links(assigned: list[str], links: list[tuple[str, str]]) -> list[str]:
    """Union-find: what the clustering becomes once an officer confirms the
    duplicate candidates the system deliberately escalated."""
    parent: dict[str, str] = {}

    def find(node: str) -> str:
        parent.setdefault(node, node)
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    def union(a: str, b: str) -> None:
        root_a, root_b = find(a), find(b)
        if root_a != root_b:
            parent[root_b] = root_a

    for code in assigned:
        find(code)
    for a, b in links:
        union(a, b)
    return [find(code) for code in assigned]


def evaluate_pipeline(rows: list[dict]) -> dict:
    """Replay the test complaints through the real pipeline in arrival order."""
    if TEMP_DB.exists():
        TEMP_DB.unlink()
    engine = create_engine(f"sqlite:///{TEMP_DB.as_posix()}", future=True)
    Base.metadata.create_all(bind=engine)

    stage_times: dict[str, list[float]] = defaultdict(list)
    pipeline_times: list[float] = []
    predicted_cluster: list[str] = []
    truth_cluster: list[str] = []
    located = 0
    location_sources: Counter[str] = Counter()
    dedup_decisions: Counter[str] = Counter()
    review_kinds: Counter[str] = Counter()
    review_links: list[tuple[str, str]] = []

    with Session(engine) as db:
        ensure_reference_data(db)
        for row in rows:
            created_at = datetime.fromisoformat(row["created_at"])
            report = Report(
                ticket_code=new_ticket_code(),
                raw_text_encrypted=encrypt_text(row["text"]),
                location_text=row["location_text"],
                lat=float(row["lat"]),
                lon=float(row["lon"]),
                location_source="gps",
                created_at=created_at,
                ground_truth_category=row["category"],
                ground_truth_cluster=row["cluster_id"],
                is_seed=True,
            )
            db.add(report)
            db.flush()

            started = time.perf_counter()
            outcome = run_pipeline(db, report, raw_text=row["text"])
            pipeline_times.append((time.perf_counter() - started) * 1000)
            db.commit()

            for stage in outcome.stage_summary:
                stage_times[stage["stage"]].append(float(stage["duration_ms"]))
            predicted_cluster.append(outcome.issue.issue_code)
            truth_cluster.append(row["cluster_id"])
            dedup_decisions[outcome.dedup_decision.decision] += 1
            if (
                outcome.dedup_decision.decision == "review"
                and outcome.dedup_decision.issue is not None
            ):
                review_links.append(
                    (outcome.issue.issue_code, outcome.dedup_decision.issue.issue_code)
                )
            for kind in outcome.review_kinds:
                review_kinds[kind] += 1
            if report.lat is not None:
                located += 1
            location_sources[report.location_source] += 1

        issue_count = len(set(predicted_cluster))

    # Two clusterings are scored. The first is what the machine did entirely on
    # its own. The second is what the system produces once an officer confirms
    # the duplicate candidates it deliberately escalated - which is how the
    # product actually runs, and the honest number to quote alongside it.
    total = len(truth_cluster)
    auto = _pairwise(truth_cluster, predicted_cluster)
    with_review = _pairwise(
        truth_cluster, _apply_review_links(predicted_cluster, review_links)
    )
    issue_count = auto["issues"]

    truth_groups = Counter(truth_cluster)
    ideal_issue_count = len(truth_groups)

    def percentile(values: list[float], fraction: float) -> float | None:
        if not values:
            return None
        ordered = sorted(values)
        index = max(0, min(len(ordered) - 1, int(round(fraction * (len(ordered) - 1)))))
        return round(ordered[index], 2)

    if TEMP_DB.exists():
        engine.dispose()
        try:
            TEMP_DB.unlink()
        except OSError:
            pass

    return {
        "dedup": {
            "reports": total,
            "issues_created": issue_count,
            "ideal_issues": ideal_issue_count,
            "auto_merge": auto,
            "with_human_review": with_review,
            "pairwise_precision": auto["precision"],
            "pairwise_recall": auto["recall"],
            "pairwise_f1": auto["f1"],
            "triage_work_saved_pct": round(100.0 * (1 - issue_count / total), 1) if total else 0.0,
            "triage_work_saved_with_review_pct": (
                round(100.0 * (1 - with_review["issues"] / total), 1) if total else 0.0
            ),
            "best_possible_work_saved_pct": (
                round(100.0 * (1 - ideal_issue_count / total), 1) if total else 0.0
            ),
            "decisions": dict(dedup_decisions),
            "caveat": (
                "Every true-duplicate pair in this split passes the hard gates "
                "(same category, within 150 m, within 14 days) and no non-duplicate pair "
                "does, so precision of 1.000 is an upper bound: the split contains no "
                "near-miss negatives. Thresholds were therefore set by reasoning about "
                "score composition with a safety margin, not by maximising F1 here."
            ),
        },
        "geocoding": {
            "resolved_pct": round(100.0 * located / total, 1) if total else 0.0,
            "by_source": dict(location_sources),
        },
        "human_review": {
            "tasks_raised": sum(review_kinds.values()),
            "by_kind": dict(review_kinds),
            "share_of_reports_pct": round(
                100.0 * sum(review_kinds.values()) / total, 1
            ) if total else 0.0,
        },
        "latency": {
            "pipeline_p50_ms": percentile(pipeline_times, 0.5),
            "pipeline_p95_ms": percentile(pipeline_times, 0.95),
            "by_stage": {
                stage: {
                    "p50_ms": percentile(values, 0.5),
                    "p95_ms": percentile(values, 0.95),
                }
                for stage, values in sorted(stage_times.items())
            },
        },
    }


def evaluate_geocoding_from_text(rows: list[dict], online: bool) -> dict:
    """Resolve location from TEXT ONLY - the hard case, with no GPS to lean on."""
    previous = settings.geocoding_enabled
    settings.geocoding_enabled = online
    resolved = 0
    sources: Counter[str] = Counter()
    try:
        with session_scope() as db:
            for row in rows:
                landmarks = analyse(row["text"]).landmarks
                resolution = geocode_stage.resolve_location(
                    db,
                    location_text=row["location_text"],
                    landmarks=landmarks,
                )
                sources[resolution.source] += 1
                if resolution.resolved:
                    resolved += 1
            db.commit()
    finally:
        settings.geocoding_enabled = previous

    return {
        "mode": "with Nominatim" if online else "offline (landmark fallback only)",
        "n": len(rows),
        "resolved_pct": round(100.0 * resolved / len(rows), 1) if rows else 0.0,
        "by_source": dict(sources),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate the NagarNetra pipeline")
    parser.add_argument(
        "--online-geocode",
        action="store_true",
        help="Also query Nominatim when scoring text-only geocoding (slow: 1 req/s)",
    )
    args = parser.parse_args()

    # The main database holds the EvalRun row and the geocode cache; make sure
    # its schema exists even on a clean checkout.
    init_db()

    rows = load_test_rows()
    print(f"Held-out test split: {len(rows)} complaints, "
          f"{len({r['cluster_id'] for r in rows})} ground-truth clusters\n")

    classification = evaluate_classification(rows)
    print("\nReplaying complaints through the full pipeline...")
    pipeline = evaluate_pipeline(rows)
    print("Scoring text-only geocoding...")
    geocoding_text = evaluate_geocoding_from_text(rows, args.online_geocode)

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "test_set": {
            "reports": len(rows),
            "clusters": len({row["cluster_id"] for row in rows}),
            "languages": dict(Counter(row["language"] for row in rows)),
            "categories": dict(Counter(row["category"] for row in rows)),
        },
        "classification": classification,
        **pipeline,
        "geocoding_text_only": geocoding_text,
        "configuration": {
            "llm_provider": settings.llm_provider,
            "llm_active": settings.llm_active,
            "offline_model_trained": load_model() is not None,
        },
    }

    REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    with session_scope() as db:
        db.add(EvalRun(label="holdout", report=report))
        db.commit()

    # ---- console summary ----
    offline = classification["offline_classifier"]
    dedup = pipeline["dedup"]
    print("\n" + "=" * 72)
    print("NAGARNETRA EVALUATION - held-out split")
    print("=" * 72)
    print(f"Classification (offline)   accuracy {offline['accuracy']:.1%}   "
          f"macro-F1 {offline['macro_f1']:.3f}")
    for language, stats in offline["by_language"].items():
        print(f"    {language:9s} n={stats['n']:<4} accuracy {stats['accuracy']:.1%}   "
              f"macro-F1 {stats['macro_f1']:.3f}")
    print(f"    routed to a human: {offline['routed_to_human_pct']}% of complaints")
    print()
    auto_d, review_d = dedup["auto_merge"], dedup["with_human_review"]
    print(f"Deduplication (automatic)  precision {auto_d['precision']:.3f}   "
          f"recall {auto_d['recall']:.3f}   F1 {auto_d['f1']:.3f}")
    print(f"Deduplication (+ officer)  precision {review_d['precision']:.3f}   "
          f"recall {review_d['recall']:.3f}   F1 {review_d['f1']:.3f}")
    print(f"    {dedup['reports']} reports collapsed into {dedup['issues_created']} issues "
          f"(ideal {dedup['ideal_issues']})")
    print(f"    triage work removed: {dedup['triage_work_saved_pct']}% automatically, "
          f"{dedup['triage_work_saved_with_review_pct']}% with officer confirmation "
          f"(best possible {dedup['best_possible_work_saved_pct']}%)")
    print()
    print(f"Geocoding (GPS present)    {pipeline['geocoding']['resolved_pct']}% located")
    print(f"Geocoding (text only, {geocoding_text['mode']})  "
          f"{geocoding_text['resolved_pct']}% located")
    print()
    print(f"Latency                    p50 {pipeline['latency']['pipeline_p50_ms']} ms   "
          f"p95 {pipeline['latency']['pipeline_p95_ms']} ms")
    print(f"Human review raised on     {pipeline['human_review']['share_of_reports_pct']}% "
          f"of complaints {pipeline['human_review']['by_kind']}")
    print("=" * 72)
    print(f"\nWrote {REPORT_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
