"""Streamlit dashboard for Razorpay-style payment settlement reconciliation."""
from __future__ import annotations
import csv
import os
import random
import sys
import tempfile
import time
import uuid
from pathlib import Path
import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.dirname(__file__))
from agent import explain
import reconcile as reconciliation_module
from reconcile import reconcile, summarize
from evaluate import _metrics, _truth
from generate_data import SCENARIOS, build as build_synthetic_world
from knowledge_base import load

st.set_page_config(page_title="Settlement Control Room | AI Finance Controller", page_icon="💳", layout="wide")
st.markdown("""
<style>
        @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Space+Grotesk:wght@500;600;700&display=swap');
        :root { --ink: #17212b; --muted: #687782; --teal: #087f8c; --mint: #dff4ef; --coral: #e56b54; --line: #dfe7e8; --paper: #f7faf9; }
        .stApp { background: var(--paper); color: var(--ink); }
        [data-testid="stHeader"] { background: rgba(247, 250, 249, 0.88); }
        [data-testid="stSidebar"] { background: #eef6f4; border-right: 1px solid var(--line); }
        .block-container { max-width: 1420px; padding-top: 2.2rem; padding-bottom: 3rem; }
        h1, h2, h3 { font-family: 'Space Grotesk', sans-serif; color: var(--ink); letter-spacing: 0; }
        p, label, .stMarkdown, .stCaption { font-family: 'DM Sans', sans-serif; }
        .hero { display: flex; justify-content: space-between; align-items: end; gap: 2rem; padding: 1.6rem 1.8rem; margin-bottom: 1.4rem; background: #ffffff; border: 1px solid var(--line); border-left: 6px solid var(--teal); border-radius: 12px; box-shadow: 0 8px 24px rgba(23, 33, 43, 0.05); }
        .hero-kicker { color: var(--teal); font-size: 0.75rem; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; }
        .hero-title { margin: 0.3rem 0 0; font-family: 'Space Grotesk', sans-serif; font-size: 2.25rem; font-weight: 700; line-height: 1.05; }
        .hero-copy { max-width: 690px; margin: 0.7rem 0 0; color: var(--muted); font-size: 0.98rem; line-height: 1.55; }
        .hero-mark { display: grid; place-items: center; width: 68px; height: 68px; flex: 0 0 68px; background: var(--mint); border: 1px solid #b9e4da; border-radius: 16px; color: var(--teal); font-size: 2rem; }
        [data-testid="stMetric"] { background: #ffffff; border: 1px solid var(--line); border-radius: 10px; padding: 1rem 1.1rem; box-shadow: 0 5px 16px rgba(23, 33, 43, 0.04); }
        [data-testid="stMetricLabel"] { color: var(--muted); font-weight: 600; }
        [data-testid="stMetricValue"] { color: var(--ink); font-family: 'Space Grotesk', sans-serif; }
        div[data-baseweb="tab-list"] { gap: 0.35rem; border-bottom: 1px solid var(--line); }
        div[data-baseweb="tab-list"] button[data-baseweb="tab"] { color: #41515c !important; font-weight: 700; opacity: 1 !important; background: transparent; }
        div[data-baseweb="tab-list"] button[data-baseweb="tab"] p { color: inherit !important; }
        div[data-baseweb="tab-list"] button[data-baseweb="tab"][aria-selected="true"] { color: #087f8c !important; border-bottom: 3px solid #087f8c; }
        .section-kicker { color: var(--teal); font-size: 0.75rem; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; margin-top: 1rem; }
        .stButton > button, .stDownloadButton > button { border-radius: 8px; border: 1px solid var(--teal); color: white; background: var(--teal); font-weight: 700; }
        .stButton > button:hover, .stDownloadButton > button:hover { border-color: #05616b; background: #05616b; color: white; }
        [data-testid="stDataFrame"] { border: 1px solid var(--line); border-radius: 10px; overflow: hidden; }
        div[data-testid="stExpander"] { border-color: var(--line); border-radius: 10px; background: #ffffff; overflow: hidden; }
        div[data-testid="stExpander"] details summary { background: #e7f3f0 !important; color: #17212b !important; }
        div[data-testid="stExpander"] details summary:hover { background: #d5ebe6 !important; }
        div[data-testid="stExpander"] details summary p, div[data-testid="stExpander"] details summary span { color: #17212b !important; font-weight: 700; }
</style>
<div class="hero">
    <div>
        <div class="hero-kicker">AI Finance Controller · Track 4</div>
        <div class="hero-title">Settlement Control Room</div>
        <p class="hero-copy">A focused view of payment settlement health, exceptions, and the next action for finance. Every amount is verified by deterministic Python; AI explains the evidence.</p>
    </div>
    <div class="hero-mark">₹</div>
</div>
""", unsafe_allow_html=True)

SUGGESTED_ACTIONS = {
    "MISSING_SETTLEMENT": "Check the T+3 window; escalate to Razorpay ops if still missing.",
    "FEE_MISMATCH": "Recalculate the fee and file a fee dispute with Razorpay ops.",
    "PARTIAL_SETTLEMENT": "Check holds, reserves, split releases, and the remaining unreconciled balance.",
    "DELAYED_SETTLEMENT": "Review settlement timing and escalate if the delayed credit is not explained.",
    "DUPLICATE_BANK_CREDIT": "Flag for manual reversal before month-end close; do not double-count it.",
    "UNMATCHED_BANK_CREDIT": "Search adjustments and UTRs, then route the credit to finance review.",
    "AMOUNT_MISMATCH": "Compare gateway and bank reports, then open an investigation for the difference.",
}


def anomaly_trace(row) -> list[str]:
    """Describe the deterministic branches that produced this result."""
    trace = []
    if row.payment_id:
        trace.append("Checked the captured payment against its merchant order amount.")
        if row.status == "PENDING" and row.anomaly_type == "MISSING_SETTLEMENT":
            trace.append("Checked for a linked settlement and bank credit; one was missing.")
        else:
            trace.append("Calculated expected net as gross amount minus gateway fee and tax on fee.")
            if row.anomaly_type == "DUPLICATE_BANK_CREDIT":
                trace.append("Checked settlement references and found more than one bank credit.")
            elif row.anomaly_type == "DELAYED_SETTLEMENT":
                trace.append("Compared settlement date with payment creation date and found a late settlement.")
            elif row.actual_amount is not None:
                trace.append("Compared expected net with the actual bank credit and found a difference.")
    else:
        trace.append("Inspected the bank credit for a matching payment settlement.")
        trace.append("No matching payment settlement was found.")
    trace.append(f"Applied the cited policy rule and flagged {row.anomaly_type}.")
    return trace


def _create_test_order(amount_rupees: float) -> tuple[str, str, float]:
    """Create one live test order, falling back to a previously issued ID."""
    try:
        import razorpay

        key_id = os.environ.get("RAZORPAY_KEY_ID")
        key_secret = os.environ.get("RAZORPAY_KEY_SECRET")
        if not key_id or not key_secret:
            raise RuntimeError("Razorpay test credentials are not configured")
        client = razorpay.Client(auth=(key_id, key_secret))
        order = client.order.create({
            "amount": int(round(amount_rupees * 100)),
            "currency": "INR",
            "receipt": f"live_sim_{uuid.uuid4().hex[:10]}",
            "notes": {"source": "settlement-control-room-live-simulator"},
        })
        return order["id"], "real Razorpay test-mode order", amount_rupees
    except Exception as error:
        fallback_path = Path(__file__).resolve().parents[1] / "real_razorpay_orders.csv"
        if not fallback_path.exists():
            raise RuntimeError(f"Razorpay API failed and no fallback order file exists: {error}") from error
        fallback = pd.read_csv(fallback_path).iloc[0]
        return str(fallback["order_id"]), "using a previously created live order - network hiccup", float(fallback["amount"])


def _scale(value: str | float, ratio: float) -> float:
    return round(float(value) * ratio, 2)


def _simulation_world(order_id: str, amount: float, scenario: str) -> dict[str, list[dict]]:
    """Adapt one existing generator scenario to the live order amount and ID."""
    world = build_synthetic_world()
    index = next(i for i, row in enumerate(world["truth"]) if row["expected_status"] == scenario)
    template_order = world["orders"][index]
    template_payment = world["payments"][index]
    template_amount = float(template_order["order_amount"])
    ratio = amount / template_amount
    payment_id = f"sim_pay_{uuid.uuid4().hex[:10]}"
    settlement_id = f"sim_stl_{uuid.uuid4().hex[:10]}"
    bank_prefix = f"sim_bnk_{uuid.uuid4().hex[:8]}"
    order = dict(template_order)
    order.update({"order_id": order_id, "order_amount": amount})
    payment = dict(template_payment)
    payment.update({"payment_id": payment_id, "order_id": order_id, "amount": amount})
    settlements = []
    for row in world["settlements"]:
        if row["payment_id"] != template_payment["payment_id"]:
            continue
        settlement = dict(row)
        settlement.update({"settlement_id": settlement_id, "payment_id": payment_id, "gross_amount": _scale(row["gross_amount"], ratio), "gateway_fee": _scale(row["gateway_fee"], ratio), "tax_on_fee": _scale(row["tax_on_fee"], ratio), "net_amount": _scale(row["net_amount"], ratio)})
        settlements.append(settlement)
    credits = []
    for credit in world["credits"]:
        if credit["settlement_id"] == world["truth"][index]["settlement_id"] or (scenario == "UNMATCHED_BANK_CREDIT" and credit["bank_transaction_id"] == world["truth"][index]["bank_transaction_id"]):
            bank_credit = dict(credit)
            bank_credit.update({"bank_transaction_id": f"{bank_prefix}_{len(credits)}", "settlement_id": settlement_id if scenario != "UNMATCHED_BANK_CREDIT" else f"sim_unknown_{uuid.uuid4().hex[:6]}", "credited_amount": _scale(credit["credited_amount"], ratio)})
            credits.append(bank_credit)
    if scenario == "DUPLICATE_BANK_CREDIT" and len(credits) > 1:
        credits = credits[:2]
    return {"orders": [order], "payments": [payment], "settlements": settlements, "credits": credits}


def _write_simulation_files(root: Path, world: dict[str, list[dict]]) -> None:
    fields = {
        "merchant_orders.csv": ["order_id", "merchant_id", "customer_id", "order_amount", "currency", "order_date", "order_status"],
        "payments.csv": ["payment_id", "order_id", "merchant_id", "amount", "payment_method", "payment_status", "created_at"],
        "settlements.csv": ["settlement_id", "payment_id", "merchant_id", "gross_amount", "gateway_fee", "tax_on_fee", "net_amount", "settlement_date", "settlement_status"],
        "bank_credits.csv": ["bank_transaction_id", "settlement_id", "merchant_id", "credited_amount", "credit_date", "bank_reference"],
    }
    world_keys = {"merchant_orders.csv": "orders", "payments.csv": "payments", "settlements.csv": "settlements", "bank_credits.csv": "credits"}
    for filename, columns in fields.items():
        with (root / filename).open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=columns)
            writer.writeheader()
            writer.writerows(world[world_keys[filename]])


def run_live_simulation(amount: float, scenario: str) -> tuple[object, str, str]:
    order_id, source, effective_amount = _create_test_order(amount)
    world = _simulation_world(order_id, effective_amount, scenario)
    with tempfile.TemporaryDirectory(prefix="settlement_sim_") as directory:
        root = Path(directory)
        _write_simulation_files(root, world)
        previous_data_dir = reconciliation_module.DATA_DIR
        reconciliation_module.DATA_DIR = root
        try:
            simulated_results = reconcile()
        finally:
            reconciliation_module.DATA_DIR = previous_data_dir
    payment_id = world["payments"][0]["payment_id"]
    candidates = [row for row in simulated_results if row.payment_id == payment_id or row.anomaly_type == "UNMATCHED_BANK_CREDIT"]
    result = next((row for row in candidates if row.anomaly_type == scenario), candidates[0])
    return result, order_id, source


def reconcile_simulation_world(world: dict[str, list[dict]]) -> object:
    with tempfile.TemporaryDirectory(prefix="settlement_sim_") as directory:
        root = Path(directory)
        _write_simulation_files(root, world)
        previous_data_dir = reconciliation_module.DATA_DIR
        reconciliation_module.DATA_DIR = root
        try:
            simulated_results = reconcile()
        finally:
            reconciliation_module.DATA_DIR = previous_data_dir
    payment_id = world["payments"][0]["payment_id"]
    candidates = [row for row in simulated_results if row.payment_id == payment_id or row.anomaly_type == "UNMATCHED_BANK_CREDIT"]
    return next((row for row in candidates if row.anomaly_type == scenario), candidates[0])

@st.cache_data
def load_frames():
    root = Path(__file__).resolve().parents[1] / "data"
    return {name.removesuffix(".csv"): pd.read_csv(root / name) for name in ["merchant_orders.csv", "payments.csv", "settlements.csv", "bank_credits.csv"]}

@st.cache_data
def reconciliation_frame():
    results = reconcile()
    return pd.DataFrame([row.__dict__ for row in results]), summarize(results)


@st.cache_data
def load_live_orders():
    path = Path(__file__).resolve().parents[1] / "real_razorpay_orders.csv"
    if not path.exists():
        return None
    live_orders = pd.read_csv(path)
    live_orders["created_at"] = pd.to_datetime(live_orders["created_at"], unit="s", errors="coerce").dt.strftime("%Y-%m-%d %H:%M:%S")
    return live_orders

frames = load_frames()
rec_df, summary = reconciliation_frame()
results = reconcile()
live_orders = load_live_orders()
if "simulator_rows" not in st.session_state:
    st.session_state.simulator_rows = []
simulator_rows = st.session_state.simulator_rows
simulator_df = pd.DataFrame(simulator_rows)
display_rec_df = pd.concat([simulator_df, rec_df], ignore_index=True) if not simulator_df.empty else rec_df
tabs = st.tabs(["Overview", "Reconciliation", "Anomalies", "Data Explorer", "Evaluation", "Live Integration", "Live Simulator"])
with tabs[0]:
    with st.expander("How this works", expanded=True):
        st.write("The LLM proposes, deterministic code disposes. Python validates order, payment, settlement, and bank-credit amounts; AI only explains flagged anomalies and cites policy rules.")
    metrics = [
        ("💳 Total Payments", len(frames["payments"]) + len(simulator_rows)), ("💰 Total Settled Amount", f"INR {frames['settlements']['net_amount'].sum() + sum(row.get('actual_amount') or 0 for row in simulator_rows):,.2f}"),
        ("✅ Matched Transactions", summary["by_status"].get("MATCHED", 0) + sum(row.get("status") == "MATCHED" for row in simulator_rows)), ("🕒 Pending Transactions", summary["by_status"].get("PENDING", 0) + sum(row.get("status") == "PENDING" for row in simulator_rows)),
        ("⚠️ Mismatched Transactions", summary["by_status"].get("MISMATCHED", 0) + sum(row.get("status") == "MISMATCHED" for row in simulator_rows)), ("🚨 Anomalies Detected", sum(summary["by_anomaly"].values()) + sum(bool(row.get("anomaly_type")) for row in simulator_rows)),
    ]
    columns = st.columns(3)
    for index, (label, value) in enumerate(metrics):
        columns[index % 3].metric(label, value)
    st.subheader("Anomaly distribution")
    st.bar_chart(pd.Series(summary["by_anomaly"], name="records"))
    evaluation = _metrics(results, _truth())
    top_anomalies = sorted(summary["by_anomaly"].items(), key=lambda item: item[1], reverse=True)[:3]
    executive_summary = "\n".join([
        "# Settlement Control Room - Executive Summary",
        "",
        f"Total reconciliation transactions: {summary['total_results']}",
        f"Match rate: {summary['by_status'].get('MATCHED', 0) / max(1, summary['total_results']):.1%}",
        f"Precision: {evaluation['precision']:.1%}",
        f"Recall: {evaluation['recall']:.1%}",
        f"F1: {evaluation['f1']:.1%}",
        "",
        "Top anomaly types:",
        *[f"- {name}: {count}" for name, count in top_anomalies],
        "",
        "Live Razorpay test-mode orders were used as an API integration touchpoint; reconciliation evaluation uses reproducible synthetic settlement data.",
    ])
    st.download_button("Download executive summary", executive_summary, "settlement_executive_summary.md", "text/markdown")
with tabs[1]:
    selected = st.multiselect("Status", ["MATCHED", "PENDING", "MISMATCHED", "UNMATCHED", "DUPLICATE"], default=["MATCHED", "PENDING", "MISMATCHED", "UNMATCHED", "DUPLICATE"])
    exceptions = display_rec_df[display_rec_df["status"] != "MATCHED"]
    st.download_button("Export exceptions for finance team", exceptions.to_csv(index=False), "settlement_exceptions.csv", "text/csv")
    badge_colors = {"MATCHED": "#15803d", "PENDING": "#b45309", "MISMATCHED": "#b91c1c", "DUPLICATE": "#b91c1c", "UNMATCHED": "#4b5563"}
    badges = " ".join(f'<span style="background:{badge_colors[status]};color:white;padding:4px 9px;border-radius:999px;font-size:0.8rem">{status}</span>' for status in selected)
    st.markdown(badges, unsafe_allow_html=True)
    view = display_rec_df[display_rec_df["status"].isin(selected)]
    st.dataframe(view[["payment_id", "settlement_id", "bank_transaction_id", "expected_amount", "actual_amount", "difference", "status", "anomaly_type", "reason"]], use_container_width=True, hide_index=True)
    st.subheader("Ask the agent")
    payment_query = st.text_input("Enter a payment ID", placeholder="pay_001002")
    if payment_query:
        matches = display_rec_df[display_rec_df["payment_id"].astype(str).str.lower() == payment_query.strip().lower()]
        if matches.empty:
            st.warning(f"I could not find payment `{payment_query.strip()}` in this reconciliation batch.")
        else:
            record = matches.iloc[0]
            expected = f"INR {record['expected_amount']:,.2f}" if pd.notna(record["expected_amount"]) else "not available"
            actual = f"INR {record['actual_amount']:,.2f}" if pd.notna(record["actual_amount"]) else "not available"
            st.info(
                f"Payment `{record['payment_id']}` is **{record['status']}**. "
                f"Expected amount: **{expected}**. Actual amount: **{actual}**. "
                f"Difference: **INR {record['difference']:,.2f}**. "
                f"{record['reason']}"
            )
with tabs[2]:
    anomalies = [row for row in results if row.anomaly_type]
    for row in anomalies[:50]:
        with st.container(border=True):
            st.markdown(f"**{row.anomaly_type}**  |  `{row.payment_id or row.bank_transaction_id}`")
            st.write(f"Expected: INR {row.expected_amount:,.2f}" if row.expected_amount is not None else "Expected: unavailable")
            st.write(f"Actual: INR {row.actual_amount:,.2f}" if row.actual_amount is not None else "Actual: unavailable")
            st.write(f"Difference: INR {row.difference:,.2f}" if row.difference is not None else "Difference: unavailable")
            st.caption(row.reason)
            st.info(explain(row))
            st.warning(f"Suggested next action: {SUGGESTED_ACTIONS[row.anomaly_type]}")
            with st.expander("Agent reasoning trace"):
                for step_number, step in enumerate(anomaly_trace(row), 1):
                    st.write(f"{step_number}. {step}")
with tabs[3]:
    entity = st.selectbox("Dataset", list(frames))
    st.dataframe(frames[entity], use_container_width=True, hide_index=True)
with tabs[4]:
    report = _metrics(results, _truth())
    cols = st.columns(4)
    for column, key in zip(cols, ["reconciliation_accuracy", "precision", "recall", "f1"]):
        column.metric(key.replace("_", " ").title(), f"{report[key]:.1%}")
    st.dataframe(pd.DataFrame(report["accuracy_by_anomaly_type"].items(), columns=["Anomaly", "Accuracy"]), use_container_width=True, hide_index=True)
    st.caption(f"Policy knowledge base: {len(load())} settlement rules")
with tabs[5]:
    st.subheader("Razorpay test-mode orders")
    if live_orders is None:
        st.info("No real_razorpay_orders.csv found. Run fetch_real_razorpay_orders.py with Razorpay test credentials to create the live API proof.")
    else:
        st.caption("These order IDs were issued by the Razorpay test-mode API. Settlement evaluation remains synthetic and reproducible.")
        st.dataframe(live_orders[["order_id", "amount", "currency", "created_at", "status", "receipt"]], use_container_width=True, hide_index=True)
with tabs[6]:
    st.subheader("Live Transaction Simulator")
    st.caption("Creates one Razorpay test-mode order, injects an existing settlement scenario, and runs the unchanged reconciliation and explanation paths.")
    counter_col, tally_col = st.columns(2)
    counter_col.metric("Simulator session", len(simulator_rows))
    tally_col.caption("Separate from the validated 150-transaction Evaluation batch.")
    if st.button("Create Live Transaction", type="primary"):
        requested_amount = round(random.uniform(500, 15000), 2)
        scenario = random.choice(SCENARIOS)
        with st.spinner("Step 1/4 - Creating one Razorpay test-mode order..."):
            order_id, source, effective_amount = _create_test_order(requested_amount)
            time.sleep(0.6)
        st.success(f"Step 1: Real Razorpay order created: `{order_id}` (amount: INR {effective_amount:,.2f})")
        if source != "real Razorpay test-mode order":
            st.caption(f"{source}")

        with st.spinner("Step 2/4 - Generating settlement and bank credit..."):
            world = _simulation_world(order_id, effective_amount, scenario)
            time.sleep(0.6)
        settlement_text = "no settlement generated" if not world["settlements"] else ", ".join(f"net INR {row['net_amount']:,.2f}" for row in world["settlements"])
        credit_text = "no bank credit generated" if not world["credits"] else ", ".join(f"INR {row['credited_amount']:,.2f}" for row in world["credits"])
        st.info(f"Step 2: Scenario `{scenario}` · settlement: {settlement_text} · bank credit: {credit_text}")

        with st.spinner("Step 3/4 - Running reconciliation engine..."):
            result = reconcile_simulation_world(world)
            time.sleep(0.6)
        st.write(f"Step 3: Reconciliation result: **{result.status}**" + (f" · `{result.anomaly_type}`" if result.anomaly_type else ""))
        if result.anomaly_type:
            st.info(f"Step 4: {explain(result)}")
        else:
            st.success("Step 4: No anomaly detected; the payment, settlement, and bank credit agree.")

        simulator_row = result.__dict__.copy()
        simulator_row["simulation_scenario"] = scenario
        simulator_row["order_id"] = order_id
        simulator_row["source"] = source
        st.session_state.simulator_rows.insert(0, simulator_row)
        st.success("Step 5: Added to the top of the Reconciliation table. Overview totals update on the next app rerun.")
