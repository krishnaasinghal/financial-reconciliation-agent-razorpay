"""Synthetic payment settlement policy corpus, not proprietary Razorpay documentation."""
from __future__ import annotations
import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
KB_PATH = DATA_DIR / "knowledge_base.jsonl"
POLICIES = [
    ("captured_pending", "Captured payment with pending settlement", "A captured payment may remain pending until the gateway creates a settlement; do not treat absence of a settlement as a zero-value settlement."),
    ("net_calculation", "Expected settlement calculation", "Expected net settlement is gross amount minus gateway fee minus tax on gateway fee. This arithmetic is deterministic code."),
    ("fees", "Gateway fees and tax", "Gateway fees are deducted from gross payment value and tax on the fee is deducted separately; fee policy differences require review."),
    ("partial", "Partial settlements", "A bank credit below expected net is a partial settlement and should remain open for the unreconciled balance."),
    ("delayed", "Delayed settlements", "A settlement outside the normal zero-to-three-day window is delayed and should be flagged even when its amount matches."),
    ("duplicate", "Duplicate bank credits", "Two bank credits referencing one settlement are duplicate credits and require operational review."),
    ("unmatched", "Unmatched bank credits", "A bank credit without a corresponding payment settlement is unmatched and must not be assigned to a payment by guesswork."),
    ("holds", "Settlement holds and reserves", "Reserves, holds, refunds, and adjustments can explain a short credit, but the deterministic difference remains visible."),
    ("amount", "Amount mismatches", "A settlement gross amount or bank credit that differs from the captured payment or expected net is an amount mismatch."),
]


def build() -> list[dict]:
    return [{"doc_id": f"kb-{index:04d}", "category": "Settlement Operations", "section": "Reconciliation", "topic": key, "title": title, "text": text} for index, (key, title, text) in enumerate(POLICIES, 1)]


def write() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with KB_PATH.open("w", encoding="utf-8") as handle:
        for row in build():
            handle.write(json.dumps(row) + "\n")


def load() -> list[dict]:
    if not KB_PATH.exists():
        write()
    with KB_PATH.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


if __name__ == "__main__":
    write()
    print(f"Wrote {len(POLICIES)} payment settlement policies to {KB_PATH}")
