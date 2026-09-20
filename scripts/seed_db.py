"""Build the NagarNetra demo database from the synthetic corpus.

Replays every complaint through the real pipeline, so the seeded database is a
genuine product of the code being demonstrated rather than a fabricated table.

Run:  python scripts/seed_db.py [--reset] [--split all|train|test] [--limit N]
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.db import init_db, session_scope  # noqa: E402
from app.services.demo import seed, wipe  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the NagarNetra database")
    parser.add_argument("--reset", action="store_true", help="Delete existing complaints first")
    parser.add_argument("--split", default="all", choices=["all", "train", "test"])
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    init_db()
    started = time.perf_counter()
    with session_scope() as db:
        if args.reset:
            print("Clearing existing complaint data...")
            wipe(db)
        print(f"Seeding ({args.split} split) through the live pipeline...")
        summary = seed(db, split=args.split, limit=args.limit, progress=True)

    elapsed = time.perf_counter() - started
    print("\nDone in %.1fs" % elapsed)
    for key, value in summary.items():
        print(f"  {key:20s} {value}")
    collapsed = summary["reports_collapsed"]
    if summary["reports"]:
        print(
            f"\n  {collapsed} of {summary['reports']} reports were folded into existing issues "
            f"= {100.0 * collapsed / summary['reports']:.1f}% less triage work."
        )


if __name__ == "__main__":
    main()
