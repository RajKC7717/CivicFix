# NagarNetra — Build Plan

**Challenge:** PS-18 "CivicFix" — Intelligent Citizen Grievance Triage, Deduplication and Accountability
**Event:** Global SDG + AI Hackathon 2026, BV(DU) COEP Pune · Safe & Smart Communities track
**SDGs:** 11 (Sustainable Cities & Communities) + 16 (Peace, Justice & Strong Institutions)

> *NagarNetra* (नगरनेत्र, "the city's eye") turns scattered citizen complaints into a
> single, ranked, accountable work queue for a municipal corporation.

---

## 1. Positioning — the one-sentence pitch

Indian city grievance portals fail not because citizens do not report, but because
**100 reports of the same pothole arrive as 100 tickets in 3 languages, get triaged by
hand, and nobody can tell which ward is being ignored.** NagarNetra collapses reports into
*issues*, ranks them with a formula an officer can read, and publishes an equity audit that
makes neglect visible.

Three things make it more than a form plus a map:

1. **"One issue, many voices."** Cross-lingual deduplication. A Marathi voice note and a
   Hinglish text about the same pothole become *one issue with a count of 2*, not two tickets.
   The citizen is never told "rejected" — they are told "12 others reported this, your report
   raised its priority."
2. **Explainable priority.** The AI only *extracts features*. The score is a transparent
   weighted sum defined in `priority_config.yaml` that an officer (or a journalist, or an RTI
   applicant) can read and audit. Every score ships with its arithmetic.
3. **Equity audit.** Per-ward and per-language resolution-time and SLA-breach parity, with an
   optional, visible, toggleable priority boost for under-served wards. This is the SDG-16
   accountability half that most civic apps skip.

---

## 2. Decisions made up front (defaults chosen, not asked)

| # | Decision | Rationale |
|---|---|---|
| D1 | **No PyTorch. Deterministic offline NLP is the primary path.** | The build machine has 3.6 GB free disk; `sentence-transformers` plus torch is ~3 GB. More importantly the brief demands the app "fully work with `LLM_PROVIDER=none`" on venue Wi-Fi. A pinned, CPU-only, ~40 MB stack is *more* feasible (criterion 5) and removes the biggest demo risk. `requirements-ml.txt` documents the neural upgrade and the code auto-detects it — see D2. |
| D2 | **Pluggable `Embedder` interface** (`pipeline/embed.py`). | `SentenceTransformerEmbedder` is used automatically *if installed*; otherwise `LexicalEmbedder` (TF-IDF char n-grams over lexicon-normalised English). Same call site, so the upgrade is `pip install -r requirements-ml.txt` with zero code change. |
| D3 | **Cross-lingual dedup works by embedding `summary_en`, not raw text.** | Raw "कात्रज डेअरी समोर मोठा खड्डा" and "Katraj dairy ke saamne bada gaddha" share almost no characters. Both normalise to an English summary containing *pothole, katraj, dairy*. So dedup is cross-lingual even with a purely lexical encoder. This is what makes D1 safe. |
| D4 | **A hand-built civic lexicon plus Devanagari transliterator** (`pipeline/lexicon.py`) is core IP, not a stopgap. | It powers offline language ID (en/hi/mr/hinglish), the offline `summary_en`, and offline classification features. It is auditable — an officer can read *why* a word mapped to a category, which the Responsible-AI criterion rewards. |
| D5 | **Wards = Voronoi tessellation of 12 real Pune locality centroids, clipped to the Pune bbox.** | No Pune ward GeoJSON with an unambiguous licence was available in time. Voronoi over *real* coordinates gives gap-free, non-overlapping, geographically plausible polygons. Disclosed as synthetic in `DISCLOSURES.md` and in the UI. Swappable: drop a real GeoJSON at `data/wards.geojson` and it is used as-is. |
| D6 | **NYC 311 sample fetched from NYC Open Data's Socrata API**, not Kaggle. | No login, no multi-GB download, explicit public terms of use. `scripts/fetch_nyc311.py` caches rows to `data/nyc311_sample.csv`; training degrades gracefully to synthetic-only when offline. |
| D7 | **Demo auth is a signed token over a hardcoded officer list**, clearly labelled demo-only. | Real SSO is out of scope for a prototype; pretending otherwise would be a Responsible-AI red flag. A banner in the UI says so. |
| D8 | **SQLite plus FastAPI BackgroundTasks. No Celery, Redis or Postgres.** | One process, one file, one command. Feasibility criterion. |
| D9 | **Self-hosted fonts via `@fontsource`**, no Google Fonts CDN at runtime. | Venue Wi-Fi must not be able to break the typography mid-demo. |
| D10 | **Raw complaint text is encrypted at rest**; only redacted text ever leaves the process. | Fernet key derived from `SECRET_KEY`. Satisfies the privacy requirement literally, not just in the README. |
| D11 | **Tailwind v3.4 (not v4)**, React Router v6, Recharts 2. | Stable, well-trodden versions. A hackathon is the wrong place to debug a CSS-engine migration. |

---

## 3. Architecture

```
            +---------------------- CITIZEN (mobile-first PWA) ----------------------+
            |  text · voice (Web Speech API hi-IN/mr-IN/en-IN) · photo · GPS/pin/landmark |
            +-----------------------------------+------------------------------------+
                                                | POST /api/complaints (multipart)
                                                v
  +--------------------------- INGEST (synchronous, target <200 ms) --------------------------+
  |  1. persist Report + ticket code  ->  2. PII redaction  ->  3. enqueue BackgroundTask      |
  |  the citizen gets a ticket immediately - nothing is ever rejected                          |
  +-----------------------------------+--------------------------------------------------------+
                                      v
  +------------------------ PIPELINE (orchestrator.py, every stage logged) --------------------+
  |  redact -> understand -> image -> geocode -> ward -> dedup -> priority -> sla               |
  |              |  LLM (JSON      | multi- | GPS >     | point- | embed + | weighted           |
  |              |  schema)        | modal  | EXIF >    | in-    | geo +   | formula            |
  |              |  v retry v      | v skip | Nominatim | polygon| time    | (yaml)             |
  |              |  TF-IDF+LogReg  |        | v review  | v unkn.| v review|                    |
  |              +-- every stage writes {output, confidence, source, ms} to PipelineStageLog ---|
  +-----------------------------------+--------------------------------------------------------+
                                      v
  +------ Issue (cluster) ------+   +------- ReviewTask -------+   +------- AuditLog -------+
  | n Reports · priority · SLA  |   | low-conf · dedup band ·  |   | every officer override |
  | status timeline · assignment|   | no location · unparsed   |   | with a written reason  |
  +--------------+--------------+   +------------+-------------+   +-----------+------------+
                 +-------------------------------+-----------------------------+
                                                 v
             +--------------- OFFICER DASHBOARD (desktop) ----------------+
             | cluster map · priority queue + score breakdown · review    |
             | queue · SLA analytics · EQUITY AUDIT · AI HEALTH · audit   |
             +------------------------------------------------------------+
```

**Why ingest is synchronous but the pipeline is not:** the citizen must get a ticket ID in
under a second even if Nominatim is down or the LLM is slow. The report row is written first;
the pipeline then enriches it. A failed pipeline stage degrades the row, it never loses it.

---

## 4. Data model (SQLite / SQLAlchemy 2.0)

| Table | Purpose | Key columns |
|---|---|---|
| `reports` | One citizen submission. **Never deleted, never merged away.** | `ticket_code`, `issue_id`, `raw_text_encrypted`, `redacted_text`, `summary_en`, `language`, `channel`, `lat`/`lon`, `location_text`, `ward_id`, `photo_path`, `category`, `sub_issue`, `severity`, `hazard_flags`, `confidence`, `ai_source`, `dedup_decision`, `dedup_score`, `needs_review`, `status` |
| `issues` | A cluster of reports = one real-world problem. The unit of work. | `issue_code`, `category`, `status`, `lat`/`lon`, `ward_id`, `report_count`, `priority_score`, `priority_band`, `priority_breakdown`, `sla_hours`, `sla_deadline`, `sla_breached`, `department`, `resolved_at` |
| `status_events` | Public timeline (Received, Verified, Assigned, In progress, Resolved). | `issue_id`, `from_status`, `to_status`, `actor`, `note` |
| `review_tasks` | Human-in-the-loop queue. Four kinds. | `kind`, `report_id`, `payload`, `status`, `resolved_by`, `resolution` |
| `audit_log` | Every override: who / what / before / after / **why** / when. | `actor`, `action`, `entity_type`, `entity_id`, `before`, `after`, `reason` |
| `pipeline_stage_logs` | Per-stage output, confidence, source, latency. Feeds AI Health and explainability. | `report_id`, `stage`, `output`, `confidence`, `source`, `duration_ms` |
| `feedback` | Citizen rating after closure. | `issue_id`, `report_id`, `rating`, `comment` |
| `wards` | Ward metadata. | `code`, `name`, `zone`, `population` |
| `pois` | Schools and hospitals for the vulnerable-location bonus. | `name`, `kind`, `lat`/`lon` |
| `geocode_cache` | Nominatim results; the 1 req/s policy is honoured. | `query_hash`, `lat`/`lon`, `display_name`, `source` |
| `departments` | Routing targets. | `code`, `name`, `categories` |
| `settings` | Runtime toggles (e.g. the equity boost on/off). | `key`, `value` |

---

## 5. API surface

**Public / citizen**

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/complaints` | Submit (multipart: text, language, lat, lon, location_text, photo, consents). Returns ticket, category, explanation and cluster message. |
| GET | `/api/complaints/{ticket_code}` | Track one report: status timeline, category with confidence and source, cluster size. |
| POST | `/api/complaints/{ticket_code}/feedback` | Rate the fix after closure. |
| GET | `/api/public/stats` | Homepage counters (issues, resolved, median days, citizens joined). |
| GET | `/api/public/map` | Anonymised open issues for the public map. |

**Auth**

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/auth/login` | Demo officer login, returns a bearer token. |
| GET | `/api/auth/me` | Current officer. |

**Officer (bearer token required)**

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/admin/issues` | Filter by category/ward/status/band/age/breached; sorted by priority. |
| GET | `/api/admin/issues/{id}` | Full detail: all reports, score breakdown, timeline, stage logs, audit trail. |
| PATCH | `/api/admin/issues/{id}/status` | Advance status. |
| PATCH | `/api/admin/issues/{id}/assign` | Route to a department. |
| POST | `/api/admin/issues/{id}/override-category` | **Reason mandatory**, writes to the audit log, recomputes priority. |
| POST | `/api/admin/issues/{id}/override-priority` | Manual band pin, reason mandatory. |
| POST | `/api/admin/issues/{id}/merge` | Merge two issues (reason). |
| POST | `/api/admin/reports/{id}/unmerge` | Split a report back out into its own issue (reason). |
| GET | `/api/admin/review` | Review queue, grouped by kind. |
| POST | `/api/admin/review/{id}/resolve` | Confirm or correct the category, set a map pin, merge or separate. |
| GET | `/api/admin/audit` | Paginated audit log. |
| GET/PATCH | `/api/admin/settings` | Equity-boost toggle and similar. |
| POST | `/api/admin/demo/reset` | `DEMO_MODE` only: reseed a clean dataset. |

**Analytics**

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/analytics/sla` | Open vs resolved, breaches by department and ward, median time-to-resolve, backlog ageing. |
| GET | `/api/analytics/equity` | Per-ward and per-language parity vs the city median, flags, AI accuracy by language. |
| GET | `/api/analytics/ai-health` | Held-out evaluation (accuracy/F1 by language, dedup P/R/F1, geocode rate, p50/p95 latency) plus live counters. |

---

## 6. File tree

```
nagarnetra/
+- backend/
|  +- app/
|  |  +- main.py  db.py  models.py  schemas.py  security.py
|  |  +- config/    settings.py · priority_config.yaml · categories.py
|  |  +- pipeline/  orchestrator.py · redact.py · lexicon.py · understand.py
|  |  |             fallback_clf.py · image.py · geocode.py · ward.py
|  |  |             embed.py · dedup.py · priority.py · sla.py
|  |  |             +- llm/ base.py · anthropic_provider.py · gemini_provider.py
|  |  |                     openai_provider.py · none_provider.py
|  |  +- services/  audit.py · analytics.py · equity.py · demo.py
|  |  +- routers/   complaints.py · admin.py · analytics.py · public.py · auth.py
|  +- tests/        test_redact · test_lexicon · test_dedup · test_priority
|                   test_sla · test_geocode_cache · test_ward · test_api
+- frontend/src/
|  +- citizen/      Home · Report · Ticket · Track · PublicMap
|  +- admin/        Login · Dashboard · IssueDetail · Review · SLA · Equity · AIHealth · Audit
|  +- components/   ui/ (Button, Card, Badge, Modal, Toast, ...) · MapView · ScoreBreakdown
|  +- i18n/         en.ts · hi.ts · mr.ts · index.tsx
|  +- lib/          api.ts · auth.ts · format.ts · types.ts
+- data/    synthetic_complaints.csv · wards.geojson · pois.csv · nyc311_sample.csv
+- scripts/ generate_synthetic.py · fetch_nyc311.py · build_wards.py
|           train_fallback.py · evaluate.py · seed_db.py
+- docs/    ARCHITECTURE · RESPONSIBLE_AI · EVALUATION · IMPACT
|           DISCLOSURES · LIMITATIONS · DEMO_SCRIPT
+- README.md  PLAN.md  docker-compose.yml  run.sh  run.ps1  Makefile  .env.example
```

*Deviations from the brief's suggested tree:* added `pipeline/lexicon.py` (D4),
`pipeline/embed.py` (D2), `services/`, `routers/auth.py`, and `run.ps1` (the build and demo
machine is Windows). Everything else matches.

---

## 7. Milestones

| ID | Milestone | Exit criteria |
|---|---|---|
| **M0** | Scaffold | `run.ps1` starts both servers; `/api/health` green; SQLite schema created; README quotes PS-18. |
| **M1** | Data | 400+ synthetic complaints in 4 languages, 12 wards, 9 categories, planted duplicate groups with ground-truth cluster IDs, 2 deliberately under-served wards; `wards.geojson`; `pois.csv`; NYC 311 sample. |
| **M2** | Core pipeline | All 8 stages, each independently testable, each with a fallback. `POST /api/complaints` works end-to-end with `LLM_PROVIDER=none`. Unit tests green. |
| **M3** | Citizen app | Report (text/voice/photo/GPS/pin/landmark), ticket with explanation and "N others reported this", tracking timeline, post-closure rating. Three languages. |
| **M4** | Admin dashboard | Cluster map, priority queue with breakdown cards, review queue with reasoned overrides, status and assignment, SLA charts. |
| **M5** | Equity · AI Health · Audit | Ward and language parity with flags, toggleable equity boost, AI health page, full audit trail. |
| **M6** | Evaluation and docs | `evaluate.py` produces real numbers; all seven docs written with those numbers filled in. |
| **M7** | Demo hardening | `DEMO_MODE` reset, pre-cached geocodes and LLM responses for the scripted inputs, error/loading/empty states everywhere, full offline run verified. |
| **S** | Stretch (only after M7) | Image severity cues · councillor weekly ward report · PWA offline capture. |

Commit after every milestone. Tests run before every commit.

---

## 8. Risk register

| Risk | Mitigation |
|---|---|
| No internet at the venue | Everything works with `LLM_PROVIDER=none`; the geocode cache is pre-warmed; fonts are self-hosted; the map degrades to a plain-canvas ward renderer if OSM tiles fail. |
| No API key | The default provider is `none`. The LLM is an *enhancement*, never a dependency. |
| Web Speech API unsupported in the demo browser | Voice is explicitly a convenience; the textarea always works and the UI says so. |
| Nominatim rate limit or outage | 1 req/s limiter, SQLite cache, bounded retries, then the review queue — never a crash. |
| Dedup over-merges | The middle confidence band goes to a human; officers can unmerge; nothing is ever deleted. |
| Demo laptop is slow | No torch, no model downloads at runtime, SQLite, `DEMO_MODE` preseeded. |

---

## 9. Judging-criterion traceability (completed at M7 in README)

| Criterion | Pts | Where it lives |
|---|---|---|
| SDG impact | 25 | Three-language plus voice intake, equity audit, `docs/IMPACT.md` outcome metrics |
| Technical execution | 25 | Eight-stage pipeline each with a fallback, test suite, zero-network demo mode |
| Innovation | 15 | Cross-lingual "one issue, many voices" clustering, explainable priority, equity audit |
| Responsible AI | 15 | No silent rejection, review queue, reasoned overrides plus audit log, PII redaction and encryption at rest, per-language fairness evaluation, model card |
| Feasibility | 10 | One command, one laptop, no GPU, no running cost offline, PMC adoption path in `IMPACT.md` |
| Demo and communication | 10 | `docs/DEMO_SCRIPT.md`, seeded deterministic data, reset button |
