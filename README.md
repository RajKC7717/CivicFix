<div align="center">

# नगरनेत्र · NagarNetra

**The city's eye — intelligent citizen grievance triage, deduplication and accountability**

**Challenge `PS-18` "CivicFix"** · Global SDG + AI Hackathon 2026 · BV(DU) COEP, Pune
Safe & Smart Communities track · **SDG 11** (Sustainable Cities) + **SDG 16** (Accountable Institutions)

</div>

---

## The problem

Indian cities do not have a *reporting* problem. They have a **triage** problem.

A hundred people report the same pothole in three languages, and a hundred separate
tickets land on one officer's desk. Each gets its own work order, its own SLA clock,
its own crew visit. Meanwhile nobody can answer the only question that matters for
accountability: **is this ward being served as well as that one?**

## What NagarNetra does

| | |
|---|---|
| **One issue, many voices** | A Marathi voice note and a Hinglish text about the same pothole become **one issue with a count of two**, not two tickets. The citizen is never told "duplicate, rejected" — they are told *"12 others reported this, and your report raised its priority."* |
| **Explainable priority** | The AI only *extracts features*. The score is a transparent weighted sum published in [`priority_config.yaml`](backend/app/config/priority_config.yaml) that an officer, an auditor or an RTI applicant can reproduce by hand. Every score ships with its arithmetic. |
| **Equity audit** | Per-ward and per-language resolution-time and SLA-breach parity against the city median, with an optional, visible, switchable priority boost for under-served wards. This is the SDG-16 half that most civic apps skip. |

> **Scope.** NagarNetra is a **decision-support tool for municipal staff. It is not an
> autonomous enforcement system. Final decisions rest with officers.**

---

## Quick start

**One command.** No API key, no GPU, no internet required.

```powershell
./run.ps1        # Windows PowerShell
```
```bash
./run.sh         # macOS / Linux / Git Bash
```

The first run creates the virtualenv, installs dependencies, builds the ward polygons
and synthetic corpus, trains the offline classifier and seeds the demo database. Later
runs just start the servers.

| | |
|---|---|
| Citizen app | <http://localhost:5173> |
| Officer console | <http://localhost:5173/admin> — `officer` / `officer` |
| API documentation | <http://127.0.0.1:8000/docs> |

**Recording a demo?** [`docs/DEMO_SCRIPT.md`](docs/DEMO_SCRIPT.md) has the exact text to
paste, a timed shot list, narration, and what to do when something fails on camera.

<details>
<summary>Manual setup, or Docker</summary>

```bash
python -m venv .venv && .venv/Scripts/python.exe -m pip install -r backend/requirements-dev.txt
.venv/Scripts/python.exe scripts/build_wards.py          # ward polygons + POIs
.venv/Scripts/python.exe scripts/generate_synthetic.py   # 430-complaint corpus
.venv/Scripts/python.exe scripts/fetch_nyc311.py         # optional, needs network
.venv/Scripts/python.exe scripts/train_fallback.py       # offline classifier
.venv/Scripts/python.exe scripts/seed_db.py --reset      # demo database
.venv/Scripts/python.exe -m uvicorn app.main:app --app-dir backend --port 8000
cd frontend && npm install && npm run dev
```

```bash
docker compose up --build        # same thing, containerised
```
</details>

---

## It works with the internet unplugged

This is a design constraint, not a fallback. `LLM_PROVIDER=none` is the **default and
fully supported** configuration, and it is how the demo runs.

* **Cross-lingual understanding with no translation API.** A hand-built civic lexicon
  plus a Devanagari transliterator maps Marathi, Hindi, Hinglish and English onto one
  canonical English representation. `"कात्रज डेअरी समोर मोठा खड्डा"` and
  `"Katraj dairy ke saamne bada gaddha hai"` share almost no characters and produce an
  **identical** match key.
* **No PyTorch.** The deduplication embedder is stateless hashed n-grams over that
  canonical text — deterministic, ~0 ms, nothing to download. `sentence-transformers`
  is an optional drop-in upgrade the code auto-detects; it is never required.
* **Geocoding degrades in four steps** — GPS → photo EXIF → Nominatim → a known Pune
  locality → the human review queue. "Katraj dairy samor" still lands on the map with
  no network.
* **The map says so.** When OpenStreetMap tiles are unreachable the tile layer is
  dropped, ward outlines and markers keep rendering, and a note explains why.

An LLM (Claude, Gemini or OpenAI, behind one interface) is an *enhancement*. When a key
is present it is used, its output is validated against a strict schema with one retry,
and if it fails or times out the offline path answers instead — the citizen never sees
a failure.

---

## Measured results

Held out **by cluster** (never by row — splitting a duplicate group across train and
test would make the dedup score meaningless). Reproduce with
`python scripts/evaluate.py`.

### Classification — 96 unseen complaints

| Language | n | Accuracy | macro-F1 |
|---|---:|---:|---:|
| English | 25 | 100% | 1.000 |
| मराठी Marathi | 37 | 100% | 1.000 |
| हिन्दी Hindi | 15 | 100% | 1.000 |
| Hinglish (romanised) | 19 | 100% | 1.000 |
| **Overall** | **96** | **100%** | **1.000** |

> ⚠️ **Read this number honestly.** The test split is *synthetic* and shares phrasing
> patterns with training, so 100% is **not a real-world accuracy claim** — it shows the
> pipeline is sound, not that it is finished. The 5-fold cross-validated macro-F1 on
> the training corpus is **0.951 ± 0.030**, which is the more sober figure. The AI
> Health page in the app states this caveat on screen. See
> [`docs/LIMITATIONS.md`](docs/LIMITATIONS.md).

### Deduplication — the headline capability

| | Precision | Recall | F1 | Triage work removed |
|---|---:|---:|---:|---:|
| Fully automatic | **1.000** | 0.660 | 0.795 | 18.8% |
| With officer confirmation | **1.000** | 1.000 | **1.000** | **24.0%** |
| *Theoretical maximum* | — | — | — | *24.0%* |

**Zero false merges.** The system auto-merges only what it is sure of and escalates the
ambiguous middle band to a human — and once those are confirmed it reaches this
dataset's ceiling exactly. 96 reports collapse into 78 issues automatically.

> The held-out split contains no *near-miss negatives* (every true-duplicate pair passes
> the hard gates and no other pair does), so precision of 1.000 is an upper bound. The
> thresholds were therefore chosen by reasoning about score composition with a safety
> margin, **not** by maximising F1 on this set. That caveat ships inside the metric
> itself and is rendered on the AI Health page.

### Everything else

| | |
|---|---:|
| Geocoding success (GPS present) | 100% |
| Geocoding success (text only, **fully offline**) | 100% |
| Pipeline latency | **p50 20 ms**, p95 42 ms |
| Complaints routed to a human | 10.4% |
| Test suite | **95 passing** |

---

## How it works

```
        CITIZEN (mobile-first, en/hi/mr)
        text · voice · photo · GPS/pin/landmark
                      │
                      ▼  POST /api/complaints
        ┌─────────────────────────────────┐
        │ INGEST — ticket issued first    │   nothing is ever rejected
        └──────────────┬──────────────────┘
                       ▼
  redact → understand → image → geocode → ward → dedup → priority → sla
     │         │                   │                │        │
     │         ├ LLM (schema)      ├ GPS>EXIF>      ├ embed  ├ weighted
     │         │  ↓ retry ↓        │  Nominatim>    │ +geo   │ formula
     │         └ TF-IDF+LogReg     │  landmark      │ +time  │ (yaml)
     │                             └ ↓ review       └ ↓ review
     └── every stage logs {output, confidence, source, ms} to the database
                       ▼
     Issue (n reports) ── ReviewTask ── AuditLog (who/what/before/after/why)
                       ▼
        OFFICER DASHBOARD — queue · map · review inbox
        SLA · EQUITY AUDIT · AI HEALTH · audit log
```

Two invariants hold no matter what fails:

1. **Nothing is ever rejected.** A failing stage degrades the record and raises a
   review task. It never discards a citizen's report.
2. **Nothing is ever deleted.** Deduplication *links* a report to an issue; the report
   keeps its own ticket code and stays independently addressable. Merges are reversible.

Full detail in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

---

## Responsible AI — built as features, not slides

| Requirement | Where it lives |
|---|---|
| **No silent rejection** | Every submission gets a ticket. Low confidence, an unresolvable location or an ambiguous duplicate raise a `ReviewTask` — never a discard. 10.4% of complaints are routed to a human *by design*. |
| **Human in the loop** | Officers override category, priority band, cluster membership, location and status. The review inbox shows both reports side by side for duplicates. |
| **Reasoned overrides** | Every override **requires a written reason** (enforced at the API layer, minimum 8 characters) and is written to an append-only `audit_log` with actor, before, after, why and when. No code path edits or deletes an audit row. |
| **Transparency** | Every AI output is shown with its confidence *and its source* — "Claude", "offline classifier" or a named officer. Citizens see the exact words that produced their category. The full 8-stage trace is on the issue page. |
| **Privacy** | PII is redacted (phone, e-mail, Aadhaar, vehicle, PAN) *before* anything is classified, logged or sent anywhere. Raw text is Fernet-encrypted at rest and never returned by any endpoint. Photo EXIF is stripped by pixel re-encode; GPS is read **only** with explicit consent. PIN codes and house numbers are deliberately *not* redacted — they are location, not identity. |
| **Fairness** | Per-language classification accuracy and per-ward/per-language resolution parity are first-class dashboard pages, not appendices. |
| **Scope statement** | In the app footer, the API description and this README. |

Model card: [`docs/RESPONSIBLE_AI.md`](docs/RESPONSIBLE_AI.md).

---

## Repository layout

```
backend/app/
  config/      priority_config.yaml   ← the ENTIRE scoring, SLA and dedup policy
  pipeline/    redact · lexicon · understand · fallback_clf · image
               geocode · ward · embed · dedup · priority · sla · orchestrator
               llm/   anthropic · gemini · openai · none
  routers/     complaints · admin · analytics · public · auth
  services/    equity · audit · demo · bootstrap
backend/tests/ 95 tests
frontend/src/  citizen/ · admin/ · components/ · i18n/ · lib/
data/          synthetic_complaints.csv · wards.geojson · pois.csv · nyc311_sample.csv
scripts/       generate_synthetic · build_wards · fetch_nyc311
               train_fallback · evaluate · seed_db
docs/          ARCHITECTURE · RESPONSIBLE_AI · EVALUATION · IMPACT
               DISCLOSURES · LIMITATIONS · DEMO_SCRIPT
```

**Stack.** Python 3.11 · FastAPI · SQLAlchemy 2 · SQLite · scikit-learn · shapely ·
Pillow — React 18 · Vite · TypeScript · Tailwind · React-Leaflet · Recharts.
No Celery, no Redis, no Postgres, no GPU. One process, one file, one command.

---

## Data & disclosures

* **All complaint data is synthetic.** 430 generated complaints across four languages,
  12 Pune localities and 9 categories, with **42 planted duplicate groups** carrying
  ground-truth cluster ids. No real citizen complaint, name or phone number appears in
  this repository. Deterministic: same seed, same file.
* **Ward boundaries are synthetic.** A Voronoi tessellation of twelve *real* Pune
  locality centroids clipped to the city bounding box — verified gap-free and
  non-overlapping over 3,000 random points. They are **not** PMC electoral wards, and
  the app says so wherever they are drawn.
* **NYC 311** (NYC Open Data, Socrata API) contributes 368 distinct real English civic
  descriptors, down-weighted 3:1 against our multilingual corpus so the model cannot
  drift into being English-only.
* **AI coding tools** (Claude Code) were used to build this project.

Full licence and attribution list: [`docs/DISCLOSURES.md`](docs/DISCLOSURES.md).

---

## Configuration

Copy `.env.example` to `.env`. The defaults are a complete, working, fully offline
configuration — **you do not need to change anything to run the demo.**

| Variable | Default | Notes |
|---|---|---|
| `LLM_PROVIDER` | `none` | `none` · `anthropic` · `gemini` · `openai` |
| `ANTHROPIC_API_KEY` | *(empty)* | If absent, the offline classifier answers and the UI says so |
| `SECRET_KEY` | dev value | Derives the at-rest encryption key. **Change before any non-demo use.** |
| `NOMINATIM_USER_AGENT` | identifying string | Policy requires a real contact; 1 req/s is enforced in code |
| `DEMO_MODE` | `true` | Exposes the dashboard's reset button |

Never commit a real `.env`.

---

## Verify it yourself

```bash
python -m pytest backend/tests -q     # 95 tests
python scripts/evaluate.py            # regenerate every number above
```

---

## Known limitations

The lexicon is deliberately narrow and deep — civic vocabulary for nine categories in
four languages. It is not a general translator. Demo authentication is hardcoded and
labelled as such. The synthetic corpus, however carefully built, is not a substitute
for real municipal data, and the headline accuracy figure should be read with that in
mind. The honest, complete list is in [`docs/LIMITATIONS.md`](docs/LIMITATIONS.md) —
written before anyone had to ask.

---

<div align="center">

**Decision-support for municipal staff. Not an autonomous enforcement system.
Final decisions rest with officers.**

`PS-18` · SDG 11 + SDG 16

</div>
