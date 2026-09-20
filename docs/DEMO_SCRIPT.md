# NagarNetra — Demo Video Guide

**PS-18 "CivicFix"** · Global SDG + AI Hackathon 2026 · SDG 11 + 16

Everything you need to record a 3-minute demo that works every time: what to run,
what to type, what to point at, and what to say.

> **The one rule:** the whole demo runs with `LLM_PROVIDER=none` — no API key, no
> internet. If the venue Wi-Fi dies mid-recording, nothing on screen changes except
> the map tiles, and the app tells you that itself. Do not "fix" this by adding a key.

---

## 0. Start the project

**One command, from the repo root:**

```powershell
./run.ps1            # Windows PowerShell
```
```bash
./run.sh             # macOS / Linux / Git Bash
```

The first run sets everything up (virtualenv, dependencies, ward polygons, synthetic
corpus, trained classifier, seeded database) and then starts both servers. Later runs
just start them. Add `-Reseed` / `--reseed` to rebuild the demo data at start-up.

<details><summary>Or start the two servers by hand</summary>

```bash
# Terminal 1 - API
.venv/Scripts/python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000

# Terminal 2 - web app
cd frontend && npm run dev
```
</details>

| What | URL |
|---|---|
| Citizen app | <http://localhost:5173> |
| Officer dashboard | <http://localhost:5173/admin/login> — `officer` / `officer` |
| API docs (Swagger) | <http://127.0.0.1:8000/docs> |

Confirm it is alive before you hit record:
```bash
curl http://127.0.0.1:8000/api/health
```
You want `"status":"ok"`, `"offline_classifier_trained":true`, `"demo_mode":true`.

---

## 1. Pre-flight checklist (do this every time)

- [ ] **Reset the data.** Officer dashboard → **Reset demo data** (top right). Takes ~10 s.
      You should land on **430 reports → ~354 issues, ~47 items in Human review**.
- [ ] **Sign in once before recording** so the login screen is not in your 3 minutes
      (or record the login — it is only 4 seconds and it shows the audit story).
- [ ] **Browser zoom 100%**, window 1600×1000 or larger for the dashboard.
- [ ] **Close other tabs.** Chrome with many tabs will make the map stutter.
- [ ] **Have the text snippets below in a scratch file** to paste — do not type
      Devanagari live, it is slow and error-prone on camera.
- [ ] **Allow location** when the browser asks, or plan to drop a map pin instead.
- [ ] If you want the voice demo: **test the microphone first** (see §5 — voice needs
      Chrome *and* internet). If either is missing, use the typed path; the script
      below works identically.

**Recording:** OBS Studio or Windows `Win+Alt+R`. 1080p, 30 fps. Record a single take
per section and cut — do not try to nail 3 minutes in one pass.

---

## 2. Text to paste (keep this open in Notepad)

| # | Paste this |
|---|---|
| **A** | `कात्रज डेअरी समोर मोठा खड्डा आहे, शाळेजवळ, दोन दिवसांपासून` |
| **B** | `Katraj dairy ke saamne bada gaddha hai, school ke paas` |
| **C** | `light nahi hai` |
| **D** | `Baner me kachra nahi uthaya, mera number 9822012345 hai` |

**A** is Marathi: *"There is a big pothole opposite Katraj dairy, near the school, for two days."*
**B** is the same pothole in romanised Hinglish, written by a different person.

**Coordinates**, if you drop a pin instead of using GPS: Katraj is around
**18.4575, 73.8677**. Zoom into south Pune and click roughly there — it does not
need to be exact.

---

## 3. The 3-minute shot list

Timings are targets. Each row: what you do, then what you say.

### [0:00–0:20] The problem

**Show:** the citizen homepage at <http://localhost:5173>.

> "Indian cities do not have a reporting problem. They have a *triage* problem.
> A hundred people report the same pothole in three languages, and a hundred
> separate tickets land on one officer's desk. NagarNetra is built for PS-18:
> it turns those voices into one accountable issue."

**Point at** the green banner: *"430 citizen reports have been grouped into 354 real
issues — 17.7% less manual triage, and no citizen was ever told their report was a
duplicate."*

---

### [0:20–1:00] One issue, many voices — the core demo

**Click** *Report an issue*.

**Step 1 — Marathi complaint with a photo and GPS**
1. Switch the language toggle to **मराठी** (top right). The whole UI changes.
2. Paste **A** into the textarea. *(Or click "बोलून सांगा" and speak it — see §5.)*
3. Optionally attach any photo.
4. Click **"माझे सध्याचे ठिकाण घ्या"** (use my location), or drop a pin near Katraj.
5. Click **तक्रार पाठवा** (send).

**Show the result page** and point at, in this order:
- the **ticket number**
- **Category: Pothole / Road damage**, **Severity 4/5**
- the **confidence bar (~89%)** and the chip saying **Offline classifier**
- **"Why this category"** → the matched Marathi words `खड्ड`, `शाळ`, `मोठ`
- the **priority breakdown**: `Severity 4/5 +32 · Near a school +10 · 1 report +4.2`

> "It read Marathi with no translation API and no model download. Severity four,
> near a school. And notice it shows *which words* convinced it — that is a keyword
> match an officer can argue with, not a black box."

**Step 2 — the same pothole, different person, different language**
1. Click **Report another issue**.
2. Switch language back to **English**.
3. Paste **B**. Drop a pin in the same place (or use GPS again).
4. Send.

**This is the money shot.** Point at the blue card:

> **"2 people have reported this same problem. Your report has been added to issue
> ISU-… and raised its priority — it was not filed as a duplicate."**

> "Marathi and Hinglish. Zero words in common. Same issue. The citizen is never told
> 'rejected' — they are told they were heard, and their report made it more urgent.
> That is the difference between deduplication and dismissal."

**Point at** the breakdown line changing to **`2 reports +6.7`**.

> "The count is log-scaled on purpose, so one organised group cannot brigade a street
> to the top of the queue."

---

### [1:00–1:25] Nothing is ever rejected

**Step 3 — a complaint the AI cannot place**
1. New report. Paste **C** — `light nahi hai`. Give it **no location at all**.
2. Send.

**Show:** *"Your complaint has been registered. We could not pinpoint the location,
so an officer will confirm it on the map."*

> "Three words, no GPS. It still got a ticket. The system knew it was a streetlight
> problem but not *where* — so instead of guessing or discarding it, it put it in
> front of a human."

**Optional, 8 seconds — privacy.** Paste **D**, send, then open the ticket:
the stored text reads `mera number [PHONE] hai`.

> "Personal numbers are stripped before anything is classified, logged, or sent
> anywhere. The original is encrypted at rest and never leaves the process."

---

### [1:25–2:10] The officer side

**Go to** <http://localhost:5173/admin> (sign in as `officer` / `officer` if needed).

**Show the priority queue.** Point at the four counters, then the list:
band colours, **"N voices"** chips, **"equity +"** chips, red **overdue** text.

> "One ranked queue. Every number here comes from a formula published in a YAML file
> the officer can read — the AI only extracts the features."

**Set the sort dropdown to *Most reported*** and open the issue at the top.

> Issue codes are regenerated on every reset, so do not memorise one — sorting by
> *Most reported* always puts the biggest cluster first. At the time of writing it is
> a 7-voice Yerawada pothole spanning all four languages.

> "Seven citizens. Four languages — English, Marathi, Hinglish and Hindi. One issue,
> one work order, one SLA clock."

**Scroll to** *Why this priority* and read one line aloud, then point at the
coloured source chips (`ai`, `citizens`, `map`, `policy`).

> "Severity came from the AI. The report count came from citizens. The school came
> from verified map data, not from the text. The SLA pressure came from policy.
> You can reproduce this number by hand."

**Click** *Human review* in the sidebar (badge shows **47**).

> "This is what the system does when it is unsure. Not a rejection queue — a
> deferral queue."

**Resolve one item on camera:** pick a *Low-confidence classification*, click
**Confirm the AI**, type a reason such as
`Photo and location confirm this is a road defect.` and save.

> "Every override needs a written reason. There is no way to change what the AI
> decided without leaving a record."

**Click** *Audit log* — your entry is at the top, with before → after and your reason.

---

### [2:10–2:45] The differentiator: equity

**Click** *Equity audit*.

> "A grievance system that only gets *faster* can still be unfair."

**Point at** the flagged rows:
- **Yerawada — 85.3 h median fix time, 2.25× the city median of 37.9 h, 79% SLA breach**
- **Kondhwa — 68.2 h, 1.8×, 84% breach**

> "Two wards are being served materially worse than the rest of the city. The system
> found that on its own and said so on the front page of the dashboard."

**Point at** *Language parity* and *AI accuracy by language*.

> "And it audits itself: how often an officer had to correct the classifier, split by
> the language the citizen wrote in. If this tool works worse in Marathi than in
> English, that is a fairness defect and it belongs on screen."

**Click** the **Equity boost: ON** button, then **Cancel** (or toggle it and show the
toast).

> "Flagged wards get a small, visible, switchable boost — six points, shown in every
> score breakdown. An officer can turn it off, and that decision is audited too."

---

### [2:45–3:00] Close honestly

**Click** *AI health*.

> "Held out from training: 100% classification accuracy on our synthetic test split
> across all four languages. **That number is high because the test data is synthetic
> and shares phrasing patterns with training — it is not a real-world accuracy claim,
> and the page says so.** The measurement that matters more is this one:"

**Point at** the deduplication card:

> "18.8% of triage work removed automatically, 24% once an officer confirms the
> flagged candidates — which is the theoretical maximum for this dataset. Precision
> 1.000: zero false merges. And a median pipeline latency of 14 milliseconds on a
> laptop, with no GPU and no API key."

**End on** the footer line:

> "Decision-support for municipal staff. Not an autonomous enforcement system. Final
> decisions rest with officers."

---

## 4. If you have 5 minutes instead of 3

Add these, in this order of value:

1. **The policy file.** `backend/app/config/priority_config.yaml` in an editor. Scroll
   the comments. *"This is the entire scoring policy. There is no hidden model."*
2. **A duplicate-candidate review item** — shows the two reports side by side and the
   merge/keep-separate choice.
3. **Split a report out** of a cluster (issue detail → *Split out*), proving merges are
   reversible and nothing is deleted.
4. **The pipeline trace** on an issue detail page → *Show detail*: eight stages, each
   with its source, confidence and millisecond timing.
5. **Kill the network** (turn off Wi-Fi) and submit another complaint. It still works;
   the map shows *"Offline map — street tiles are unreachable"* and carries on.

---

## 5. Voice input — read before you rely on it

The voice button uses the browser's **Web Speech API**.

| | |
|---|---|
| **Works in** | Chrome and Edge, desktop and Android |
| **Does NOT work in** | Firefox, Safari desktop, most in-app webviews |
| **Needs** | a working microphone **and an internet connection** — Chrome sends the audio to Google for recognition |

**This is the one part of the demo that needs the internet.** The app detects the
failure and shows *"Voice input is not available in this browser. Please type
instead — it works exactly the same."*

**Recommendation:** record the voice step separately, before the main take, when you
know the connection is good. If it fails, paste the text instead — the pipeline is
identical and nothing about the story changes. You can still say:

> "Voice is a convenience for citizens who find typing Devanagari slow. It is never a
> dependency — the text box always works, and the app says so when voice is
> unavailable."

To demo voice: set the UI language to मराठी first, so the recogniser is asked for
`mr-IN` rather than the browser default.

---

## 6. If something goes wrong on camera

| Symptom | What to do |
|---|---|
| Map is grey / tiles missing | Keep going. Say *"no internet at the venue — ward outlines still render, and the app says so."* It is a feature, not a failure. |
| Merge did not happen in step 2 | Your two pins were more than 150 m apart. Drop the second pin closer and resubmit. |
| Voice button missing | You are not in Chrome/Edge. Paste the text (§2). |
| Dashboard is empty | You reset while the API was restarting. Click **Reset demo data** again. |
| Numbers differ from this script | Expected — the equity and SLA figures shift slightly on each reseed. The *shape* of the story is stable: Yerawada and Kondhwa are always the flagged wards. |
| Everything is broken | `curl http://127.0.0.1:8000/api/health`. If that fails, restart Terminal 1. |

---

## 7. Regenerating the numbers

If you change the pipeline and want fresh figures on the AI Health page:

```bash
.venv/Scripts/python.exe scripts/evaluate.py     # held-out benchmark -> AI Health page
.venv/Scripts/python.exe scripts/seed_db.py --reset   # rebuild demo data from scratch
.venv/Scripts/python.exe -m pytest backend/tests -q   # 95 tests, run before every commit
```

`evaluate.py` replays the held-out complaints through the real pipeline in arrival
order and stores the result, so the dashboard is never showing a hand-written number.

---

## 8. The three sentences to land

If the recording gets cut short, make sure these three got said:

1. **"Marathi and Hinglish, zero words in common, one issue — and the citizen is told
   they were heard, not that they were a duplicate."**
2. **"The AI extracts features; the priority score is arithmetic an officer can read
   and argue with."**
3. **"It found two wards being served twice as slowly as the rest of the city, and put
   that on the front page instead of in a footnote."**
