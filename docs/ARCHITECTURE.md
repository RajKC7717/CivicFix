# Architecture

**NagarNetra** · PS-18 "CivicFix"

---

## 1. The two nouns everything hangs off

The whole design follows from one distinction:

| | **Report** | **Issue** |
|---|---|---|
| Is | what *one citizen said* | what *the city has to fix* |
| Created by | a submission | the first report that cannot join an existing issue |
| Lifecycle | immutable evidence | status, SLA, assignment, priority |
| Deleted? | **never** | **never** (merges set `merged_into_id`) |
| Addressable by | its own ticket code, forever | an issue code |

A conventional grievance portal has only the first noun, so a hundred reports of one
pothole become a hundred work orders. NagarNetra makes the *issue* the unit of work and
the *count of reports* a signal that feeds priority. That is the entire "one issue, many
voices" idea, and it is a data-model decision before it is an AI one.

---

## 2. Request path

```
        CITIZEN (mobile-first PWA, en / hi / mr)
        text · voice (Web Speech) · photo · GPS / pin / landmark
                          │
                          │  POST /api/complaints   (multipart)
                          ▼
   ┌──────────────────────────────────────────────────────────────┐
   │ INGEST                                                        │
   │  1. write the Report row + ticket code   ← the citizen's receipt
   │  2. encrypt raw text at rest (Fernet)                         │
   │  3. run the pipeline                                          │
   └──────────────────────────┬───────────────────────────────────┘
                              ▼
   redact → understand → image → geocode → ward → dedup → priority → sla
                              │
                              ├─ attach to an existing Issue, or create one
                              ├─ raise ReviewTask(s) where the AI deferred
                              └─ respond to the citizen with the explanation
                              ▼
            BackgroundTask: recompute the cluster's scoring
```

**Why ingest is synchronous.** The citizen must get a ticket *and a plain-language
explanation* in one round trip — "your report joined 12 others and raised its priority"
is worthless three minutes later. The offline path costs ~20 ms end to end, so this is
affordable. The genuinely deferrable work (recomputing the whole cluster's priority
after the equity cache may have shifted) runs in a `BackgroundTask`.

**Why the Report row is written first.** It is the citizen's receipt. If every AI stage
exploded, the complaint still exists, still has a ticket, and is flagged for a human.
The API has an explicit handler for exactly this: it returns 201 with a degraded
payload rather than 500-ing a citizen who did nothing wrong.

---

## 3. The eight stages

Each is a separate, independently testable function with its own fallback. Each writes
a `PipelineStageLog` row: output, confidence, which implementation answered, and
milliseconds. That table is what the officer's trace view and the AI Health page are
built from — without it, "explainable" would be a slide.

| # | Stage | Primary | Fallback | Failure mode |
|---|---|---|---|---|
| 1 | **redact** | regex rules (phone, e-mail, Aadhaar, vehicle, PAN) | — | cannot fail; deterministic |
| 2 | **understand** | LLM, forced to a JSON schema, one corrective retry | TF-IDF + logistic regression, then the lexicon alone | low confidence → review queue |
| 3 | **image** | Pillow decode, EXIF GPS *with consent*, metadata stripped by pixel re-encode | skip; record "image not analysed" | non-image upload is refused, intake continues |
| 4 | **geocode** | GPS/pin → EXIF → Nominatim (1 req/s, cached) → known locality centroid | each step is the next one's fallback | unresolved → review queue asking for a pin |
| 5 | **ward** | point-in-polygon (shapely, prepared geometries) | nearest locality centroid | no coordinate → skipped |
| 6 | **dedup** | embed match key + distance + recency | — | middle band → human; no location → never auto-merges |
| 7 | **priority** | weighted sum from `priority_config.yaml` | — | pure arithmetic |
| 8 | **sla** | per-category hours, hazard may only shorten | default hours | — |

### Stage 2 in detail — why there are two classifiers

The LLM path and the offline path produce the **same** validated `Understanding`
object, so nothing downstream branches on which one ran. Only `source` and `model`
differ, and both are surfaced to the citizen and the officer.

When the trained model and the rule-based lexicon **disagree**, that disagreement is
itself the signal: confidence is deliberately cut and the complaint goes to a human.
Which category gets pre-filled is decided by the model's *margin over its runner-up*,
not its raw probability — a model at 0.51 with the next class on 0.17 has made a real
choice; one at 0.46 with the next on 0.30 is guessing, and an unambiguous keyword beats
a guess. (This rule was added after the test suite caught an exposed live wire being
filed as a tree hazard.)

---

## 4. The cross-lingual trick

This is the technical core, and it is not a neural model.

```
"कात्रज डेअरी समोर मोठा खड्डा आहे, शाळेजवळ"        (Marathi)
"Katraj dairy ke saamne bada gaddha hai, school ke paas"  (Hinglish)
        │                                    │
        └────────────  lexicon.analyse()  ───┘
                          │
     ┌────────────────────┴────────────────────┐
     ▼                                         ▼
summary_en (for humans)                 match_text (for machines)
"Pothole opposite Katraj dairy          "dairy katraj katraj large near
 (near school)"                          near school opposite pothole
                                          school"           ← sorted
     │                                         │
     ▼                                         ▼
 issue title, citizen explanation        dedup cosine similarity → 1.000
```

Three deliberate choices make this work:

1. **Both languages normalise to the same canonical English terms.** A hand-built civic
   lexicon (Devanagari stems + romanised variants + English) plus a Devanagari→Latin
   transliterator for unknown words, mostly place names.
2. **The display title and the match key are different strings.** A title is written to
   be *read* by an officer; a match key is written to be *compared* by a machine.
   Forcing one string to do both cost real accuracy — separating them moved the
   separation AUC from 0.904 to 0.989.
3. **The match key is sorted.** The vectoriser uses word bigrams and character n-grams,
   so two identical complaints whose terms merely matched in a different order scored
   0.905 instead of 1.000 until the key was sorted.

Because the comparison happens on canonical English, a purely lexical embedder is
sufficient — which is why the system needs no PyTorch and no model download.

---

## 5. Deduplication

```
                     incoming report
                            │
        ┌───────────────────▼───────────────────┐
        │ HARD GATES (never compared otherwise) │
        │   same category                       │
        │   within 150 m                        │
        │   within 14 days                      │
        │   issue still open, not merged away   │
        └───────────────────┬───────────────────┘
                            ▼
   score = 0.60·cosine(match_text) + 0.30·proximity + 0.10·recency

        ≥ 0.72  →  MERGE      "12 others reported this"
        ≥ 0.58  →  REVIEW     both reports, side by side, to a human
        <  0.58 →  NEW ISSUE
```

The hard gates do most of the discriminating work, which keeps false merges rare and
the query cheap (a bounding-box pre-filter runs before any haversine).

**Proximity decays gently inside the radius** (`distance_decay: 0.5`). A candidate has
already passed a hard 150 m gate, and two people pinning the same pothole routinely
differ by 50–100 m through GPS drift or by describing opposite ends of one defect. A
linear decay to zero punished that normal variation so hard that genuinely identical
reports failed to merge.

**A report with no location can never auto-merge** — only reach *review*. Without a pin
we cannot distinguish this pothole from the next street's, and guessing would be worse
than asking.

---

## 6. Priority

The AI never produces the number. It extracts features; the number is arithmetic.

```
score = severity×8                        (AI)        max 40
      + Σ hazard points                   (AI)        max 35
      + 14·log₁₀(1 + report_count)        (citizens)  max 22
      + 12·min(1, elapsed/sla) + breach   (policy)
      + nearby school/hospital            (map data)  max 12
      + equity adjustment                 (equity)    6
      → capped at 100 → band P1..P4
```

Every weight lives in [`priority_config.yaml`](../backend/app/config/priority_config.yaml)
and nowhere else. The file is served verbatim at `/api/meta/policy` so anyone can audit
it without repository access.

Three properties worth naming:

* **Cluster size is log-scaled** so one organised group cannot brigade a street to the
  top of the queue. The 2nd report is strong evidence; the 50th adds little.
* **SLA pressure rises with age**, so old unglamorous complaints cannot be starved
  forever by a stream of new dramatic ones.
* **No double charging.** A `near_school` hazard already counted suppresses the
  map-derived school bonus.

Every component carries a `source` (`ai` · `citizens` · `map` · `policy` · `equity`) so
the dashboard can colour-code where each point came from.

---

## 7. Data model

```
wards ──┬── issues ──┬── reports ──┬── pipeline_stage_logs
        │            │             └── review_tasks
pois    │            ├── status_events
        │            └── feedback
        └── (merged_into_id → issues.id, self-referencing)

audit_log     append-only, never updated or deleted
settings      runtime policy toggles (equity boost)
geocode_cache Nominatim results, survives a reseed
eval_runs     stored output of scripts/evaluate.py
```

`reports.raw_text_encrypted` holds Fernet ciphertext and is **never** returned by any
endpoint. `reports.redacted_text` is the only text that is classified, logged or sent
anywhere. `reports.reporter_ref` is a salted hash of a client-generated device id — it
lets us count distinct citizens without storing anything that identifies one.

---

## 8. Frontend

Two applications, one bundle, code-split so a citizen on a slow connection never
downloads the officer dashboard.

```
/                 citizen home, live counters, city map
/report           text · voice · photo · GPS/pin/landmark
/ticket/:code     the explained confirmation
/track/:code      public timeline + post-resolution rating
/map              public issue map

/admin            priority queue + cluster map
/admin/issues/:c  reports, score arithmetic, 8-stage trace, overrides, audit
/admin/review     human-in-the-loop inbox (4 kinds)
/admin/sla        breach rates, backlog ageing, created-vs-resolved
/admin/equity     ward + language parity, AI accuracy by language
/admin/ai-health  live counters and the held-out benchmark, kept apart
/admin/audit      append-only decision log
```

**i18n** is a hand-written typed dictionary, not a library — the string set is small,
the bundle stays tiny, and there is no runtime loader that can fail on venue Wi-Fi.
TypeScript refuses to compile if a translation goes missing.

**Fonts are self-hosted** via `@fontsource` (Inter + Noto Sans Devanagari). No Google
Fonts CDN, so the network cannot break the typography mid-demo.

**The map degrades.** `MapView` counts tile errors; after six it drops the tile layer,
keeps rendering ward polygons and markers on a plain canvas, and tells the user why.
Markers are Leaflet `divIcon`s rather than images — no bundler asset paths to break,
and the colour encodes the priority band directly.

---

## 9. Deliberate non-choices

| Not used | Why |
|---|---|
| PyTorch / sentence-transformers | ~3 GB for a marginal similarity gain on text that is already canonicalised. Auto-detected if installed; never required. |
| Celery / Redis | One `BackgroundTask` covers the only deferrable work. A queue would be infrastructure with no job. |
| PostgreSQL | One file, one process, zero setup. The data volume is municipal, not web-scale. |
| An i18n library | 3 languages, ~120 strings. A dictionary with compile-time checking is smaller and cannot fail at runtime. |
| Tailwind v4 | A hackathon is the wrong place to debug a CSS-engine migration. |
| Google Fonts CDN | The venue network must not be able to change how the app looks. |

---

## 10. Where to look in the code

| To understand | Read |
|---|---|
| The scoring policy | `backend/app/config/priority_config.yaml` |
| The cross-lingual trick | `backend/app/pipeline/lexicon.py` |
| How stages compose | `backend/app/pipeline/orchestrator.py` |
| Clustering | `backend/app/pipeline/dedup.py` |
| The equity audit | `backend/app/services/equity.py` |
| Officer overrides | `backend/app/routers/admin.py` |
| The explainability UI | `frontend/src/components/shared.tsx` (`ScoreBreakdown`) |
