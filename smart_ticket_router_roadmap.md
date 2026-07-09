# Smart Ticket Router — Build Roadmap

**Stack:** Python (FastAPI + Pydantic) · **Model:** Local, open-source via Ollama · **Interface:** CLI + Streamlit web form

## The unique angle: "grammar-constrained, self-repairing routing"

Most people who build this project write one prompt that says "return JSON" and hope the model listens. That approach breaks constantly with local open-source models, which are far less disciplined about output format than GPT-4/Claude. Rather than fight that with prompt engineering alone, this build leans into it and turns reliability into the actual engineering story:

1. **Grammar-constrained decoding** — Ollama's `format` parameter accepts a JSON Schema and forces the model to decode only tokens that produce syntactically valid JSON matching that schema. This isn't a prompt trick; it's a decoding-time constraint, so malformed JSON becomes structurally impossible, not just "less likely."
2. **Semantic validation** — Pydantic checks the syntactically-valid JSON against business rules the grammar can't enforce (enum values, string length, required non-empty reasoning).
3. **One-shot self-repair** — if Pydantic validation fails, the validation error is fed back to the model in a second call ("You returned X, but Y is required — fix it") rather than giving up.
4. **Deterministic fallback** — if repair also fails, the system never crashes or returns nothing; it returns a safe, clearly-labeled `Unclassified / Needs Human Review` object with the raw failure logged.

This four-layer stack is what you'll explain when a mentor asks "where does this fail and how do you know" (M4A4) and "why this approach over just prompting" (M4A2) — you chose it specifically because local models need it, which is a genuine, defensible design decision rather than a copied tutorial pattern.

Optional extra personality: give the project a name (e.g. **Routely** or **TicketSense**) and a fictional-but-specific home — "built for a 40-person SaaS company's support inbox" — with a real taxonomy (Billing, Account Access, Bug Report, Feature Request, Integration/API, General Inquiry) instead of generic placeholders. Concrete context makes the demo and the README feel like a product, not an exercise.

---

## 1. Architecture

```
                ┌─────────────────────┐
 Ticket text →  │  1. Fast-path rules  │──► obvious match (e.g. "reset password" → Account Access)
                │  (regex/keyword)     │        │
                └─────────┬────────────┘        │ no match
                          │                      ▼
                          ▼               ┌─────────────────────┐
                  skip LLM, return        │ 2. LLM call (Ollama) │
                  instantly                │  format=JSON Schema  │
                                           └─────────┬────────────┘
                                                     ▼
                                           ┌─────────────────────┐
                                           │ 3. Pydantic validate │
                                           └─────┬───────────┬────┘
                                             pass │           │ fail
                                                  ▼           ▼
                                          return result   4. one repair
                                                            retry call
                                                             │
                                                        pass │ fail
                                                             ▼      ▼
                                                    return result  fallback
                                                                  "Needs Review"
                          all paths → log {input, output, latency, path_taken} → analytics
```

Why the fast-path layer exists: it's a genuine hybrid-AI design choice, not just an LLM wrapper. It's free, instant, and 100% consistent for obvious tickets ("password reset", "invoice", "refund"), and it's your answer to "why not just keyword search?" (M4A2) — you *do* use keyword matching, but only where it's reliable, and hand off to the LLM exactly where keyword matching breaks down: tone, ambiguity, novel phrasing.

## 2. Data contract (the schema you enforce)

```python
from pydantic import BaseModel, Field
from typing import Literal

class TicketRoute(BaseModel):
    category: Literal[
        "Billing", "Account Access", "Bug Report",
        "Feature Request", "Integration/API", "General Inquiry",
        "Unclassified"
    ]
    priority: Literal["High", "Medium", "Low"]
    assigned_team: Literal[
        "Billing Ops", "Identity & Access", "Engineering",
        "Product", "Platform/API", "Customer Success", "Human Triage"
    ]
    reasoning: str = Field(min_length=10, max_length=280)
    confidence: float = Field(ge=0.0, le=1.0)
```

`confidence` is the piece that makes ambiguity handling explicit rather than hidden: if `confidence < 0.6`, the router overrides `assigned_team` to `Human Triage` regardless of what category the model guessed, and the `reasoning` field is required to name the runner-up category it considered. That single field is your answer for M4S5 (ambiguous ticket) and M4A5 (a real business outcome: fewer wrong auto-routes reaching the wrong team).

Pass the JSON-Schema version of this model straight into Ollama's `format` field so the constraint is enforced at decode time, not just requested in the prompt.

## 3. Prompt design

Keep the system prompt short, explicit, and separate tone from category:

```
You are a support ticket router. Read the ticket and classify it.

Rules:
- Judge CATEGORY by the technical substance of the request, ignoring tone,
  capitalization, profanity, or punctuation.
- Judge PRIORITY partly by urgency language and emotional intensity — an angry
  or all-caps message about a real outage is High priority even if a calm
  message about the same issue would be Medium.
- If the message is too short or vague to identify a real issue (e.g. one
  word, no noun/verb describing a problem), set category to "Unclassified",
  assigned_team to "Human Triage", confidence to 0.0, and explain in
  reasoning what information is missing.
- If the ticket could reasonably fit two categories, pick the better fit and
  name the other candidate in your reasoning, explaining the tiebreaker.
- Always return every field. Never leave reasoning empty.

Categories: Billing, Account Access, Bug Report, Feature Request,
Integration/API, General Inquiry, Unclassified.
```

Use temperature 0–0.2 for consistency (directly relevant to M4B1's "run it twice, compare outputs" test). Few-shot: include 2–3 short examples covering a calm ticket, an angry-tone ticket, and an ambiguous one, right in the system prompt — this is your answer to "why few-shot vs zero-shot" (M4A2): zero-shot local models drift on edge-case formatting; 3 examples anchor tone-handling and the ambiguity-reasoning pattern far more reliably than instructions alone.

## 4. The three mandated edge cases, explicitly

| Case | Input example | Expected behavior |
|---|---|---|
| Angry tone | "This is RIDICULOUS, nothing works and I've been waiting 3 days!!!" | Category driven by substance (likely Bug Report or General Inquiry depending on context given), priority pushed to High by urgency+tone, reasoning notes the tone influenced priority not category |
| Very short/vague | "broken" | category=Unclassified, assigned_team=Human Triage, confidence=0.0, reasoning states what's missing (no product/feature named) — never a crash, never a wild guess |
| Ambiguous | "I was charged twice but now I also can't log in" | Picks one category, reasoning explicitly names the second candidate (Billing vs Account Access) and states the tiebreaker (e.g. "billing issue mentioned first and is the actionable root cause") |

Build these three into your fixed test set so they run identically every demo — don't leave them to chance during the live mentor session.

## 5. Reliability engineering checklist (maps to M4B)

- Grammar-constrained JSON via Ollama `format` (syntax guaranteed)
- Pydantic validation (semantics guaranteed)
- One repair retry with the validation error appended to the prompt
- Deterministic fallback object if repair also fails — app never throws to the user
- Wrap the Ollama call in a try/except for "Ollama not running / model not pulled" — return a clear error message in the interface, not a stack trace (this is your local-model equivalent of the "invalid API key" test)
- No secrets to leak, since everything runs locally — but still put `OLLAMA_HOST` and `MODEL_NAME` in a `.env` file (not hardcoded) so you can demonstrate the practice and so the code is portable if you ever add a cloud fallback later
- Log every request: timestamp, input, path taken (fast-path/LLM/repair/fallback), latency, final output — this log is what you'll show for the consistency test (M4B1) and the before/after timing evidence (M4S7)

## 6. Interface

- **CLI** (`router_cli.py`): paste or pipe in ticket text, get pretty-printed JSON back plus latency. Fastest for your own iteration and for the mentor to batch-run the 20 sample tickets.
- **Streamlit web form** (`app.py`): single textbox, "Route Ticket" button, renders category/priority/team as colored badges and reasoning as plain text below. This is the piece a non-technical person can use with zero explanation (M4C2) — test it by handing it to someone who hasn't seen the project and watching whether they succeed unassisted.
- Both interfaces call the same underlying `route_ticket()` function — one core service, two front doors. That's the "reusable function/service" deliverable, and it's also why the CLI and web form will never disagree with each other.

## 7. Before/after timing evidence (M4S7)

1. Pick your 20 sample tickets (mix of categories, priorities, and the 3 edge cases).
2. Manual baseline: time yourself (or a colleague) reading and classifying all 20 by hand with a stopwatch, no AI. Record average seconds/ticket.
3. AI timing: your logging layer already records latency per ticket automatically — just average it across the same 20.
4. Present as a small table in the README: manual avg vs AI avg, plus total time for 20 tickets both ways. Local models are slower than hosted APIs, so also note this tradeoff honestly (no cost/no API key, but higher latency) — that honesty is itself a good answer for M4D4.

## 8. Two-week plan (for a real, spread-out commit history — M4D3)

| Days | Milestone | Commit checkpoint |
|---|---|---|
| 1–2 | Repo scaffold, Pydantic schema, `.env`, pull + test a couple of Ollama models for JSON reliability, pick one | `init project structure` / `add TicketRoute schema` |
| 3–4 | Fast-path keyword rules + unit tests for them | `add rule-based fast path` |
| 5–6 | Core `route_ticket()` function: Ollama call with schema-constrained format, Pydantic validation | `add LLM routing with schema enforcement` |
| 7 | Repair-retry loop + deterministic fallback + Ollama-down error handling | `add self-repair and fallback logic` |
| 8 | Logging layer (JSON lines or SQLite) capturing input/output/latency/path | `add request logging` |
| 9 | CLI interface | `add CLI` |
| 10 | Streamlit web form interface | `add web interface` |
| 11 | Build and run the 20-ticket test set + 3 edge cases; fix whatever breaks | `add test ticket set, fix edge cases` |
| 12 | Consistency test (same input, 5 min apart) + manual-vs-AI timing table | `add reliability + timing evidence` |
| 13 | README: setup, architecture diagram, demo GIF/screenshots, limitations, "what I'd do differently" | `write README and docs` |
| 14 | Buffer day: polish, re-run full 20-ticket demo end to end, rehearse answers to the M4A/M4D interview questions | `polish and final fixes` |

Commit at the end of each milestone (or more often) so the history shows steady progress rather than a single late dump.

## 9. Repo structure

```
smart-ticket-router/
├── README.md
├── .env
├── .gitignore
├── requirements.txt
├── app/
│   ├── schema.py        # Pydantic TicketRoute model
│   ├── fast_path.py     # keyword/regex pre-filter
│   ├── router.py        # route_ticket() core service
│   ├── ollama_client.py # wraps Ollama calls + repair retry
│   └── logger.py        # request logging
├── router_cli.py
├── app.py                # Streamlit form
├── tests/
│   ├── test_tickets.json   # 20 sample tickets + 3 edge cases
│   └── test_router.py
└── logs/
    └── requests.jsonl
```

## 10. README must include

- Setup steps: install Ollama, pull the model, `pip install -r requirements.txt`, create a `.env`
- How to run: CLI command and Streamlit command
- Architecture diagram (reuse the one above)
- Sample input → output JSON
- The before/after timing table
- A short "Limitations & what I'd do differently" section — genuine self-awareness reads far better to a mentor than a polished claim of perfection (M4D2/M4D4)
- A short "what I figured out beyond the brief" note — e.g. discovering and using Ollama's schema-constrained `format` parameter is a legitimate, specific answer to "what did you research beyond the instructions" (M4D5)

## 11. Rubric coverage map

| Rubric item | Where it's covered |
|---|---|
| M4A1–A5 (concept understanding) | Sections 1–3 give you the plain-English story, the "why this approach," and the failure-mode analysis to speak from |
| M4B1 consistency | temp=0–0.2, log and diff two runs 5 min apart |
| M4B2 edge cases | Section 4 |
| M4B3 failure without crash | try/except around Ollama calls, fallback object |
| M4B4 usable output | Streamlit badges + plain reasoning text |
| M4B5 no hardcoded secrets | `.env` for config even without a paid API key |
| M4C1–C4 (real problem, usable, right format, complete) | Fast-path + LLM + interfaces together form one end-to-end service |
| M4D1–D5 (reflection) | Sections 7, 10; keep a running notes file while building so answers are ready, not improvised |
| M4S1–S2 (valid JSON, all fields) | Grammar-constrained decoding + Pydantic |
| M4S3–S5 (edge cases) | Section 4 |
| M4S6 priority defensibility | Explicit priority rule in the prompt (Section 3) tied to urgency+tone language |
| M4S7 timing evidence | Section 7 |

---

Next step: scaffold the repo (Section 9) and get one Ollama model returning schema-constrained JSON reliably before building anything else — that's the riskiest part, so validate it first.

# Smart Ticket Router — Plan v2 (with IT-value add-ons, UI spec, test set, mentor prep)

This supersedes the day-by-day schedule in the original roadmap. Architecture details are in `system_architecture.md` and stay valid — this file adds four things: features that make the tool genuinely useful to an IT team (not just a demo), a concrete Streamlit visual design, a 20-prompt test set, and plain-English mentor-prep answers for the whole rubric.

## 1. Features that make this useful to an actual IT team

A router that only outputs JSON is a tech demo. A router an IT team would actually keep using needs to answer "so what happens next." These are ordered by effort-to-value; build Core first, add Stretch only if the 2-week schedule leaves room.

**Core add-ons**

- **Live stats dashboard** (a second Streamlit page): ticket volume by category/priority/team, repair-rate and fallback-rate, average latency by path. This turns your project from "a router" into "a router with a manager-facing view of what's flowing through support" — the single biggest thing that makes it look like a real tool rather than an exercise.
- **SLA flag on High priority**: every routed ticket gets a computed "respond within N hours" field (e.g. High = 2h, Medium = 8h, Low = 48h). A "Mark Resolved" button records resolution time; anything past its SLA shows as overdue, in red, on the dashboard. This is a real IT pain point (SLA breaches) solved with almost no extra code — it's just a timestamp comparison.
- **Correction feedback loop**: a "This was misrouted" button on any result lets whoever's testing pick the right category instead; logged to `corrections.jsonl`. You don't have to retrain anything live — the value is that you can show real evidence of *where* the model is wrong and say exactly what you'd fine-tune or add as a few-shot example next. This is your strongest, most concrete answer to "what would you do differently" and "where does it fail."
- **Duplicate ticket detection**: before routing, compare the new ticket text against the last 24h of logged tickets using simple text similarity (`difflib.SequenceMatcher`, no ML needed). If similarity is high, the response includes `"possible_duplicate_of": "<earlier ticket id>"`. Real IT teams lose real time to duplicate tickets; this is cheap to build and a strong "why this actually helps" talking point.

**Stretch add-ons** (only if Core is done early)

- **CSV batch import**: upload a CSV of tickets (e.g. exported from an inbox), get all of them routed and downloadable as a results CSV. Turns the tool from "type one ticket" into "clear a backlog."
- **Plain-English daily digest**: a button that feeds the day's logged tickets back into the same local model and asks for a 3-sentence summary ("18 tickets today, 4 High priority, mostly outages; Engineering team most loaded"). Reuses the same LLM infrastructure for a second job — a nice, low-effort way to show range.

## 2. Streamlit UI — visual design spec

Palette (only red, blue, black, grey — no green/amber, so color always means the same thing):

| Token | Hex | Meaning |
|---|---|---|
| `--rt-black` | `#111827` | Headings, primary text, header bar background |
| `--rt-grey-bg` | `#F7F8FA` | Page background |
| `--rt-grey-panel` | `#E5E7EB` | Card borders, dividers, sidebar background |
| `--rt-grey-muted` | `#6B7280` | Secondary text (reasoning, hints), Low-priority badge |
| `--rt-blue` | `#2563EB` | Primary action (buttons, links), Medium-priority badge, confidence bar fill |
| `--rt-red` | `#DC2626` | High-priority badge, SLA-overdue flag, error states |

Color-to-meaning is fixed and never overloaded: red = High/overdue/error, blue = action/Medium/info, grey = Low/neutral/secondary, black = text/structure. State that mapping once, visibly, in the UI (a small legend) so a first-time user never has to guess.

Layout:

- **Header bar**: full-width, black background, project name in white/blue bold (e.g. "Routely — Smart Ticket Router"), one-line tagline in grey.
- **Main panel, left**: a text area for the ticket, a "Route Ticket" button (blue, filled), and a small dropdown of the 3 mandated edge-case examples for instant demo re-runs.
- **Main panel, right**: the result card — a white card with a left border colored by priority (red/blue/grey), category and assigned team in bold black, priority as a colored pill, reasoning in grey italic below, and a thin horizontal confidence bar filled in blue. An expandable "Show raw JSON" toggle underneath renders the exact response in a monospace block for the technical audience/mentor.
- **Sidebar**: grey background, running stats — total routed, average latency, repair-rate %, fallback-rate %, and a small bar chart by category using a single blue ramp. High-priority-overdue count shown in red if non-zero.

Practical build note: use Streamlit's native theme file for the base palette (this is the "simple, idiomatic Streamlit" way, not heavy custom HTML) and layer a small CSS snippet only for the priority pills and header bar:

`.streamlit/config.toml`
```toml
[theme]
base="light"
primaryColor="#2563EB"
backgroundColor="#F7F8FA"
secondaryBackgroundColor="#E5E7EB"
textColor="#111827"
font="sans serif"
```

Pill/badge CSS (inject once via `st.markdown(..., unsafe_allow_html=True)`):
```css
.badge-high  { background:#DC2626; color:white; padding:2px 10px; border-radius:12px; font-weight:600; }
.badge-med   { background:#2563EB; color:white; padding:2px 10px; border-radius:12px; font-weight:600; }
.badge-low   { background:#6B7280; color:white; padding:2px 10px; border-radius:12px; font-weight:600; }
```

Keep it genuinely simple: one font, flat colors, generous spacing, no gradients or icons-for-decoration's-sake. That restraint is itself the "appealing" part — it reads as a real internal tool, not a hackathon theme.

## 3. 20 test prompts — full coverage set

Use this exact list for the mentor demo and for your own `tests/test_tickets.json`. It hits the 3 mandated edge cases, grammar/typo issues, and every other edge case worth showing.

| # | Ticket text | What it tests | Expected behavior |
|---|---|---|---|
| 1 | "I can't log into my account, it says invalid password even though I reset it yesterday." | Normal, clear case | Account Access / Medium |
| 2 | "Server is down for everyone, we are losing money every minute!!" | Known-High severity | Bug Report or Platform/API, High |
| 3 | "This is RIDICULOUS, nothing works and I've been waiting 3 days!!!" | **Mandated: angry tone** | Category by substance, priority raised by urgency, not by profanity/caps |
| 4 | "broken" | **Mandated: very short/vague** | Unclassified → Human Triage, confidence 0, reasoning states missing info |
| 5 | "I was charged twice but now I also can't log in" | **Mandated: ambiguous** | One category chosen, reasoning names the runner-up and the tiebreaker |
| 6 | "wen fix bug plz its verry anoying and i cant acess my acount" | Grammar/spelling issues | Still classified correctly (Account Access/Bug) despite typos |
| 7 | "" (empty) | Empty input | Rejected before hitting the model (HTTP 422 / "please enter a ticket"), not sent to the LLM |
| 8 | A 300+ word rambling message describing three unrelated issues at once | Very long, multi-issue input | Picks the dominant issue, reasoning notes multiple topics were present |
| 9 | "¿Por qué no puedo acceder a mi cuenta?" | Wrong/non-English language | Best-effort classification or Unclassified with reasoning noting language, never a crash |
| 10 | "THIS APP IS TRASH FIX IT NOW!!!!1!" | All-caps + no real detail (tone + vagueness combined) | Leans Unclassified/Human Triage — insufficient substance despite strong tone |
| 11 | "asdkjfh qwoieru 12345 !!!" | Nonsense/spam input | Unclassified, confidence 0, reasoning notes the text is not interpretable |
| 12 | "Hi team, just wondering if you plan to add dark mode soon? Not urgent at all, whenever you get a chance :)" | Known-Low severity, polite tone | Feature Request / Low |
| 13 | "Getting error code 500 when calling /api/v2/orders endpoint intermittently since this morning" | Technical jargon | Integration/API, Medium–High |
| 14 | "My card ending in 4521 was billed $299 instead of $99, please refund the difference" | Sensitive data (partial card number) present | Billing, correctly classified; reasoning/logs should not echo the full card fragment back unnecessarily |
| 15 | "The app crashes immediately when I open it — nothing loads, just a white screen" | Clear bug, no ambiguity | Bug Report, High |
| 16 | "Can someone walk me through how to export my report as PDF? Don't want to mess anything up." | Known-Low severity, calm | General Inquiry, Low |
| 17 | "🙂🙂 idk it's just kinda weird lol app doing weird stuff" | Vague + emoji + informal tone | Leans Unclassified/Human Triage — not enough concrete detail |
| 18 | "Production database is completely down, no one can process orders" | Known-High severity (unambiguous) | Bug Report/Platform, High |
| 19 | "There's a typo in the footer — copyright year still says 2023" | Known-Low severity (unambiguous) | Bug Report or General Inquiry, Low |
| 20 | "Payment gateway intermittently fails for about 5% of transactions since last night" | Known-Medium severity (unambiguous) | Billing/Integration, Medium |

Run all 20, save the raw JSON outputs, and keep them in the repo (`tests/sample_outputs.json`) — that file is your evidence for M4S1/M4S2 (valid JSON, all fields present on every one) without having to re-run live in front of the mentor if something's flaky.

## 4. Mentor-prep answers, in plain English

Write these in your own words before the demo — they're drafted here so you have a correct starting point, not a script to read verbatim.

**M4A1 — Explain a core concept like I'm a PM.** JSON schema enforcement, plainly: normally when you ask an AI for structured data, it's just following instructions and can slip up — extra text, a missing field, a made-up category. Schema enforcement means you hand the AI a strict template *before* it starts writing, and the software generating its response is only allowed to fill in that template — it physically cannot produce anything else. It's the difference between asking someone to "please format this neatly" versus handing them a form with boxes they can only check.

**M4A2 — Why this approach?** Why not just keyword search: keyword search is instant and free but breaks the moment wording is unusual, sarcastic, or a ticket mentions two things at once — so I use it *only* for the obvious cases (fast path) and hand anything uncertain to the model. Why few-shot over zero-shot: with instructions alone, a local model drifts on formatting and on how it handles ambiguity; giving it 2–3 worked examples anchors that behavior far more reliably than more instructions would.

**M4A3 — Walk me through what happens after submit.** The ticket text is first checked against a small set of obvious keyword rules — if one matches confidently, that's the answer, instantly, no AI involved. If not, the text goes to the local model along with a strict template of what the answer must look like; the model can only produce output matching that template. The result is double-checked in code; if anything's off, the model gets one chance to fix it with the specific error explained to it. If it still fails, the system returns a safe "needs a human" answer instead of guessing or crashing. Every step is timestamped and logged.

**M4A4 — Where is this most likely to be wrong?** Genuinely ambiguous tickets that blend two categories, very short tickets with real intent behind them that my "too vague" rule can't distinguish from actual nonsense, and non-English tickets, since the model's reliability drops outside English. My confidence threshold and Human Triage fallback exist specifically to catch these rather than let a wrong guess through silently.

**M4A5 — Who uses this and what problem does it solve?** A support team lead or L1 triage agent, who currently spends time reading every incoming ticket and manually deciding who should own it. This gives them consistent first-pass routing in under a couple seconds instead of minutes, flags anything it's unsure about instead of guessing, and gives them an SLA/overdue view they didn't have before.

**M4D1 — What took longest / what broke you didn't expect?** Getting the local model to reliably return valid JSON without hosted-API-style structured output support — plain prompting alone wasn't enough, which is what led to building the schema-constrained decoding + repair-retry layers rather than just writing a better prompt.

**M4D2 — What would you do differently?** [Fill this in honestly once you've built it — a good real answer usually references something the correction-feedback log actually showed you, e.g. "I'd add two more few-shot examples for the Billing-vs-Access boundary because that's where corrections clustered."]

**M4D4 — What are you least confident about?** Priority calibration for tone-heavy tickets, and behavior on non-English input — both are documented as known limitations rather than claimed as solved.

**M4D5 — What did you figure out beyond the brief?** Discovering and using the local model runtime's schema-constrained decoding feature (`format` as a JSON Schema) instead of relying on prompt instructions alone — that's a specific, real thing you researched and applied, not something handed to you in the brief.

**The check-style items (M4B, M4C, M4E, M4S) aren't questions — here's the one-line version of what each one is actually checking and how this build answers it:**

- **M4B1 consistency** — run one ticket twice, 5 minutes apart; low temperature setting means the classification should come out the same both times.
- **M4B2 edge cases** — blank input is rejected before it ever reaches the model; very long and non-English input are handled by the same pipeline without special-casing, with documented best-effort behavior.
- **M4B3 failure without crashing** — stop the local model service and send a request; you get a clear "unavailable" message, never a stack trace.
- **M4B4 usable output** — the web form shows color-coded badges and plain-English reasoning; the raw JSON is one click away for anyone technical.
- **M4B5 no hardcoded secrets** — there's no API key at all (local model), but config still lives in `.env`, not in code, to show the habit.
- **M4C1 solves the real problem** — feed it an actual messy ticket and it comes back with a defensible route and reasoning, not a toy example.
- **M4C2 usable by a non-technical person** — the web form is one textbox and one button; no explanation should be needed.
- **M4C3 right interface for context** — a web form fits a support-triage tool better than a CLI would; the CLI still exists for fast dev testing.
- **M4C4 complete scope** — routing, validation, fallback, logging, dashboard, and the UI all work together end-to-end, not just the happy path shown in a demo.
- **M4E1 readable code** — small, single-purpose files (`fast_path.py`, `router.py`, `ollama_client.py`, etc.) so each one is understandable on its own.
- **M4E2 README works cold** — the setup steps are literally "install Ollama, pull the model, pip install, create `.env`, run" — nothing assumed.
- **M4E3 no obvious security issues** — inputs are length-validated by Pydantic before they touch anything else; no secrets in source.
- **M4E4 stack conventions** — standard Python project layout, Pydantic models, PEP8-style naming.
- **M4S1/S2 valid JSON, all fields** — guaranteed structurally by schema-constrained decoding, checked semantically by Pydantic.
- **M4S3–S5 the three edge cases** — items 3, 4, 5 in the test set above.
- **M4S6 defensible priority** — items 2, 12, 16, 18, 19, 20 are chosen specifically because their real-world severity is unambiguous, so the reasoning field can be checked against an obvious right answer.
- **M4S7 timing evidence** — the stats dashboard's average latency, compared against a manually-timed pass over the same 20 tickets.

## 5. Updated 2-week schedule

| Days | Focus | Commit checkpoint |
|---|---|---|
| 1–2 | Repo scaffold, schema, pull/test Ollama models for JSON reliability | `init project, schema` |
| 3–4 | Fast-path rules + unit tests | `add fast path` |
| 5–6 | LLM client with schema-constrained format + Pydantic validation | `add LLM routing` |
| 7 | Repair-retry loop, fallback, Ollama-down handling | `add repair + fallback` |
| 8 | Logging + stats service | `add logging/stats` |
| 9 | CLI + Streamlit base UI with the palette/layout above | `add CLI + styled UI` |
| 10 | Core add-on: dashboard page + SLA flag | `add dashboard + SLA` |
| 11 | Core add-on: correction feedback loop + duplicate detection | `add feedback loop + dup detection` |
| 12 | Run all 20 test prompts, fix whatever breaks, save sample outputs | `add test set, fix issues` |
| 13 | Consistency test, timing comparison, stretch add-on if time allows | `add reliability evidence` |
| 14 | README, mentor-prep notes, final polish and rehearsal | `finalize docs` |