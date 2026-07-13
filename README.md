# 🧾 Routely — Smart Ticket Router

**Turn a raw support ticket into a routing decision in seconds, not the ~4 minutes it takes a human.** Category, priority, team, SLA, reasoning, duplicate/outage flags — schema-validated, every time.

Built with **Python · Pydantic · OpenAI · Streamlit**

---

## ✨ Overview

Routely takes free-text support tickets and turns them into structured routing decisions using an LLM constrained by a strict Pydantic schema. If the model's output doesn't validate, Routely automatically asks it to repair the response — and if that fails too, it degrades safely to a human-triage fallback instead of crashing or guessing. Every decision is logged, deduplicated against recent history, and trackable through resolution/escalation/correction workflows — all visualized in a live Streamlit dashboard, or scriptable from the CLI.

## 🚀 Features

### 🧠 Core Routing Engine
- **LLM-based classification** — routes tickets into 9 categories, 3 priority levels, and 9 teams using OpenAI's Chat Completions API
- **Strict schema enforcement** — every response is validated against a Pydantic model (`TicketRoute`) with `extra="forbid"`, literal enums, and bounded fields
- **Self-repair loop** — if the model returns invalid JSON or a schema mismatch, Routely re-prompts with the validation error and a two-stage repair attempt
- **Safe fallback path** — if the provider is unreachable, misconfigured, or repair fails twice, the ticket routes to `Unclassified` / `Human Triage` / `Low` instead of erroring out
- **Empty-input guard** — blank tickets short-circuit to a friendly fallback without calling the LLM at all

### 🎯 Prompt Intelligence (the routing "rulebook")
- **Category vs. category disambiguation** — e.g. Security (third-party compromise) vs. Account Access (owner's own lockout); Legal/Compliance vs. Security/Billing
- **Multi-issue tiebreaker logic** — when a ticket raises two problems, decides the primary one by stated urgency → dollar impact → order mentioned, and still surfaces the secondary issue in plain language
- **Severe-stakes priority trigger** — a concrete dollar threshold (**$1,000+**) or a named hard deadline auto-escalates a single-user issue to High, without needing "many users affected"
- **Business-risk override** — recurring incidents + an explicit churn/cancellation threat is treated as its own High-priority trigger
- **Anger-signal detection by word choice, not punctuation** — insults/profanity/contempt count; ALL CAPS, "asap," and "!!!" alone never do
- **System-wide outage flag** — a dedicated boolean that only fires on genuinely broad-impact language ("everyone," "no one," "the whole team") or a discovered auth/authz vulnerability, tightening the SLA to a Critical window
- **No-content ("Case B") handling** — bare words with zero elaboration (`"broken"`) route to Human Triage instead of guessing a category
- **Multilingual-tolerant** — non-English tickets are still classified sensibly (see demo below)

### ⏱️ SLA & Duplicate Detection
- **Configurable SLA windows** per priority (Critical / High / Medium / Low), with a shorter Critical SLA auto-applied for system-wide outages
  - `sla_hours = SLA_CRITICAL_HOURS` if `priority == High and system_wide_outage == True`, else `SLA_HOURS[priority]` (defaults: Critical 1h, High 2h, Medium 12h, Low 24h)
- **Fuzzy duplicate detection** — flags a ticket as a likely repeat if either:
  - `SequenceMatcher(current, previous).ratio() >= DUPLICATE_SIMILARITY_THRESHOLD` (default `0.8`), **or**
  - shared word tokens between the two tickets `>= 2` **and** similarity ratio `>= 0.5`
  - compared only against requests within the rolling lookback window (`DUPLICATE_LOOKBACK_HOURS`, default 24h); the closest match above threshold wins
- **Confidence score** — the model returns a `confidence` value between `0.0` and `1.0` for every routed ticket; it's forced below `0.6` whenever a ticket is genuinely ambiguous between two categories, so a low score is a real signal to double-check the routing rather than a decorative number

### 📋 Ticket Lifecycle Tracking — the 3 per-ticket action buttons
Every routed result (single or batch) gets three one-click actions in the UI:
1. **Mark Resolved** — closes out the ticket and excludes it from the overdue-SLA count
2. **Escalate** — flags the ticket for immediate human follow-up
3. **This was misrouted** — lets the user pick the category they believe is correct, logging a correction that feeds the correction-rate metric

Each button is disabled after use (per ticket) so the same action can't be logged twice.

### 📊 Analytics Engine — the numbers and how they're computed
All figures are recomputed live from the JSONL logs in `logs/` (see [app/analytics.py](app/analytics.py)):

| Metric | Formula |
|---|---|
| **Total tickets routed** | count of all entries in `requests.jsonl` |
| **Average latency (ms)** | `sum(latency_ms for each request) / total requests` |
| **Repair rate %** | `(requests where path_taken == "repair") / total requests × 100` |
| **Fallback/error rate %** | `(requests where path_taken == "fallback") / total requests × 100` |
| **Correction rate %** | `(entries in corrections.jsonl) / total requests × 100` |
| **Overdue SLA count** | for every unresolved ticket, `now − routed_timestamp > sla_hours` (SLA hours from the formula above) |
| **Category / priority breakdowns** | simple counts of each `category` / `priority` value across all routed requests |

### 📦 Batch Processing
- **File upload** — accepts a CSV (needs a `ticket` column) or a JSON file (a list of strings, or objects with a `ticket` field)
- **One-click batch run** — "Route All Tickets" routes every ticket in the file through the same LLM → validate → repair → fallback pipeline as single-ticket routing, sequentially, and times the whole run
- **Results table** — shows ticket ID, category, assigned team, priority (with a Critical tag for system-wide outages), reasoning, SLA hours, and confidence for every ticket in one `st.dataframe`
- **Throughput readout** — reports total elapsed time and average seconds/ticket for the batch
- **Export** — download the full results table as CSV or JSON directly from the dashboard

### 🖥️ Streamlit Dashboard (`app.py`)
- Custom dark-mode theme with color-coded priority badges and a distinct violet "CRITICAL — SYSTEM-WIDE OUTAGE" banner
- Live sidebar metrics: tickets routed, avg latency, avg *manual* routing time (for comparison), fallback rate, correction rate, overdue count
- Category/team filter that highlights matching results and dims non-matches
- Built-in example prompts + free-text entry form
- One-click **Resolve / Escalate / Flag as misrouted** actions per ticket (the 3 lifecycle buttons, detailed above)
- Raw JSON inspector for any routed result

### ⌨️ CLI (`router_cli.py`)
- Route a single ticket from the terminal, prints the provider used and full JSON result — ideal for scripting or quick checks

### 🔐 Configuration & Safety
- All config via `.env` (never hardcoded) — API keys, model choice, log paths, SLA hours, duplicate-detection thresholds
- Graceful, explicit error surfacing (`provider_error`) instead of silent failures

---

## 🧩 Components

| Component | File | What it does |
|---|---|---|
| **Streamlit UI** | [app.py](app.py) | Full web dashboard — single + batch routing, lifecycle actions, live stats, theming |
| **CLI entrypoint** | [router_cli.py](router_cli.py) | Terminal-based single-ticket routing |
| **Routing orchestrator** | [app/router.py](app/router.py) | Ties together LLM call → validation → repair → fallback → logging → duplicate check |
| **LLM client** | [app/llm_client.py](app/llm_client.py) | Builds the routing prompt/rulebook, calls OpenAI, parses responses, handles repair requests |
| **Schema** | [app/schema.py](app/schema.py) | `TicketRoute` Pydantic model — the contract every routing decision must satisfy |
| **Analytics** | [app/analytics.py](app/analytics.py) | SLA math, duplicate detection, resolution/escalation/correction tracking, dashboard stats |
| **Logger** | [app/logger.py](app/logger.py) | Appends structured JSONL entries for every routed request |
| **Config** | [app/config.py](app/config.py) | Loads `.env`, exposes typed settings (API key, model, SLA hours, thresholds, log paths) |
| **Tests** | [tests/test_router.py](tests/test_router.py) | pytest coverage for routing, SLA, and duplicate logic |
| **Demo data** | [demo/sample_tickets.json](demo/sample_tickets.json), [demo/routed_tickets.json](demo/routed_tickets.json) | 20 realistic sample tickets + their actual routed output |
| **Logs (generated)** | `logs/*.jsonl` | `requests`, `corrections`, `resolutions`, `escalations` — one JSONL file per event type |

## 🗂 Project Structure

```
Port_4/
├── app.py                  # Streamlit dashboard
├── router_cli.py           # CLI entrypoint
├── app/
│   ├── config.py           # .env-driven settings
│   ├── schema.py           # TicketRoute Pydantic schema
│   ├── llm_client.py        # Prompt rulebook + OpenAI calls + repair
│   ├── router.py           # Orchestration: classify → validate → log
│   └── analytics.py        # SLA, duplicates, stats, lifecycle tracking
├── demo/
│   ├── sample_tickets.json   # 20 example raw tickets
│   └── routed_tickets.json   # Their routed output (for reference)
├── logs/                   # Generated JSONL logs (requests/corrections/resolutions/escalations)
├── tests/
│   └── test_router.py
├── requirements.txt
└── .env                    # Your local secrets/config (not committed)
```

---

## ⚙️ Setup

**1. Clone and enter the project**
```bash
cd Port_4
```

**2. Create a virtual environment** *(a `.venv` is already present, or create your own)*
```bash
python3 -m venv .venv
source .venv/bin/activate
```

**3. Install dependencies**
```bash
pip install -r requirements.txt
```

**4. Configure `.env`** in the project root:

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `OPENAI_API_KEY` | ✅ | — | Your OpenAI API key |
| `OPENAI_MODEL` | | `gpt-4o-mini` | Model used for routing |
| `REQUEST_LOG_PATH` | | `logs/requests.jsonl` | Where routed requests are logged |
| `CORRECTIONS_LOG_PATH` | | `logs/corrections.jsonl` | Where misrouting flags are logged |
| `RESOLUTIONS_LOG_PATH` | | `logs/resolutions.jsonl` | Where resolved tickets are logged |
| `ESCALATIONS_LOG_PATH` | | `logs/escalations.jsonl` | Where escalations are logged |
| `SLA_CRITICAL_HOURS` | | `1` | SLA for system-wide outages |
| `SLA_HIGH_HOURS` | | `2` | SLA for High priority |
| `SLA_MEDIUM_HOURS` | | `12` | SLA for Medium priority |
| `SLA_LOW_HOURS` | | `24` | SLA for Low priority |
| `DUPLICATE_LOOKBACK_HOURS` | | `24` | How far back to check for duplicate tickets |
| `DUPLICATE_SIMILARITY_THRESHOLD` | | `0.8` | Similarity ratio required to flag a duplicate |

Without `OPENAI_API_KEY`, every ticket safely falls back to `Unclassified` / `Human Triage` rather than failing.

---

## ▶️ Running It

**CLI:**
```bash
python router_cli.py "I can't log into my account, it says invalid password even though I reset it yesterday."
```

**Streamlit dashboard:**
```bash
streamlit run app.py
```
Opens at `http://localhost:8501`.

**Tests:**
```bash
pytest
```

---

## 🎬 Live Demo Walkthrough

The fastest way to see everything in action:

1. Run `streamlit run app.py`
2. Try the **built-in example dropdown** at the top, or type your own ticket, then click **Route Ticket**
3. Scroll to **Batch Routing** → upload [demo/sample_tickets.json](demo/sample_tickets.json) → click **Route All Tickets** to see 20 realistic tickets routed at once, with a results table you can export as CSV/JSON

Here's a taste of what that batch run produces (from [demo/routed_tickets.json](demo/routed_tickets.json)):

| Ticket | Category | Team | Priority | SLA |
|---|---|---|---|---|
| "I can't log into my account, it says invalid password even though I reset it yesterday." | Account Access | Identity & Access | Medium | 12h |
| "Server is down for everyone, we are losing money every minute!!" | Bug Report | Engineering | **High (Critical)** | 1h |
| "Someone logged into my account from a device I don't recognize and changed my email and password." | Security | Security & Trust | High | 2h |
| "Under GDPR I am requesting you delete all my personal data from your systems within 30 days." | Legal/Compliance | Legal & Compliance | Medium | 12h |
| "broken" | Unclassified | Human Triage | Low | 24h |
| "." | Unclassified | Human Triage | Low | 24h |

Notice how the router distinguishes a *routine* lockout (Medium) from an *account takeover* (Security/High), and correctly treats a bare `"broken"` as not-enough-information rather than guessing.

---

## 🧭 Routing Logic

**Category → Team mapping** (fixed, never guessed):

| Category | Team |
|---|---|
| Billing | Billing Ops |
| Account Access | Identity & Access |
| Bug Report | Engineering |
| Feature Request | Product |
| Integration/API | Platform/API |
| General Inquiry | Customer Success |
| Security | Security & Trust |
| Legal/Compliance | Legal & Compliance |
| Unclassified | Human Triage |

**Priority at a glance:**

| Priority | Trigger |
|---|---|
| 🟣 **Critical** | High + `system_wide_outage=true` (broad-impact outage or exposed vuln) |
| 🔴 **High** | Total feature failure, security breach, multi-day unresolved issue, $1,000+ stakes, hard business deadline, or repeated incident + churn threat |
| 🟠 **Medium** | Single-user, single-function issue with an available (or already-exhausted) workaround |
| 🟢 **Low** | General inquiries, feature requests, cosmetic issues, or no identifiable content |

---

## 📊 Analytics & Logs

All events are appended as JSONL under `logs/`:

- `requests.jsonl` — every routing decision, latency, and path taken (`llm` / `repair` / `fallback`)
- `corrections.jsonl` — user-flagged misroutes
- `resolutions.jsonl` — tickets marked resolved
- `escalations.jsonl` — tickets escalated for human follow-up

These feed the live sidebar metrics in the Streamlit dashboard: total routed, avg latency, fallback rate, correction rate, and overdue-SLA count.

---

## 🧪 Testing

```bash
pytest -v
```

Covers empty/no-content input handling, SLA computation, and fuzzy duplicate-ticket detection.
