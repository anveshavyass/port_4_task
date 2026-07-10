import streamlit as st

from app.analytics import build_stats, is_ticket_corrected, is_ticket_resolved, log_correction, record_resolution
from app.router import route_ticket

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
    already_corrected = is_ticket_corrected(result["ticket_id"])

    col1, col2 = st.columns([1, 1])
    with col1:
        if st.button("Mark Resolved", disabled=already_resolved):
            if record_resolution(result["ticket_id"]):
                st.write("Resolution recorded")
                st.rerun()
        if already_resolved:
            st.caption("Already marked resolved.")
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
        st.json(result)

