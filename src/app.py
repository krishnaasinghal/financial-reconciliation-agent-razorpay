"""Streamlit dashboard for Razorpay-style payment settlement reconciliation."""
from __future__ import annotations
import os
import sys
from pathlib import Path
import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.dirname(__file__))
from agent import explain
from reconcile import SUGGESTED_ACTIONS, reconcile, summarize
from evaluate import _metrics, _truth
from knowledge_base import load

st.set_page_config(page_title="Settlement Control Room | AI Finance Controller", page_icon="💳", layout="wide")
st.title("Settlement Control Room")
st.caption("Synthetic Razorpay-style payment settlement data. Deterministic code calculates every amount; AI only explains anomalies.")


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

frames = load_frames()
rec_df, summary = reconciliation_frame()
results = reconcile()
tabs = st.tabs(["Overview", "Reconciliation", "Anomalies", "Data Explorer", "Evaluation"])
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
