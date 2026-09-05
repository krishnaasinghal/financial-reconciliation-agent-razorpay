"""Shared typed records for synthetic payment settlement reconciliation."""
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class ReconciliationResult:
    payment_id: str | None
    settlement_id: str | None
    bank_transaction_id: str | None
    expected_amount: float | None
    actual_amount: float | None
    difference: float | None
    status: str
    anomaly_type: str | None
    reconciliation_confidence: float
    reason: str


STATUSES = ["MATCHED", "PENDING", "MISMATCHED", "UNMATCHED", "DUPLICATE"]
ANOMALIES = ["FEE_MISMATCH", "PARTIAL_SETTLEMENT", "DELAYED_SETTLEMENT", "MISSING_SETTLEMENT", "UNMATCHED_BANK_CREDIT", "DUPLICATE_BANK_CREDIT", "AMOUNT_MISMATCH"]

# Compatibility exports for the retained retrieval modules.
REVENUE = "Settlement Revenue"
COGS = "Gateway Costs"
OPEX = "Operations"
OTHER = "Other"
CATEGORIES = {}
CATEGORY_NAMES = ["Settlement Operations"]
UNKNOWN = "Needs Review"


def income_statement_section(category: str) -> str:
    return "Reconciliation"
