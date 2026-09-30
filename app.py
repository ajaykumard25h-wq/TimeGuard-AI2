import os
import sqlite3
import re
from pathlib import Path

import pandas as pd
import streamlit as st
import plotly.express as px

APP_DIR = Path(__file__).parent
DB_PATH = APP_DIR / "timeguard.db"
DATA_DIR = APP_DIR / "data"

st.set_page_config(
    page_title="TimeGuard AI",
    page_icon="⏱️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# -----------------------------
# Database
# -----------------------------
def db():
    return sqlite3.connect(DB_PATH)


def init_db():
    con = db()
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS employees (
            employee_id TEXT PRIMARY KEY, employee_name TEXT, department TEXT, designation TEXT
        );
        CREATE TABLE IF NOT EXISTS projects (
            project_id TEXT PRIMARY KEY, project_name TEXT, client_name TEXT
        );
        CREATE TABLE IF NOT EXISTS timesheets (
            id INTEGER PRIMARY KEY AUTOINCREMENT, employee_id TEXT, project_id TEXT, date TEXT, hours_logged REAL
        );
        CREATE TABLE IF NOT EXISTS leave_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT, employee_id TEXT, leave_date TEXT, leave_type TEXT, leave_status TEXT
        );
        CREATE TABLE IF NOT EXISTS billing_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT, employee_id TEXT, project_id TEXT, date TEXT, approved_hours REAL
        );
        CREATE TABLE IF NOT EXISTS discrepancies (
            id INTEGER PRIMARY KEY AUTOINCREMENT, employee_id TEXT, project_id TEXT, date TEXT,
            discrepancy_type TEXT, expected_value TEXT, actual_value TEXT, severity TEXT,
            description TEXT, status TEXT DEFAULT 'OPEN'
        );
        """
    )
    con.commit()
    con.close()


def seed_if_empty():
    con = db()
    count = int(pd.read_sql("SELECT COUNT(*) AS c FROM employees", con).iloc[0, 0])
    if count == 0:
        for table, file in [
            ("employees", "employees.csv"),
            ("projects", "projects.csv"),
            ("timesheets", "timesheets.csv"),
            ("leave_records", "leave_records.csv"),
            ("billing_records", "billing_records.csv"),
        ]:
            pd.read_csv(DATA_DIR / file).to_sql(table, con, if_exists="append", index=False)
    con.close()


def load(table):
    return pd.read_sql(f"SELECT * FROM {table}", db())


def validate():
    con = db()
    con.execute("DELETE FROM discrepancies")
    ts = pd.read_sql("SELECT * FROM timesheets", con)
    lv = pd.read_sql("SELECT * FROM leave_records", con)
    bill = pd.read_sql("SELECT * FROM billing_records", con)
    emp = pd.read_sql("SELECT * FROM employees", con)
    proj = pd.read_sql("SELECT * FROM projects", con)
    issues = []

    x = ts.merge(lv, left_on=["employee_id", "date"], right_on=["employee_id", "leave_date"], how="inner")
    x = x[(x.hours_logged > 0) & (x.leave_status.str.upper() == "APPROVED")]
    for _, r in x.iterrows():
        issues.append((
            r.employee_id, r.project_id, r.date, "Leave conflict", "0 hours",
            f"{r.hours_logged:g} hours", "High",
            f"Timesheet contains {r.hours_logged:g} hours on an approved {r.leave_type.lower()} leave date."
        ))

    b = ts.merge(bill, on=["employee_id", "project_id", "date"], how="left")
    for _, r in b[b.approved_hours.notna() & (b.hours_logged > b.approved_hours)].iterrows():
        issues.append((
            r.employee_id, r.project_id, r.date, "Billing mismatch",
            f"{r.approved_hours:g} approved hours", f"{r.hours_logged:g} logged hours", "High",
            f"Logged hours exceed approved billing hours by {r.hours_logged-r.approved_hours:g} hour(s)."
        ))

    d = ts[ts.duplicated(["employee_id", "project_id", "date"], keep=False)]
    for _, r in d.drop_duplicates(["employee_id", "project_id", "date"]).iterrows():
        issues.append((
            r.employee_id, r.project_id, r.date, "Duplicate entry", "One entry", "Multiple entries", "Medium",
            "Multiple timesheet records exist for the same employee, project and date."
        ))

    for _, r in ts[ts.hours_logged > 8].iterrows():
        issues.append((
            r.employee_id, r.project_id, r.date, "Excess hours", "≤ 8 hours",
            f"{r.hours_logged:g} hours", "Medium",
            "Logged hours exceed the configured daily threshold of 8 hours."
        ))

    valid_emp, valid_proj = set(emp.employee_id), set(proj.project_id)
    for _, r in ts.iterrows():
        if r.employee_id not in valid_emp:
            issues.append((r.employee_id, r.project_id, r.date, "Invalid mapping", "Known employee", r.employee_id, "High", "Employee ID is not present in the employee master."))
        if r.project_id not in valid_proj:
            issues.append((r.employee_id, r.project_id, r.date, "Invalid mapping", "Known project", r.project_id, "High", "Project ID is not present in the project master."))

    if issues:
        con.executemany(
            """INSERT INTO discrepancies
            (employee_id,project_id,date,discrepancy_type,expected_value,actual_value,severity,description)
            VALUES (?,?,?,?,?,?,?,?)""",
            issues,
        )
    con.commit()
    con.close()


# -----------------------------
# Styling
# -----------------------------
st.markdown(
    """
    <style>
    .stApp { background: #f4f7fb; }
    [data-testid="stHeader"] { background: rgba(0,0,0,0); }
    .block-container { padding-top: 1.2rem; padding-bottom: 2rem; max-width: 1450px; }

    .hero {
        background: linear-gradient(135deg, #101b3f 0%, #182b59 55%, #244b78 100%);
        padding: 28px 32px;
        border-radius: 22px;
        color: white;
        margin-bottom: 22px;
        box-shadow: 0 12px 35px rgba(16,27,63,.16);
    }
    .hero h1 { margin: 0; font-size: 2.25rem; letter-spacing: -0.03em; }
    .hero p { margin: 8px 0 0; color: #d8e3f4; font-size: 1rem; }
    .badge {
        display:inline-block; padding:5px 10px; border-radius:999px;
        background:#d8f3e5; color:#11643b; font-size:.78rem; font-weight:700;
        margin-bottom:10px;
    }

    .metric-card {
        background: white; border: 1px solid #e5eaf2; border-radius: 16px;
        padding: 17px 18px; min-height: 105px;
        box-shadow: 0 5px 18px rgba(25,43,70,.06);
    }
    .metric-label { color:#667085; font-size:.82rem; font-weight:600; }
    .metric-value { color:#101828; font-size:1.75rem; font-weight:800; margin-top:5px; }
    .metric-sub { color:#98a2b3; font-size:.72rem; margin-top:2px; }

    .section-title { font-size:1.15rem; font-weight:800; color:#172033; margin: 8px 0 10px; }
    .section-sub { color:#667085; font-size:.88rem; margin-bottom:12px; }
    .query-card {
        background:white; border:1px solid #e5eaf2; border-radius:18px;
        padding:22px; box-shadow:0 7px 22px rgba(25,43,70,.06);
    }
    .pill { background:#eef4ff; color:#315a9d; padding:6px 10px; border-radius:999px; font-size:.76rem; margin-right:6px; }
    div[data-testid="stSidebar"] { background:#ffffff; border-right:1px solid #e7ebf2; }
    div[data-testid="stSidebar"] .block-container { padding-top: 1.4rem; }
    .sidebar-note { background:#f4f7fb; border:1px solid #e7ebf2; padding:12px; border-radius:12px; font-size:.78rem; color:#667085; }
    </style>
    """,
    unsafe_allow_html=True,
)


# -----------------------------
# Query engine
# -----------------------------
def dataframe_context():
    ts = load("timesheets")
    emp = load("employees")
    proj = load("projects")
    disc = load("discrepancies")
    lv = load("leave_records")
    bill = load("billing_records")
    return ts, emp, proj, disc, lv, bill


def deterministic_query(q):
    """Broader local query layer. No API key required.
    It supports many phrasings, but it is still rule-based rather than an LLM.
    """
    ql = re.sub(r"[^a-z0-9 ]", " ", q.lower())
    ql = re.sub(r"\s+", " ", ql).strip()
    ts, emp, proj, disc, lv, bill = dataframe_context()

    # Direct entity filtering
    matched_project = None
    for name in proj.project_name.dropna():
        if name.lower() in ql:
            matched_project = name
            break
    matched_employee = None
    for name in emp.employee_name.dropna():
        if name.lower() in ql:
            matched_employee = name
            break

    if matched_project:
        pid = proj.loc[proj.project_name == matched_project, "project_id"].iloc[0]
        ts = ts[ts.project_id == pid]
        disc = disc[disc.project_id == pid]
        bill = bill[bill.project_id == pid]

    if matched_employee:
        eid = emp.loc[emp.employee_name == matched_employee, "employee_id"].iloc[0]
        ts = ts[ts.employee_id == eid]
        disc = disc[disc.employee_id == eid]
        lv = lv[lv.employee_id == eid]

    # Intent detection
    if any(x in ql for x in ["leave", "vacation", "holiday"]):
        d = disc[disc.discrepancy_type == "Leave conflict"]
        if d.empty:
            return "No leave-related discrepancies were found for the current data scope.", d
        msg = f"I found **{len(d)} leave-related discrepancy record(s)**."
        return msg, d

    if any(x in ql for x in ["billing", "billable", "client approved", "approved hours"]):
        d = disc[disc.discrepancy_type == "Billing mismatch"]
        if d.empty:
            return "No billing discrepancies were found for the current data scope.", d
        return f"I found **{len(d)} billing discrepancy record(s)**.", d

    if any(x in ql for x in ["duplicate", "duplicates", "repeated entry"]):
        d = disc[disc.discrepancy_type == "Duplicate entry"]
        return f"There are **{len(d)} duplicate-entry issue(s)** in the current scope.", d

    if any(x in ql for x in ["excess hours", "overtime", "over 8", "more than 8"]):
        d = disc[disc.discrepancy_type == "Excess hours"]
        return f"There are **{len(d)} excess-hours issue(s)** in the current scope.", d

    if any(x in ql for x in ["unresolved", "open issue", "open issues", "pending issue"]):
        d = disc[disc.status == "OPEN"]
        return f"There are **{len(d)} open discrepancy record(s)** requiring review.", d

    # Workload / hours questions
    if any(x in ql for x in ["workload", "worked", "working", "hours", "effort", "work"]):
        if any(x in ql for x in ["employee", "person", "who", "people", "staff"]):
            x = ts.groupby("employee_id", as_index=False).hours_logged.sum().rename(columns={"hours_logged": "total_hours"})
            x = x.merge(emp, on="employee_id").sort_values("total_hours", ascending=False)
            if x.empty:
                return "There is no timesheet data for that question.", x
            if any(x in ql for x in ["highest", "most", "maximum", "top", "more"]):
                r = x.iloc[0]
                return f"**{r.employee_name}** has the highest recorded workload at **{r.total_hours:g} hours** in the current scope.", x.head(10)
            return "Here is the employee workload summary based on recorded timesheet hours.", x[["employee_name", "department", "designation", "total_hours"]].head(15)

        if any(x in ql for x in ["project", "projects"]):
            x = ts.groupby("project_id", as_index=False).hours_logged.sum().rename(columns={"hours_logged": "total_hours"})
            x = x.merge(proj, on="project_id").sort_values("total_hours", ascending=False)
            if x.empty:
                return "There is no project timesheet data for that question.", x
            return "Here is the project workload summary based on recorded timesheet hours.", x[["project_name", "client_name", "total_hours"]]

        return f"The current scope contains **{ts.hours_logged.sum():g} logged hours** across **{ts.employee_id.nunique()} employees** and **{ts.project_id.nunique()} projects**.", ts.head(20)

    if any(x in ql for x in ["how many", "count", "number of", "total issues", "discrepancies"]):
        return f"There are **{len(disc)} discrepancy record(s)** in the current scope.", disc

    if "project" in ql and any(x in ql for x in ["highest", "most", "max", "more"]):
        x = disc.groupby("project_id").size().reset_index(name="discrepancies").sort_values("discrepancies", ascending=False)
        x = x.merge(proj, on="project_id")
        if x.empty:
            return "No project discrepancy data is available.", x
        r = x.iloc[0]
        return f"**{r.project_name}** currently has the highest number of recorded discrepancies (**{int(r.discrepancies)}**).", x

    return None, pd.DataFrame()


def get_gemini_key():
    try:
        if "GEMINI_API_KEY" in st.secrets:
            return st.secrets["GEMINI_API_KEY"]
    except Exception:
        pass
    return os.getenv("GEMINI_API_KEY")


def gemini_query(q):
    """Optional free-form AI layer. Deterministic rules remain the source of truth for compliance flags."""
    api_key = get_gemini_key()
    if not api_key:
        return None
    try:
        from google import genai

        ts, emp, proj, disc, lv, bill = dataframe_context()
        context = f"""
You are the TimeGuard AI analytics assistant. Answer the user's question using ONLY the supplied synthetic business data.
Do not invent records. If the data cannot answer the question, say so.
Compliance flags are generated by deterministic validation rules; do not create new compliance findings.
Use concise business language and show the calculation when useful.

EMPLOYEES:
{emp.to_csv(index=False)}

PROJECTS:
{proj.to_csv(index=False)}

TIMESHEETS:
{ts.to_csv(index=False)}

LEAVE RECORDS:
{lv.to_csv(index=False)}

BILLING RECORDS:
{bill.to_csv(index=False)}

DISCREPANCIES:
{disc.to_csv(index=False)}

USER QUESTION:
{q}
"""
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model="gemini-3.8-flash",
            contents=context,
        )
        return response.text
    except Exception as exc:
        return f"Gemini could not answer this query right now. Local query mode is still available. ({type(exc).__name__})"


# -----------------------------
# App boot
# -----------------------------
init_db()
seed_if_empty()
validate()

disc = load("discrepancies")
ts = load("timesheets")
emp = load("employees")
proj = load("projects")
lv = load("leave_records")
bill = load("billing_records")

# -----------------------------
# Sidebar
# -----------------------------
with st.sidebar:
    st.markdown("## ⏱️ TimeGuard")
    st.caption("Compliance + workforce intelligence")
    st.markdown("---")
    st.markdown("### Dashboard filters")
    project_filter = st.selectbox("Project", ["All projects"] + list(proj.project_name))
    status_filter = st.selectbox("Issue status", ["All statuses"] + sorted(disc.status.dropna().unique().tolist()))
    st.markdown("---")
    if st.button("🔄 Re-run validation", use_container_width=True, type="primary"):
        validate()
        st.rerun()
    st.markdown("<div class='sidebar-note'><b>Demo data</b><br>All records are synthetic. Compliance checks are deterministic and can be re-run after data changes.</div>", unsafe_allow_html=True)

# Apply project filter globally.
view_ts = ts.copy()
view_disc = disc.copy()
if project_filter != "All projects":
    pid = proj.loc[proj.project_name == project_filter, "project_id"].iloc[0]
    view_ts = view_ts[view_ts.project_id == pid]
    view_disc = view_disc[view_disc.project_id == pid]

if status_filter != "All statuses":
    view_disc = view_disc[view_disc.status == status_filter]

# -----------------------------
# Header
# -----------------------------
st.markdown(
    """
    <div class="hero">
      <div class="badge">● LIVE DEMO • SYNTHETIC DATA</div>
      <h1>TimeGuard AI</h1>
      <p>AI-powered timesheet compliance, billing validation and workforce analytics.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

# -----------------------------
# KPI cards
# -----------------------------
kpis = [
    ("Employees", view_ts.employee_id.nunique(), "Active in selected scope"),
    ("Projects", view_ts.project_id.nunique(), "With recorded hours"),
    ("Logged hours", f"{view_ts.hours_logged.sum():,.0f}", "From timesheets"),
    ("Discrepancies", len(view_disc), "Matching selected filters"),
    ("Open issues", int((view_disc.status == "OPEN").sum()), "Require review"),
]
cols = st.columns(5)
for col, (label, value, sub) in zip(cols, kpis):
    with col:
        st.markdown(
            f'<div class="metric-card"><div class="metric-label">{label}</div><div class="metric-value">{value}</div><div class="metric-sub">{sub}</div></div>',
            unsafe_allow_html=True,
        )

st.write("")

# -----------------------------
# Main dashboard
# -----------------------------
left, right = st.columns(2)
with left:
    st.markdown('<div class="section-title">🚨 Discrepancy mix</div><div class="section-sub">What is being flagged in the selected scope.</div>', unsafe_allow_html=True)
    dtype = view_disc.groupby("discrepancy_type").size().reset_index(name="count")
    if dtype.empty:
        st.info("No discrepancies match the selected filters.")
    else:
        fig = px.bar(dtype, x="discrepancy_type", y="count", text="count")
        fig.update_layout(height=330, margin=dict(l=10, r=10, t=10, b=10), xaxis_title=None, yaxis_title="Issues")
        fig.update_traces(textposition="outside")
        st.plotly_chart(fig, use_container_width=True)

with right:
    st.markdown('<div class="section-title">📊 Project workload</div><div class="section-sub">Recorded timesheet hours by project.</div>', unsafe_allow_html=True)
    workload = view_ts.groupby("project_id", as_index=False).hours_logged.sum().merge(proj, on="project_id")
    if workload.empty:
        st.info("No workload data matches the selected filters.")
    else:
        fig = px.bar(workload.sort_values("hours_logged", ascending=True), x="hours_logged", y="project_name", orientation="h", text="hours_logged")
        fig.update_layout(height=330, margin=dict(l=10, r=10, t=10, b=10), xaxis_title="Hours", yaxis_title=None)
        fig.update_traces(textposition="outside")
        st.plotly_chart(fig, use_container_width=True)

left, right = st.columns(2)
with left:
    st.markdown('<div class="section-title">👥 Employee workload & activity</div><div class="section-sub">Descriptive workload indicators — not a performance rating.</div>', unsafe_allow_html=True)
    ew = view_ts.groupby("employee_id", as_index=False).hours_logged.sum().rename(columns={"hours_logged": "total_hours"}).merge(emp, on="employee_id")
    if not ew.empty:
        ew["projects"] = view_ts.groupby("employee_id").project_id.nunique().reindex(ew.employee_id).fillna(0).values
        ew["issues"] = view_disc.groupby("employee_id").size().reindex(ew.employee_id).fillna(0).values
        ew = ew.sort_values("total_hours", ascending=False)
        st.dataframe(
            ew[["employee_name", "department", "projects", "total_hours", "issues"]].rename(columns={"employee_name":"Employee", "department":"Department", "projects":"Projects", "total_hours":"Hours", "issues":"Issues"}),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("No employee activity matches the selected filters.")

with right:
    st.markdown('<div class="section-title">📈 Discrepancy trend</div><div class="section-sub">Issue volume over time in the selected scope.</div>', unsafe_allow_html=True)
    dt = view_disc.groupby("date").size().reset_index(name="issues").sort_values("date")
    if dt.empty:
        st.info("No trend data matches the selected filters.")
    else:
        fig = px.line(dt, x="date", y="issues", markers=True)
        fig.update_layout(height=330, margin=dict(l=10, r=10, t=10, b=10), xaxis_title=None, yaxis_title="Issues")
        st.plotly_chart(fig, use_container_width=True)

# -----------------------------
# Discrepancy review
# -----------------------------
st.markdown("---")
st.markdown('<div class="section-title">🔎 Discrepancy review</div><div class="section-sub">Use the sidebar filters to narrow the review queue.</div>', unsafe_allow_html=True)
if not view_disc.empty:
    show = view_disc.merge(emp[["employee_id", "employee_name"]], on="employee_id", how="left").merge(proj[["project_id", "project_name"]], on="project_id", how="left")
    st.dataframe(
        show[["employee_name", "project_name", "date", "discrepancy_type", "severity", "description", "status"]].rename(columns={
            "employee_name":"Employee", "project_name":"Project", "date":"Date", "discrepancy_type":"Issue", "severity":"Severity", "description":"Why flagged", "status":"Status"
        }),
        use_container_width=True,
        hide_index=True,
    )
else:
    st.success("No discrepancies match the selected filters.")

# -----------------------------
# AI Query
# -----------------------------
st.markdown("---")
st.markdown('<div class="section-title">💬 Ask TimeGuard</div><div class="section-sub">Ask questions about employees, projects, hours, leave, billing or discrepancies.</div>', unsafe_allow_html=True)

with st.container(border=True):
    q = st.text_input(
        "",
        placeholder="e.g. Who worked the most hours? Which project has the most issues? Show billing mismatches for Atlas ERP.",
        label_visibility="collapsed",
    )
    mode = st.radio("Query mode", ["Smart local mode", "Gemini AI mode"], horizontal=True, help="Local mode is free and rule-based. Gemini mode enables broader natural-language questions when GEMINI_API_KEY is configured.")
    st.caption("Examples: “How many leave conflicts are there?” • “Show employees with the highest workload” • “What billing issues exist for Atlas ERP?”")

    if q:
        if mode == "Gemini AI mode":
            answer = gemini_query(q)
            if answer is None:
                st.warning("Gemini mode needs a GEMINI_API_KEY. Switching to Smart local mode for this query.")
                msg, result = deterministic_query(q)
                if msg is None:
                    st.info("I couldn't map that question to the local analytics rules. Try Gemini mode for free-form questions.")
                else:
                    st.markdown(msg)
                    if not result.empty:
                        st.dataframe(result, use_container_width=True, hide_index=True)
            else:
                st.markdown(answer)
        else:
            msg, result = deterministic_query(q)
            if msg is None:
                st.info("I couldn't map that question in local mode. Use Gemini AI mode for broader natural-language questions.")
            else:
                st.markdown(msg)
                if not result.empty:
                    st.dataframe(result, use_container_width=True, hide_index=True)

# -----------------------------
# Workflow / architecture
# -----------------------------
st.markdown("---")
left, right = st.columns(2)
with left:
    st.markdown('<div class="section-title">🔁 Correction & revalidation</div>', unsafe_allow_html=True)
    st.markdown("**Detect → Notify → Employee corrects → Re-upload → Revalidate → Resolve**")
    st.caption("The MVP demonstrates detection and revalidation-ready architecture. Production would add authenticated uploads, notifications and approval workflows.")
with right:
    st.markdown('<div class="section-title">🧠 AI architecture</div>', unsafe_allow_html=True)
    st.markdown("**Structured data → deterministic validation → discrepancy store → controlled AI query → human review**")

with st.expander("Technical architecture"):
    st.code(
        """CSV / Excel\n   ↓\nPandas data processing\n   ↓\nSQLite (MVP) / PostgreSQL (production)\n   ↓\nDeterministic compliance engine\n   ↓\nDiscrepancy store\n   ↓\nDashboard + AI query layer\n   ↓\nHuman review / correction / revalidation""",
        language="text",
    )
