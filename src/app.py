"""Streamlit dashboard for Razorpay-style payment settlement reconciliation."""
from __future__ import annotations
import os
import sys
from pathlib import Path
import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.dirname(__file__))
from agent import explain
from reconcile import reconcile, summarize
from evaluate import _metrics, _truth
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
        button[data-baseweb="tab"] { color: var(--muted); font-weight: 600; }
        button[data-baseweb="tab"][aria-selected="true"] { color: var(--teal); border-bottom-color: var(--teal); }
        .section-kicker { color: var(--teal); font-size: 0.75rem; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; margin-top: 1rem; }
        .stButton > button, .stDownloadButton > button { border-radius: 8px; border: 1px solid var(--teal); color: white; background: var(--teal); font-weight: 700; }
        .stButton > button:hover, .stDownloadButton > button:hover { border-color: #05616b; background: #05616b; color: white; }
        [data-testid="stDataFrame"] { border: 1px solid var(--line); border-radius: 10px; overflow: hidden; }
        div[data-testid="stExpander"] { border-color: var(--line); border-radius: 10px; background: #ffffff; }
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
tabs = st.tabs(["Overview", "Reconciliation", "Anomalies", "Data Explorer", "Evaluation", "Live Integration"])
with tabs[0]:
    with st.expander("How this works", expanded=True):
        st.write("The LLM proposes, deterministic code disposes. Python validates order, payment, settlement, and bank-credit amounts; AI only explains flagged anomalies and cites policy rules.")
    metrics = [
        ("💳 Total Payments", len(frames["payments"])), ("💰 Total Settled Amount", f"INR {frames['settlements']['net_amount'].sum():,.2f}"),
        ("✅ Matched Transactions", summary["by_status"].get("MATCHED", 0)), ("🕒 Pending Transactions", summary["by_status"].get("PENDING", 0)),
        ("⚠️ Mismatched Transactions", summary["by_status"].get("MISMATCHED", 0)), ("🚨 Anomalies Detected", sum(summary["by_anomaly"].values())),
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
    exceptions = rec_df[rec_df["status"] != "MATCHED"]
    st.download_button("Export exceptions for finance team", exceptions.to_csv(index=False), "settlement_exceptions.csv", "text/csv")
    badge_colors = {"MATCHED": "#15803d", "PENDING": "#b45309", "MISMATCHED": "#b91c1c", "DUPLICATE": "#b91c1c", "UNMATCHED": "#4b5563"}
    badges = " ".join(f'<span style="background:{badge_colors[status]};color:white;padding:4px 9px;border-radius:999px;font-size:0.8rem">{status}</span>' for status in selected)
    st.markdown(badges, unsafe_allow_html=True)
    view = rec_df[rec_df["status"].isin(selected)]
    st.dataframe(view[["payment_id", "settlement_id", "bank_transaction_id", "expected_amount", "actual_amount", "difference", "status", "anomaly_type", "reason"]], use_container_width=True, hide_index=True)
    st.subheader("Ask the agent")
    payment_query = st.text_input("Enter a payment ID", placeholder="pay_001002")
    if payment_query:
        matches = rec_df[rec_df["payment_id"].astype(str).str.lower() == payment_query.strip().lower()]
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
