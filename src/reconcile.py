"""Deterministic multi-stage payment settlement reconciliation engine."""
from __future__ import annotations
import csv
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from schema import ReconciliationResult

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
TOLERANCE = 0.01
KB_RULES = {
    "MISSING_SETTLEMENT": "KB-01: Captured payments may remain pending until the gateway creates a settlement.",
    "FEE_MISMATCH": "KB-02: Gateway fee is 2% plus 18% GST on the fee, applied to gross amount.",
    "PARTIAL_SETTLEMENT": "KB-03: Holds, reserves, or split releases can credit only part of the expected settlement.",
    "DELAYED_SETTLEMENT": "KB-04: Normal settlement timing is T+0 to T+3 days after capture; later credits require review.",
    "DUPLICATE_BANK_CREDIT": "KB-05: Webhook retries can cause a settlement to post twice; flag it and do not double-count.",
    "UNMATCHED_BANK_CREDIT": "KB-06: A bank credit with no matching payment is likely an adjustment or stale UTR.",
    "AMOUNT_MISMATCH": "KB-07: Net settlement must equal gross minus fee minus GST, to the paisa.",
}


def _cite(anomaly: str, reason: str) -> str:
    return f"{reason} (per {KB_RULES[anomaly]})"


def _date(value: str) -> date:
    return datetime.strptime(value[:10], "%Y-%m-%d").date()


def _read(name: str) -> list[dict]:
    with (DATA_DIR / name).open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def reconcile() -> list[ReconciliationResult]:
    orders = {row["order_id"]: row for row in _read("merchant_orders.csv")}
    payments, settlements, credits = _read("payments.csv"), _read("settlements.csv"), _read("bank_credits.csv")
    settlements_by_payment, credits_by_settlement = defaultdict(list), defaultdict(list)
    for row in settlements:
        settlements_by_payment[row["payment_id"]].append(row)
    for row in credits:
        credits_by_settlement[row["settlement_id"]].append(row)
    results, referenced = [], set()
    for payment in payments:
        payment_id = payment["payment_id"]
        order = orders.get(payment["order_id"])
        order_ok = order is not None and abs(float(payment["amount"]) - float(order["order_amount"])) <= TOLERANCE
        payment_settlements = settlements_by_payment.get(payment_id, [])
        if not order_ok:
            expected = float(order["order_amount"]) if order else None
            actual = float(payment["amount"])
            results.append(ReconciliationResult(payment_id, None, None, expected, actual, round(actual - expected, 2) if expected is not None else None, "MISMATCHED", "AMOUNT_MISMATCH", 1.0, _cite("AMOUNT_MISMATCH", "Payment amount does not match the merchant order.")))
            continue
        if not payment_settlements:
            results.append(ReconciliationResult(payment_id, None, None, None, None, None, "PENDING", "MISSING_SETTLEMENT", 1.0, _cite("MISSING_SETTLEMENT", "Payment is captured but no settlement exists.")))
            continue
        for settlement in payment_settlements:
            gross, fee, tax = float(settlement["gross_amount"]), float(settlement["gateway_fee"]), float(settlement["tax_on_fee"])
            expected, declared = round(gross - fee - tax, 2), float(settlement["net_amount"])
            settlement_id, matching_credits = settlement["settlement_id"], credits_by_settlement.get(settlement["settlement_id"], [])
            gross_error = abs(gross - float(payment["amount"])) > TOLERANCE
            if not matching_credits:
                results.append(ReconciliationResult(payment_id, settlement_id, None, expected, None, None, "PENDING", "MISSING_SETTLEMENT", 1.0, _cite("MISSING_SETTLEMENT", "Settlement exists but no bank credit was found.")))
                continue
            policy_fee = round(float(payment["amount"]) * 0.02, 2)
            policy_tax = round(policy_fee * 0.18, 2)
            fee_error = abs(expected - declared) > TOLERANCE or abs(fee - policy_fee) > TOLERANCE or abs(tax - policy_tax) > TOLERANCE
            for index, credit in enumerate(matching_credits):
                actual, credit_id = float(credit["credited_amount"]), credit["bank_transaction_id"]
                difference = round(actual - expected, 2)
                referenced.add(credit_id)
                if index > 0:
                    status, anomaly, reason = "DUPLICATE", "DUPLICATE_BANK_CREDIT", _cite("DUPLICATE_BANK_CREDIT", "Multiple bank credits reference the same settlement.")
                elif gross_error:
                    status, anomaly, reason = "MISMATCHED", "AMOUNT_MISMATCH", _cite("AMOUNT_MISMATCH", f"Settlement gross INR {gross:,.2f} differs from captured payment INR {float(payment['amount']):,.2f}.")
                elif fee_error:
                    status, anomaly, reason = "MISMATCHED", "FEE_MISMATCH", _cite("FEE_MISMATCH", f"Declared net INR {declared:,.2f} differs from calculated net INR {expected:,.2f}.")
                elif abs(difference) <= TOLERANCE:
                    lag = (_date(settlement["settlement_date"]) - _date(payment["created_at"])).days
                    if lag > 3:
                        status, anomaly, reason = "MISMATCHED", "DELAYED_SETTLEMENT", _cite("DELAYED_SETTLEMENT", f"Settlement arrived after {lag} days.")
                    else:
                        status, anomaly, reason = "MATCHED", None, "Payment, settlement net calculation, and bank credit agree within tolerance."
                elif actual < expected:
                    status, anomaly, reason = "MISMATCHED", "PARTIAL_SETTLEMENT", _cite("PARTIAL_SETTLEMENT", f"Bank credit is short by INR {abs(difference):,.2f}.")
                else:
                    status, anomaly, reason = "MISMATCHED", "AMOUNT_MISMATCH", _cite("AMOUNT_MISMATCH", f"Bank credit differs from expected net by INR {difference:,.2f}.")
                results.append(ReconciliationResult(payment_id, settlement_id, credit_id, expected, actual, difference, status, anomaly, 1.0, reason))
    for credit in credits:
        if credit["bank_transaction_id"] not in referenced:
            actual = float(credit["credited_amount"])
            results.append(ReconciliationResult(None, credit["settlement_id"], credit["bank_transaction_id"], None, actual, actual, "UNMATCHED", "UNMATCHED_BANK_CREDIT", 1.0, _cite("UNMATCHED_BANK_CREDIT", "Bank credit has no matching payment settlement.")))
    return results


def summarize(results: list[ReconciliationResult]) -> dict:
    counts, anomalies = defaultdict(int), defaultdict(int)
    for result in results:
        counts[result.status] += 1
        if result.anomaly_type:
            anomalies[result.anomaly_type] += 1
    return {"total_results": len(results), "by_status": dict(counts), "by_anomaly": dict(anomalies), "matched_transactions": counts["MATCHED"]}


if __name__ == "__main__":
    import json
    print(json.dumps(summarize(reconcile()), indent=2))
