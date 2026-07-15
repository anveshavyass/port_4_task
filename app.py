import csv
import io
import json
import time
from pathlib import Path

import streamlit as st

from app.analytics import (
    build_stats,
    is_ticket_corrected,
    is_ticket_escalated,
    is_ticket_resolved,
    load_jsonl,
    log_correction,
    record_escalation,
    record_resolution,
)
from app.config import (
    CORRECTIONS_LOG_PATH,
    ESCALATIONS_LOG_PATH,
    REQUEST_LOG_PATH,
    RESOLUTIONS_LOG_PATH,
)
from app.router import route_ticket

CATEGORIES = [
    "All Categories",
    "Billing",
    "Account Access",
    "Bug Report",
    "Feature Request",
    "Integration/API",
    "General Inquiry",
    "Security",
    "Legal/Compliance",
    "Unclassified",
]
TEAMS = [
    "All Teams",
    "Billing Ops",
    "Identity & Access",
    "Engineering",
    "Product",
    "Platform/API",
    "Customer Success",
    "Security & Trust",
    "Legal & Compliance",
    "Human Triage",
]
SAMPLE_PROMPTS = [
    "I can't log into my account, it says invalid password even though I reset it yesterday.",
    "This is RIDICULOUS, nothing works and I've been waiting 3 days!!!",
    "broken",
]


def _parse_uploaded_tickets(uploaded_file) -> list[str]:
    raw = uploaded_file.read()
    name = uploaded_file.name.lower()
    texts = []
    if name.endswith(".json"):
        data = json.loads(raw.decode("utf-8"))
        items = data if isinstance(data, list) else [data]
        for item in items:
            if isinstance(item, str):
                if item.strip():
                    texts.append(item)
            elif isinstance(item, dict):
                text = item.get("ticket") or item.get("text") or item.get("message")
                if text and str(text).strip():
                    texts.append(str(text))
    else:
        reader = csv.DictReader(io.StringIO(raw.decode("utf-8")))
        fieldnames = reader.fieldnames or []
        text_field = next(
            (fn for fn in fieldnames if fn.strip().lower() in ("ticket", "text", "message")),
            fieldnames[0] if fieldnames else None,
        )
        if text_field:
            for row in reader:
                value = (row.get(text_field) or "").strip()
                if value:
                    texts.append(value)
    return texts


def _one_line(text: str) -> str:
    return " ".join(str(text).split())


def _to_summary(result: dict) -> dict:
    return {
        "category": result["category"],
        "priority": result["priority"],
        "assigned_team": result["assigned_team"],
        "reasoning": _one_line(result["reasoning"]),
    }


def _rows_to_csv(rows: list[dict]) -> str:
    if not rows:
        return ""
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


def _go_to(view: str) -> None:
    st.session_state["view"] = view
    st.rerun()


def inject_theme() -> None:
    st.markdown(
        """
        <style>
        /* Dark mode: dark background with light text */
        html, body, .stApp, .main, .block-container {
            background: linear-gradient(180deg, #071120 0%, #0b1220 100%) !important;
            color: #e6eef8 !important;
        }

        /* Ensure most Streamlit components inherit the light text color */
        * , .stText, .stMarkdown, .stDataFrame, .stJson, textarea, input, select, option, label {
            color: #e6eef8 !important;
        }

        /* Controls and cards should use slightly lighter dark surfaces */
        .css-18e3th9, .css-1y4p8pa, .stButton>button, .stSelectbox>div, .stTextInput>div, .stTextArea>div {
            background: #081426 !important;
            color: #e6eef8 !important;
            border: 1px solid rgba(255,255,255,0.04) !important;
        }

        /* Priority badges */
        .badge-high { background:#ef4444; color:#071120; padding:6px 14px; border-radius:14px; font-weight:700; font-size:0.95rem; }
        .badge-med { background:#f59e0b; color:#071120; padding:6px 14px; border-radius:14px; font-weight:700; font-size:0.95rem; }
        .badge-low { background:#34d399; color:#071120; padding:6px 14px; border-radius:14px; font-weight:700; font-size:0.95rem; }

        /* Critical / system-wide-outage tag — deliberately a new color (violet), never used for anything else,
           so it always reads as "one tier above ordinary High" at a glance */
        .critical-tag {
            display:inline-flex; align-items:center; gap:8px;
            background:#7c3aed; color:#ffffff; padding:8px 16px; border-radius:10px;
            font-weight:800; font-size:1rem; letter-spacing:0.02em;
            border:1px solid rgba(255,255,255,0.25);
            box-shadow:0 0 0 3px rgba(124,58,237,0.25);
            margin-bottom:0.75rem;
        }

        /* Legend chips */
        .legend-chip { display:inline-block; width:16px; height:16px; border-radius:6px; margin-right:8px; vertical-align:middle; }
        .legend-high { background:#dc2626; }
        .legend-med { background:#f59e0b; }
        .legend-low { background:#22c55e; }

        /* Result card styling */
        .result-card.match { border: 2px solid rgba(52,211,153,0.95); box-shadow: 0 30px 60px rgba(52,211,153,0.06); background: linear-gradient(180deg, rgba(8,20,38,0.6) 0%, rgba(8,20,38,0.85) 100%) !important; }
        .result-card.dim { opacity:0.65; filter:grayscale(20%); box-shadow: 0 6px 18px rgba(2,6,23,0.5); background: rgba(5,10,20,0.6) !important; }
        .result-title { margin-bottom: 0.5rem; color:#e6eef8; font-size:1.4rem; font-weight:700; }
        .result-row { display:flex; align-items:center; gap:1rem; flex-wrap:wrap; margin-bottom:0.75rem; }
        .result-label { color:#9fb0c9; font-weight:600; min-width:140px; }
        .result-value { color:#e6eef8; font-weight:700; }

        /* Sidebar metrics card polish */
        .sidebar .block-container { padding-top: 1rem; }
        .stSidebar [data-testid='stMetric'] > div {
            background: rgba(255,255,255,0.02) !important;
            border-radius: 16px;
            padding: 0.75rem 1rem;
            box-shadow: 0 6px 18px rgba(2,6,23,0.6);
            color: #e6eef8 !important;
        }
        /* Make primary buttons prominent (red) */
        .stButton>button {
            background: #dc2626 !important;
            color: #ffffff !important;
            border-radius: 8px !important;
            padding: 8px 14px !important;
            border: 1px solid rgba(255,255,255,0.06) !important;
        }
        /* Also target form submit buttons (Route Ticket) */
        form button[type="submit"], form input[type="submit"], .stForm button, .stForm [type="submit"] {
            background: #dc2626 !important;
            color: #ffffff !important;
            border-radius: 8px !important;
            padding: 8px 14px !important;
            border: 1px solid rgba(255,255,255,0.06) !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_landing() -> None:
    st.markdown(
        """
        <div style='text-align:center; margin: 1.5rem 0 2.5rem;'>
            <h1 style='margin-bottom:0.4rem; font-size:3rem; font-weight:800;
                       background:linear-gradient(135deg, #ffffff 0%, #9fb0c9 100%);
                       -webkit-background-clip:text; background-clip:text; color:transparent;'>
                Routely — Smart Ticket Router
            </h1>
            <div style='width:120px; height:4px; margin:0.75rem auto 1rem;
                        background:linear-gradient(90deg, #dc2626, #f59e0b); border-radius:4px;'></div>
            <p style='color:#9fb0c9; margin-top:0; font-size:1.05rem;'>
                Route support tickets with a local, schema-aware workflow
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        <style>
        .st-key-admin_square, .st-key-user_square {
            aspect-ratio: 1 / 1;
            max-width: 440px;
            margin: 0 auto;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            text-align: center;
            gap: 0.85rem;
            padding: 2rem;
            border-radius: 22px !important;
            box-shadow: 0 20px 45px rgba(2,6,23,0.55);
            transition: transform 0.2s ease, box-shadow 0.2s ease, border-color 0.2s ease;
        }
        .st-key-admin_square:hover, .st-key-user_square:hover {
            transform: translateY(-6px);
            box-shadow: 0 28px 60px rgba(2,6,23,0.7);
        }
        .st-key-admin_square:hover { border-color: rgba(220,38,38,0.6) !important; }
        .st-key-user_square:hover { border-color: rgba(245,158,11,0.6) !important; }
        .st-key-admin_square h3, .st-key-user_square h3 {
            font-size: 1.9rem;
            margin-bottom: 0.25rem;
        }
        .st-key-admin_square [data-testid="stButton"], .st-key-user_square [data-testid="stButton"] {
            display: flex;
            justify-content: center;
            margin-top: 0.5rem;
        }
        .st-key-admin_square [data-testid="stButton"] button, .st-key-user_square [data-testid="stButton"] button {
            padding: 10px 28px !important;
            font-size: 1rem !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    col1, col2 = st.columns(2)
    with col1:
        with st.container(border=True, key="admin_square"):
            st.subheader("🛠️ Admin View")
            st.write(
                "Full routing dashboard — single & batch routing, live stats, "
                "filters, ticket lifecycle actions, and the corrections / "
                "escalations / requests / resolutions logs."
            )
            if st.button("Enter Admin View"):
                _go_to("admin")
    with col2:
        with st.container(border=True, key="user_square"):
            st.subheader("🙋 User View")
            st.write("Submit a support ticket and find out when it'll be resolved.")
            if st.button("Enter User View"):
                _go_to("user")


def render_user_view() -> None:
    if st.button("← Back to Home"):
        _go_to("landing")

    st.title("Submit a Ticket")
    st.caption("Tell us what's going on and we'll route it to the right team.")

    with st.form("user_ticket_form"):
        ticket_text = st.text_area("Describe your issue")
        submitted = st.form_submit_button("Submit Ticket")

    if submitted:
        if ticket_text and ticket_text.strip():
            result = route_ticket(ticket_text)
            st.session_state["user_last_sla"] = result["sla_hours"]
        else:
            st.session_state["user_last_sla"] = None
            st.warning("Please describe your issue before submitting.")

    sla_hours = st.session_state.get("user_last_sla")
    if sla_hours is not None:
        st.success(
            f"✅ Your ticket has been submitted. It will be resolved within "
            f"**{sla_hours} hours** (SLA)."
        )


def _format_request_entry(entry: dict) -> None:
    output = entry.get("output", {}) or {}
    confidence = output.get("confidence")
    confidence_text = f"{confidence:.2f}" if isinstance(confidence, (int, float)) else "—"
    latency_ms = entry.get("latency_ms")
    latency_text = f"{latency_ms / 1000:.2f}s" if isinstance(latency_ms, (int, float)) else "—"
    ticket_id = entry.get("ticket_id")
    widget_key = f"{ticket_id or 'legacy'}_{entry.get('timestamp', '')}"

    with st.container(border=True):
        st.markdown(f"**🎫 Ticket `{ticket_id or '—'}`**")
        st.caption(entry.get("timestamp", "—"))
        st.markdown(f"\"{_one_line(entry.get('input', ''))}\"")
        st.markdown(
            f"Category: **{output.get('category', '—')}** · "
            f"Priority: **{output.get('priority', '—')}** · "
            f"Assigned team: **{output.get('assigned_team', '—')}**"
        )
        st.markdown(f"Reasoning: _{output.get('reasoning', '—')}_")
        st.markdown(
            f"Confidence: {confidence_text} · "
            f"SLA: {output.get('sla_hours', '—')}h · "
            f"Latency: {latency_text} · "
            f"Path: {entry.get('path_taken', '—')} · "
            f"Provider: {output.get('provider', '—')}"
        )

        duplicate_of = output.get("possible_duplicate_of") or entry.get("possible_duplicate_of")
        if duplicate_of:
            st.warning(f"Possible duplicate of: {duplicate_of}")

        if not ticket_id:
            st.caption("Lifecycle actions unavailable — this legacy entry has no ticket ID.")
            return

        already_resolved = is_ticket_resolved(ticket_id)
        already_escalated = is_ticket_escalated(ticket_id)
        already_corrected = is_ticket_corrected(ticket_id)

        with st.container(key=f"req_actions_{widget_key}"):
            col1, col2, col3 = st.columns([1, 1, 1.4])
            with col1:
                if st.button("Mark Resolved", key=f"resolve_{widget_key}", disabled=already_resolved):
                    if record_resolution(ticket_id):
                        st.rerun()
                if already_resolved:
                    st.caption("Already resolved.")
            with col2:
                if st.button("Escalate", key=f"escalate_{widget_key}", disabled=already_escalated):
                    if record_escalation(ticket_id, output):
                        st.rerun()
                if already_escalated:
                    st.caption("Already escalated.")
            with col3:
                corrected_category = st.selectbox(
                    "Correct category",
                    CATEGORIES[1:],
                    key=f"correct_cat_{widget_key}",
                    disabled=already_corrected,
                    label_visibility="collapsed",
                )
                if st.button("This was misrouted", key=f"misrouted_{widget_key}", disabled=already_corrected):
                    if log_correction(ticket_id, corrected_category, output, "User flagged this result"):
                        st.rerun()
                if already_corrected:
                    st.caption("Already flagged as misrouted.")


def _format_correction_entry(entry: dict) -> None:
    original = entry.get("original_result", {}) or {}
    with st.container(border=True):
        st.markdown(f"**Ticket `{entry.get('ticket_id', '—')}`** flagged as misrouted")
        st.caption(entry.get("timestamp", "—"))
        st.markdown(
            f"Originally routed to **{original.get('category', '—')}**, "
            f"corrected to **{entry.get('corrected_category', '—')}**. "
            f"Reason: _{entry.get('reason') or 'None given'}_"
        )


def _format_escalation_entry(entry: dict) -> None:
    original = entry.get("original_result", {}) or {}
    with st.container(border=True):
        st.markdown(f"**🚨 Ticket `{entry.get('ticket_id', '—')}` escalated**")
        st.caption(entry.get("timestamp", "—"))
        st.markdown(
            f"Category: {original.get('category', '—')} · "
            f"Priority: {original.get('priority', '—')} · "
            f"Team: {original.get('assigned_team', '—')}"
        )


def _format_resolution_entry(entry: dict) -> None:
    with st.container(border=True):
        st.markdown(f"**✅ Ticket `{entry.get('ticket_id', '—')}` marked resolved**")
        st.caption(entry.get("timestamp", "—"))


CORE_FIELDS = ["category", "priority", "assigned_team", "reasoning"]


def _extract_core_fields(entry: dict) -> dict:
    sources = [entry, entry.get("output") or {}, entry.get("original_result") or {}]
    filtered = {}
    for field in CORE_FIELDS:
        for source in sources:
            if field in source:
                filtered[field] = source[field]
                break
    if not filtered:
        # entries like resolutions carry none of the core fields — fall back
        # to whatever identifies the entry instead of showing an empty object
        filtered = {
            key: entry[key] for key in ("ticket_id", "timestamp") if key in entry
        }
    return filtered


def render_log_tab(path: str, human_formatter, empty_message: str) -> None:
    entries = load_jsonl(path)
    view_mode = st.radio(
        "View as",
        ["User View", "Structured JSON", "Raw JSON"],
        horizontal=True,
        key=f"view_mode_{path}",
    )
    st.caption(f"{len(entries)} entries logged in `{path}`")

    if not entries:
        st.info(empty_message)
        return

    if view_mode == "Raw JSON":
        raw_path = Path(path)
        raw_text = raw_path.read_text(encoding="utf-8") if raw_path.exists() else ""
        st.code(raw_text, language="json")
        return

    # most recent entry first, for User View / Structured JSON
    ordered_entries = list(reversed(entries))

    if view_mode == "Structured JSON":
        filtered = [_extract_core_fields(entry) for entry in ordered_entries]
        st.json(filtered)
    else:
        st.markdown(
            """
            <style>
            div[class*="st-key-req_actions_"] .stButton>button {
                padding: 3px 12px !important;
                font-size: 0.78rem !important;
                min-height: 0 !important;
                border-radius: 6px !important;
            }
            div[class*="st-key-req_actions_"] div[data-testid="stSelectbox"] {
                margin-bottom: 0 !important;
            }
            </style>
            """,
            unsafe_allow_html=True,
        )
        for entry in ordered_entries:
            human_formatter(entry)


def render_admin_view() -> None:
    if st.button("← Back to Home"):
        _go_to("landing")

    st.title("Routely — Smart Ticket Router")
    st.caption("Route support tickets with a local, schema-aware workflow")

    with st.sidebar:
        st.header("Legend")
        st.markdown(
            """
            <div style='display:flex; flex-direction:column; gap:10px;'>
                <div><span class='legend-chip legend-high'></span>High priority</div>
                <div><span class='legend-chip legend-med'></span>Medium priority</div>
                <div><span class='legend-chip legend-low'></span>Low priority</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        stats = build_stats()
        st.metric("Tickets routed", stats.get("total", 0))
        st.metric("Avg latency", f"{stats.get('avg_latency_ms', 0) / 1000:.2f} s")
        st.metric("Avg manual routing time", "3-4 mins")
        st.metric("Fallback / Error rate", f"{stats.get('fallback_rate_pct', 0):.1f}%")
        st.metric("Correction rate", f"{stats.get('correction_rate_pct', 0):.1f}%")
        st.metric("Overdue (SLA)", stats.get("overdue_count", 0))

        selected_category = st.selectbox("Show category", CATEGORIES)
        selected_team = st.selectbox("Show assigned team", TEAMS)

    tab_routing, tab_requests, tab_corrections, tab_escalations, tab_resolutions = st.tabs(
        ["Ticket Routing", "Requests", "Corrections", "Escalations", "Resolutions"]
    )

    with tab_routing:
        selected_prompt = st.selectbox("Try a built-in example", SAMPLE_PROMPTS)

        with st.form("ticket_form"):
            ticket_text = st.text_area("Ticket text", value=selected_prompt)
            submitted = st.form_submit_button("Route Ticket")

        if submitted:
            st.session_state["last_result"] = route_ticket(ticket_text)
            st.rerun()

        result = st.session_state.get("last_result")

        if result:
            st.subheader("Result")
            category_match = (selected_category == "All Categories") or (result.get("category") == selected_category)
            team_match = (selected_team == "All Teams") or (result.get("assigned_team") == selected_team)
            overall_match = category_match and team_match

            card_class = "result-card match" if overall_match else "result-card dim"

            if result.get("priority") == "High" and result.get("system_wide_outage"):
                st.markdown(
                    "<div class='critical-tag'>⚠ CRITICAL — SYSTEM-WIDE OUTAGE</div>",
                    unsafe_allow_html=True,
                )

            st.markdown(f"<div class='{card_class}'>", unsafe_allow_html=True)
            st.markdown(f"<div class='result-title'>Category: {result['category']}</div>", unsafe_allow_html=True)

            priority_class = "badge-high" if result["priority"] == "High" else "badge-med" if result["priority"] == "Medium" else "badge-low"
            st.markdown(
                f"<div class='result-row'><span class='result-label'>Assigned team:</span><span class='result-value'>{result['assigned_team']}</span></div>"
                f"<div class='result-row'><span class='result-label'>Priority:</span><span class='result-value {priority_class}'>{result['priority']}</span></div>"
                f"<div class='result-row'><span class='result-label'>Confidence:</span><span class='result-value'>{result['confidence']:.2f}</span></div>"
                f"<div class='result-row'><span class='result-label'>SLA:</span><span class='result-value'>Respond within {result['sla_hours']} hours</span></div>"
                f"<div class='result-row'><span class='result-label'>Provider:</span><span class='result-value'>{result.get('provider', 'unknown')}</span></div>",
                unsafe_allow_html=True,
            )
            st.markdown(f"<div class='result-row'><span class='result-label'>Reasoning:</span><span class='result-value'>{result['reasoning']}</span></div>", unsafe_allow_html=True)

            if result.get("possible_duplicate_of"):
                st.warning(f"Possible duplicate of: {result['possible_duplicate_of']}")

            st.markdown("</div>", unsafe_allow_html=True)

            already_resolved = is_ticket_resolved(result["ticket_id"])
            already_escalated = is_ticket_escalated(result["ticket_id"])
            already_corrected = is_ticket_corrected(result["ticket_id"])

            col1, col_escalate, col2 = st.columns([1, 1, 1])
            with col1:
                if st.button("Mark Resolved", disabled=already_resolved):
                    if record_resolution(result["ticket_id"]):
                        st.write("Resolution recorded")
                        st.rerun()
                if already_resolved:
                    st.caption("Already marked resolved.")
            with col_escalate:
                if st.button("Escalate", disabled=already_escalated):
                    if record_escalation(result["ticket_id"], result):
                        st.write("Escalated for immediate human follow-up")
                        st.rerun()
                if already_escalated:
                    st.caption("Already escalated.")
            with col2:
                corrected_category = st.selectbox(
                    "Correct category",
                    CATEGORIES[1:],
                    key=f"corrected_category_{result['ticket_id']}",
                    disabled=already_corrected,
                )
                if st.button("This was misrouted", disabled=already_corrected):
                    if log_correction(result["ticket_id"], corrected_category, result, "User flagged this result"):
                        st.write("Correction logged")
                        st.rerun()
                if already_corrected:
                    st.caption("Already flagged as misrouted.")

            with st.expander("Show raw JSON"):
                st.json(_to_summary(result))

        st.markdown("---")
        st.subheader("Batch Routing")
        st.caption("Upload a CSV or JSON file of tickets and route all of them at once.")

        uploaded_file = st.file_uploader(
            "Upload tickets (CSV needs a 'ticket' column; JSON is a list of strings or objects with a 'ticket' field)",
            type=["csv", "json"],
        )

        if uploaded_file is not None and st.button("Route All Tickets"):
            ticket_texts = _parse_uploaded_tickets(uploaded_file)
            if not ticket_texts:
                st.error("No ticket text found in the uploaded file.")
            else:
                start = time.perf_counter()
                batch = [{"ticket": text, **route_ticket(text)} for text in ticket_texts]
                elapsed = time.perf_counter() - start
                st.session_state["batch_results"] = batch
                st.session_state["batch_elapsed"] = elapsed
                st.rerun()

        batch_results = st.session_state.get("batch_results")
        if batch_results:
            elapsed = st.session_state.get("batch_elapsed", 0.0)
            st.success(
                f"Routed {len(batch_results)} tickets in {elapsed:.2f}s "
                f"({elapsed / len(batch_results):.2f}s/ticket average)."
            )

            display_rows = []
            for r in batch_results:
                priority_display = r["priority"]
                if r["priority"] == "High" and r.get("system_wide_outage"):
                    priority_display = f"{r['priority']} (Critical)"
                display_rows.append(
                    {
                        "ticket_id": r["ticket_id"],
                        "ticket": r["ticket"],
                        "category": r["category"],
                        "assigned_team": r["assigned_team"],
                        "priority": priority_display,
                        "reasoning": r["reasoning"],
                        "sla_hours": r["sla_hours"],
                        "confidence": r["confidence"],
                    }
                )

            st.dataframe(display_rows, use_container_width=True)

            csv_data = _rows_to_csv(display_rows)
            json_data = json.dumps(display_rows, indent=2)

            dl_col1, dl_col2 = st.columns(2)
            with dl_col1:
                st.download_button("Download as CSV", data=csv_data, file_name="routed_tickets.csv", mime="text/csv")
            with dl_col2:
                st.download_button(
                    "Download as JSON", data=json_data, file_name="routed_tickets.json", mime="application/json"
                )

    with tab_requests:
        render_log_tab(REQUEST_LOG_PATH, _format_request_entry, "No requests logged yet.")

    with tab_corrections:
        render_log_tab(CORRECTIONS_LOG_PATH, _format_correction_entry, "No corrections logged yet.")

    with tab_escalations:
        render_log_tab(ESCALATIONS_LOG_PATH, _format_escalation_entry, "No escalations logged yet.")

    with tab_resolutions:
        render_log_tab(RESOLUTIONS_LOG_PATH, _format_resolution_entry, "No resolutions logged yet.")


st.set_page_config(page_title="Routely — Smart Ticket Router", page_icon="🧾", layout="wide")
inject_theme()

st.session_state.setdefault("view", "landing")

if st.session_state["view"] == "user":
    render_user_view()
elif st.session_state["view"] == "admin":
    render_admin_view()
else:
    render_landing()

#streamlit app
