import csv
import io
import json
import time

import streamlit as st

from app.analytics import (
    build_stats,
    is_ticket_corrected,
    is_ticket_escalated,
    is_ticket_resolved,
    log_correction,
    record_escalation,
    record_resolution,
)
from app.router import route_ticket


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


st.set_page_config(page_title="Routely — Smart Ticket Router", page_icon="🧾", layout="wide")

st.title("Routely — Smart Ticket Router")
st.caption("Route support tickets with a local, schema-aware workflow")

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
    .legend-critical { background:#7c3aed; }
    
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

with st.sidebar:
    st.header("Legend")
    st.markdown(
        """
        <div style='display:flex; flex-direction:column; gap:10px;'>
            <div><span class='legend-chip legend-critical'></span>Critical</div>
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
    st.metric("Avg manual routing time", "240 s")
    st.metric("Fallback / Error rate", f"{stats.get('fallback_rate_pct', 0):.1f}%")
    st.metric("Correction rate", f"{stats.get('correction_rate_pct', 0):.1f}%")
    st.metric("Overdue (SLA)", stats.get("overdue_count", 0))

    categories = [
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
    teams = [
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
    selected_category = st.selectbox("Show category", categories)
    selected_team = st.selectbox("Show assigned team", teams)

sample_prompts = [
    "I can't log into my account, it says invalid password even though I reset it yesterday.",
    "This is RIDICULOUS, nothing works and I've been waiting 3 days!!!",
    "broken",
]

selected_prompt = st.selectbox("Try a built-in example", sample_prompts)

with st.form("ticket_form"):
    ticket_text = st.text_area("Ticket text", value=selected_prompt)
    submitted = st.form_submit_button("Route Ticket")

if submitted:
    st.session_state["last_result"] = route_ticket(ticket_text)
    st.rerun()

result = st.session_state.get("last_result")

if result:
    st.subheader("Result")
    # Decide highlighting based on sidebar filters
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
    # filtering status message removed to keep UI compact

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
            categories[1:],
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

