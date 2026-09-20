"""Fetch a sample of NYC 311 Service Requests and map it onto our taxonomy.

The PS-18 brief suggests NYC 311 as a reference dataset. We pull it from NYC
Open Data's Socrata API rather than Kaggle: no login, no multi-gigabyte
download, and published terms of use that permit this (see docs/DISCLOSURES.md).

Why bother, when our own corpus is purpose-built? Because it broadens the
offline classifier's English vocabulary beyond the phrasing our own templates
happen to use, which is exactly the overfitting risk a synthetic corpus carries.

A caveat worth stating plainly, because it changed how we use the data: NYC 311
``descriptor`` is a **controlled vocabulary, not free text**. The millions of
rows in that dataset contain only a few hundred distinct complaint phrasings, so
paging raw records returns the same strings over and over. We therefore ask
Socrata to group, and keep the distinct descriptor set - a few hundred real
English civic phrases such as "Catch Basin Sunken/Damaged/Raised" that no
template of ours would have produced.

It is a supporting signal, not the main one: rows are capped per category and
down-weighted during training (see scripts/train_fallback.py).

Offline? The script exits cleanly and training proceeds on the synthetic corpus
alone. Nothing in the product depends on this file existing.

Run:  python scripts/fetch_nyc311.py
"""

from __future__ import annotations

import csv
import sys
from collections import Counter
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.config.settings import DATA_DIR  # noqa: E402

ENDPOINT = "https://data.cityofnewyork.us/resource/erm2-nwe9.json"
PAGE_SIZE = 5000
MAX_PAGES = 8
PER_CATEGORY_CAP = 900

#: NYC complaint_type -> NagarNetra category. Only unambiguous mappings are
#: included; anything else is dropped rather than forced into a bucket.
COMPLAINT_TYPE_MAP: dict[str, str] = {
    "Street Condition": "pothole_road",
    "Pothole": "pothole_road",
    "Highway Condition": "pothole_road",
    "Curb Condition": "pothole_road",
    "Sidewalk Condition": "pothole_road",
    "Sanitation Condition": "garbage_waste",
    "Dirty Condition": "garbage_waste",
    "Dirty Conditions": "garbage_waste",
    "Missed Collection": "garbage_waste",
    "Missed Collection (All Materials)": "garbage_waste",
    "Illegal Dumping": "garbage_waste",
    "Overflowing Litter Baskets": "garbage_waste",
    "Residential Disposal Complaint": "garbage_waste",
    "Commercial Disposal Complaint": "garbage_waste",
    "Electronics Waste": "garbage_waste",
    "Street Light Condition": "streetlight",
    "Lamppost": "streetlight",
    "Street Light": "streetlight",
    "Sewer": "drainage_sewage",
    "Catch Basin Clogged/Flooding (Use Comments) (SC)": "drainage_sewage",
    "Street Flooding (SJ)": "drainage_sewage",
    "Water System": "water_supply",
    "Water Quality": "water_supply",
    "Water Conservation": "water_supply",
    "Drinking Water": "water_supply",
    "Rodent": "stray_animals",
    "Dead Animal": "stray_animals",
    "Unsanitary Animal Pvt Property": "stray_animals",
    "Animal in a Park": "stray_animals",
    "Unleashed Dog": "stray_animals",
    "Illegal Parking": "encroachment_illegal_parking",
    "Blocked Driveway": "encroachment_illegal_parking",
    "Obstruction": "encroachment_illegal_parking",
    "Derelict Vehicles": "encroachment_illegal_parking",
    "Derelict Vehicle": "encroachment_illegal_parking",
    "Vendor Enforcement": "encroachment_illegal_parking",
    "Damaged Tree": "tree_fall_hazard",
    "Overgrown Tree/Branches": "tree_fall_hazard",
    "Dead/Dying Tree": "tree_fall_hazard",
    "Illegal Tree Damage": "tree_fall_hazard",
}

TARGET = DATA_DIR / "nyc311_sample.csv"


def fetch() -> list[dict[str, str]]:
    """Fetch a capped sample for EACH category.

    One query per category, not one big query: the API returns rows in an
    arbitrary order that happens to cluster by complaint type, so a single
    paged query fills up on whichever types are most recent and starves the
    rest. Per-category queries guarantee balanced coverage.
    """
    by_category: dict[str, list[str]] = {}
    for complaint_type, category in COMPLAINT_TYPE_MAP.items():
        by_category.setdefault(category, []).append(complaint_type)

    collected: list[dict[str, str]] = []
    per_category: Counter[str] = Counter()

    with httpx.Client(timeout=30.0, headers={"User-Agent": "NagarNetra/1.0 (hackathon)"}) as client:
        for category, complaint_types in sorted(by_category.items()):
            quoted = ", ".join("'" + name.replace("'", "''") + "'" for name in complaint_types)
            # Ask Socrata to group, so we get the *distinct* descriptor
            # vocabulary in one request. NYC 311 descriptors are a controlled
            # list, not free text: paging raw rows returns the same handful of
            # strings thousands of times and teaches a TF-IDF model nothing.
            params = {
                "$select": "complaint_type,descriptor,count(*) as occurrences",
                "$where": f"complaint_type in({quoted})",
                "$group": "complaint_type,descriptor",
                "$order": "occurrences DESC",
                "$limit": str(PER_CATEGORY_CAP),
            }
            try:
                response = client.get(ENDPOINT, params=params)
                response.raise_for_status()
                batch = response.json()
            except Exception as exc:  # noqa: BLE001 - keep whatever we already have
                print(f"  {category:32s} failed ({type(exc).__name__})")
                continue

            # Deduplicate: 311 descriptors repeat heavily, and 900 copies of
            # "Pothole - Pothole" would teach the model nothing.
            seen: set[str] = set()
            for row in batch:
                complaint_type = (row.get("complaint_type") or "").strip()
                descriptor = (row.get("descriptor") or "").strip()
                text = f"{complaint_type} - {descriptor}".strip(" -")
                if len(text) < 6 or text.lower() in seen:
                    continue
                if per_category[category] >= PER_CATEGORY_CAP:
                    break
                seen.add(text.lower())
                per_category[category] += 1
                collected.append(
                    {
                        "text": text,
                        "category": category,
                        "source_type": complaint_type,
                        "occurrences": str(row.get("occurrences", "")),
                    }
                )
            print(f"  {category:32s} {per_category[category]:>4} distinct rows")
    return collected


def main() -> None:
    print("Fetching NYC 311 Service Requests (NYC Open Data, Socrata API)...")
    try:
        rows = fetch()
    except Exception as exc:  # noqa: BLE001 - offline is an acceptable outcome
        print(f"  could not reach NYC Open Data ({type(exc).__name__}: {exc})")
        print("  Skipping. Training will use the synthetic corpus only.")
        return

    if not rows:
        print("  no usable rows returned; skipping")
        return

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with TARGET.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=["text", "category", "source_type", "occurrences"]
        )
        writer.writeheader()
        writer.writerows(rows)

    counts = Counter(row["category"] for row in rows)
    print(f"wrote {TARGET.relative_to(ROOT)}  ({len(rows)} rows)")
    for category, count in counts.most_common():
        print(f"  {category:32s} {count}")
    print(
        "\nSource: NYC Open Data, 311 Service Requests (erm2-nwe9). "
        "Attribution and terms recorded in docs/DISCLOSURES.md."
    )


if __name__ == "__main__":
    main()
