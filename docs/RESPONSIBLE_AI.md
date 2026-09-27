# Responsible AI — Model Card & Operating Statement

**NagarNetra** · PS-18 "CivicFix" · Global SDG + AI Hackathon 2026

---

## Scope statement

> **NagarNetra is a decision-support tool for municipal staff. It is not an autonomous
> enforcement system. Final decisions rest with officers.**

This sentence appears in the citizen app footer, the officer dashboard footer, the API
description at `/docs`, and `/api/meta`. It is not a disclaimer bolted on at the end —
it describes how the system actually behaves: **no complaint is ever closed, rejected,
downgraded or escalated by the software alone.**

---

## 1. Intended use

**In scope**

* Triage of inbound civic grievances for a municipal corporation.
* Grouping multiple reports of one real-world problem into one work item.
* Ranking a work queue by a published, auditable formula.
* Auditing whether service quality is equal across wards and across the languages
  citizens write in.

**Explicitly out of scope**

| Not for | Why |
|---|---|
| Automatically closing or rejecting complaints | The system has no "reject" path at all. Low confidence produces a human task, never a dismissal. |
| Identifying, profiling or scoring individual citizens | No identity is stored. Reporters are a salted hash of a device id. |
| Enforcement, penalties, prosecution or eviction | Nothing here establishes fact. It ranks attention. |
| Legal or medical judgement | Hazard flags are keyword and model signals, not assessments. |
| Deployment on real citizen data as-is | See §7 and `LIMITATIONS.md`. Demo authentication alone disqualifies it. |
| Any use outside Pune without re-grounding | The lexicon, localities, POIs and ward polygons are Pune-specific. |

---

## 2. What the AI does and does not decide

| Decision | Made by | Reviewable |
|---|---|---|
| Issue category | AI proposes; officer may override with a reason | ✅ audit log |
| Severity 1–5, hazard flags | AI extracts from text/photo | ✅ shown with confidence and source |
| Language of the complaint | Rule-based script + function-word detection | ✅ shown to the citizen |
| Map location | GPS → EXIF (consented) → geocoder → locality → **human** | ✅ officer can re-pin |
| Whether two reports are the same problem | AI merges only above a high threshold; the ambiguous band goes to a human | ✅ reversible, audited |
| **Priority score** | **Not the AI.** Published arithmetic over AI-extracted features | ✅ full breakdown shown |
| **SLA deadline** | **Not the AI.** Category + hazard table in config | ✅ published |
| Status, assignment, closure | **Officer only.** The AI cannot advance a status | ✅ public timeline |

The split matters. An officer who disagrees with a score can read the six lines of
arithmetic that produced it, identify the input they dispute, and correct *that input*.
A model that emitted "87" could only be argued with.

---

## 3. No silent rejection

The single strongest Responsible-AI property of this system: **there is no code path
that discards a citizen's report.**

* Every submission gets a ticket code before any AI runs.
* If the classifier is unsure → `low_confidence_category` review task.
* If nothing recognisable was extracted → `unparsed` review task.
* If the location cannot be resolved → `missing_location` review task, and the citizen
  is told an officer will pin it.
* If two reports might be the same → `duplicate_candidate` review task showing both.
* If the entire pipeline throws → the report is kept, flagged for manual handling, and
  the citizen gets an honest message. The API returns 201, not 500.

On the held-out set, **10.4% of complaints were routed to a human**. That is not a
failure rate — it is the system declining to guess. The review queue is a *deferral*
queue, not a rejection queue, and the UI says so.

The word "rejected" does not appear in any citizen-facing message. A duplicate is told
*"N others have reported this. Your report has been added and increased its priority."*

---

## 4. Human oversight

**Every override requires a written reason.** This is enforced at the API layer
(`ReasonedAction`, minimum 8 meaningful characters) and there is no UI path around it.
The reason, the actor, the timestamp, the before value and the after value are written
to `audit_log`.

**`audit_log` is append-only.** No code in the product updates or deletes a row in that
table. An override an officer could hide would not be accountability.

Officers can: correct a category, pin or release a priority band, merge two issues,
split a report back out of a cluster, set a location, change status, route to a
department, and switch the equity adjustment on or off. All eleven actions are audited.

Nothing is destructive. "Merge" sets `merged_into_id` and moves report links; both
issue rows survive and the merge is reversible.

---

## 5. Transparency

| Shown to | What |
|---|---|
| **Citizen** | Category, severity, confidence %, *which system decided* ("Claude" / "Offline classifier" / an officer's name), the exact matched words, the full priority breakdown, the SLA deadline, what PII was removed, and — if applicable — that a human will review it. |
| **Officer** | All of the above, plus every report in the cluster with its own confidence, the complete 8-stage pipeline trace (output, confidence, source, milliseconds per stage), the dedup score and distance, and the issue's full audit history. |
| **Anyone** | The complete scoring policy, served verbatim at `/api/meta/policy`. The taxonomy at `/api/meta`. The equity audit's thresholds and reasoning. |

Confidence is never hidden and never rounded up. A complaint classified at 27% displays
27%.

---

## 6. Privacy

| Control | Implementation |
|---|---|
| **PII redaction before processing** | `pipeline/redact.py` masks phone numbers (incl. +91 / 0 prefixes), e-mail, Aadhaar-style 12-digit numbers, vehicle registrations and PAN — *before* the text is classified, logged, embedded or sent to any external model. |
| **Deliberate non-redaction** | PIN codes and house/plot numbers are **kept**. They are location, not identity, and removing them would make the complaint useless for the purpose the citizen filed it. |
| **Encryption at rest** | Raw text is Fernet-encrypted (key derived from `SECRET_KEY`). It is never returned by any endpoint — verified by an explicit test. |
| **Photo metadata** | EXIF is stripped by re-encoding from pixel data, not by renaming the file. GPS is read **only** when the citizen ticks the consent box, and the UI says what it did either way. |
| **Reporter identity** | A salted SHA-256 of a client-generated device id. Enough to count distinct citizens; not enough to identify one. No names, no accounts, no phone numbers stored. |
| **External calls** | Only the redacted copy ever leaves the process, and only when an LLM provider is configured. The default configuration makes zero external AI calls. |
| **Retention** | The prototype retains everything for the life of the demo database. A deployment would need a retention schedule; see `LIMITATIONS.md`. |

**Known gap:** regex redaction is a safety net, not a guarantee. Free text can carry
identity in ways patterns miss ("the corner house opposite the temple, the retired
schoolteacher"). Encryption at rest is the second line of defence; the third would be
access control, which this prototype does not have.

---

## 7. Fairness

Fairness is a **dashboard page**, not a paragraph in a report.

**Ward parity.** Median time-to-resolve and SLA breach rate per ward against the city
median. A ward is flagged when its median is ≥1.5× the city median, or its breach rate
exceeds the city rate by ≥15 percentage points.

**Language parity.** The same measurement split by the language the citizen wrote in —
because a system that quietly serves English complaints faster is unfair even if every
ward looks equal.

**Model fairness.** Classification accuracy is reported *per language* on the held-out
set, and the dashboard additionally shows the live operational figure: how often an
officer had to correct the classifier, per language. If this tool works worse in
Marathi than in English, that is a fairness defect and it belongs on screen.

**Small samples are never flagged.** A group needs ≥3 resolved issues before it can be
called under-served. Declaring a ward "neglected" on the strength of two complaints
would be its own injustice.

### The equity adjustment, and its risks

Flagged wards receive **+6 priority points** (out of 100). Deliberately small: it nudges
a queue, it does not override a live wire.

Honest risks, stated because they are real:

* **It is a proxy.** Slow resolution may reflect genuinely harder problems rather than
  neglect. The adjustment treats the symptom.
* **It can create a feedback loop.** Boosting a ward improves its metrics, which can
  un-flag it, which removes the boost. The threshold hysteresis is untuned.
* **It redistributes attention.** Points given to one ward are attention taken from
  another. That is a political choice, which is exactly why it is **visible in every
  score breakdown and switchable by a named officer with a logged reason** — rather than
  a constant buried in a model.

---

## 8. Known failure modes

| Failure | What happens | Mitigation |
|---|---|---|
| Model and keyword rules disagree | Confidence is cut; complaint goes to a human | Margin-based tie-break picks the more defensible pre-fill |
| Unknown vocabulary / code-mixing beyond the lexicon | Low confidence → review | Lexicon is extensible; the gap is visible in per-language metrics |
| Over-merge (two different problems joined) | Officer splits the report out; both survive | High threshold, hard gates, reversible, audited |
| Under-merge (duplicates stay separate) | Extra work orders — wasteful, not harmful | Deliberately preferred over over-merging |
| Location wrong or absent | Review task asking for a pin | Four-step resolution ladder; never a guess |
| LLM unreachable / malformed / slow | Offline classifier answers; UI shows the source | Schema validation + one retry + fallback |
| Nominatim down or rate-limited | Locality-centroid fallback, then review | 1 req/s limiter, SQLite cache |
| Photo is not an image | Rejected politely; the complaint proceeds | Validated by decode, not by extension |
| Devanagari text in logs on a Windows console | — | stdout/stderr forced to UTF-8 at startup |

---

## 9. Data provenance

| Source | Role | Note |
|---|---|---|
| `data/synthetic_complaints.csv` | Primary training + evaluation corpus | **100% synthetic.** 430 complaints, 4 languages, 42 planted duplicate groups with ground-truth cluster ids. Deterministic seed. No real complaint, name or number. |
| NYC 311 (NYC Open Data) | English vocabulary breadth | 368 distinct real civic descriptors, down-weighted 3:1 so the model cannot drift into being English-only. |
| `data/wards.geojson` | Ward boundaries | **Synthetic.** Voronoi tessellation of 12 real Pune locality centroids. Not PMC electoral wards; disclosed wherever drawn. |
| `data/pois.csv` | Schools/hospitals for the vulnerability bonus | **Synthetic**, fictional facilities placed inside real localities. |
| OpenStreetMap / Nominatim | Map tiles and geocoding | ODbL; usage policy respected in code. |

Full list with licences: [`DISCLOSURES.md`](DISCLOSURES.md).

---

## 10. Evaluation summary

Held out **by cluster**, never by row.

| Metric | Result |
|---|---|
| Classification accuracy (en / hi / mr / Hinglish) | 100% each, macro-F1 1.000 |
| Cross-validated macro-F1 (training corpus) | **0.951 ± 0.030** ← the sober number |
| Dedup precision (automatic) | **1.000** — zero false merges |
| Dedup F1 (automatic → with officer confirmation) | 0.795 → 1.000 |
| Triage work removed | 18.8% automatic, 24.0% with confirmation (dataset maximum) |
| Complaints routed to a human | 10.4% |

> **The 100% figure must not be quoted without its caveat.** The test split is synthetic
> and shares phrasing patterns with training. It demonstrates that the pipeline is
> sound; it is **not** a real-world accuracy claim. The application's AI Health page
> renders this caveat on screen, next to the number.

Details and method: [`EVALUATION.md`](EVALUATION.md).

---

## 11. What would have to change before real deployment

1. Replace demo authentication with the corporation's identity provider, and add
   role-based access control.
2. Validate on real, labelled municipal complaints — and re-measure per-language
   fairness on that data, not on ours.
3. Replace the synthetic ward polygons with licensed official boundaries.
4. Define and implement a data retention and deletion schedule.
5. Independent review of the priority weights with the departments they affect, and a
   published change process for `priority_config.yaml`.
6. A citizen-facing appeals route: today a citizen can see *why*, but cannot formally
   contest a classification.
7. Load, security and accessibility testing.

---

**Maintainer responsibility.** If this system is ever pointed at real complaints, the
people operating it own its outputs. The design goal throughout was to make that
ownership *possible* — by ensuring every automated decision is visible, explained,
attributable and reversible.
