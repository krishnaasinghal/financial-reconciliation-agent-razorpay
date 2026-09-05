"""AI explanation layer for deterministic reconciliation results."""
from __future__ import annotations
import os
from reconcile import KB_RULES, reconcile, summarize


def explain(result) -> str:
    citation = f" (per {KB_RULES[result.anomaly_type]})" if result.anomaly_type else ""
    if result.anomaly_type == "PARTIAL_SETTLEMENT":
        return f"The bank credit is below the deterministic expected net by INR {abs(result.difference or 0):,.2f}. This may reflect a reserve, split settlement, adjustment, or pending release.{citation}"
    if result.anomaly_type == "MISSING_SETTLEMENT":
        return f"The payment was captured, but no settlement record or bank credit is present yet.{citation}"
    if result.anomaly_type == "DELAYED_SETTLEMENT":
        return f"The amount agrees, but the settlement arrived outside the normal settlement window.{citation}"
    if result.anomaly_type == "DUPLICATE_BANK_CREDIT":
        return f"More than one bank credit references the same settlement and should be reviewed before posting.{citation}"
    if result.anomaly_type == "UNMATCHED_BANK_CREDIT":
        return f"This bank credit has no matching payment settlement in the synthetic batch.{citation}"
    if result.anomaly_type:
        return f"The deterministic engine flagged {result.anomaly_type.replace('_', ' ').lower()} for review.{citation}"
    return "The payment, settlement, and bank credit agree within tolerance."


def run(question: str, max_steps: int = 5) -> dict:
    results = reconcile()
    summary = summarize(results)
    query = question.lower()
    if "anomal" in query or "exception" in query:
        selected = [row for row in results if row.anomaly_type][:5]
        answer = f"The deterministic engine found {sum(summary['by_anomaly'].values())} anomaly records. " + " ".join(explain(row) for row in selected[:2])
    else:
        answer = f"The batch contains {summary['total_results']} reconciliation records and {summary['matched_transactions']} matched transactions. All monetary values came from deterministic Python calculations."
    return {"answer": answer, "trace": [{"tool": "reconcile", "args": {}, "result": summary}], "offline": True}
