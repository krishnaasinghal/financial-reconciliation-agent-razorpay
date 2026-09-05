"""Create real Razorpay test-mode orders for the buildathon demo.

Setup:
    pip install -r requirements.txt
    Get test keys from Razorpay Dashboard -> Settings -> API Keys.

PowerShell:
    $env:RAZORPAY_KEY_ID="rzp_test_xxx"
    $env:RAZORPAY_KEY_SECRET="yyy"
    python fetch_real_razorpay_orders.py

This script creates test-mode orders only. It does not create payments or
access production Razorpay data.
"""

from __future__ import annotations

import csv
import os
import random
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

import razorpay

KEY_ID = os.environ.get("RAZORPAY_KEY_ID")
KEY_SECRET = os.environ.get("RAZORPAY_KEY_SECRET")
NUM_ORDERS = 5
OUTPUT_PATH = Path(__file__).resolve().parent / "real_razorpay_orders.csv"


def to_paise(amount_rupees: Decimal) -> int:
    return int((amount_rupees * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def main() -> None:
    if not KEY_ID or not KEY_SECRET:
        raise SystemExit(
            "Set RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET first.\n"
            "Get test keys from Razorpay Dashboard -> Settings -> API Keys."
        )
    if not KEY_ID.startswith("rzp_test_"):
        raise SystemExit("Refusing to run: RAZORPAY_KEY_ID must be a Razorpay test-mode key (rzp_test_...).")

    client = razorpay.Client(auth=(KEY_ID, KEY_SECRET))
    rng = random.Random(42)
    rows = []
    for index in range(NUM_ORDERS):
        amount_rupees = Decimal(str(round(rng.uniform(500, 15000), 2)))
        order = client.order.create({
            "amount": to_paise(amount_rupees),
            "currency": "INR",
            "receipt": f"buildathon_demo_{index + 1}",
            "notes": {"source": "razorpay-buildathon-reconciliation-demo"},
        })
        print(f"Created Razorpay test order: {order['id']} amount={amount_rupees} INR status={order['status']}")
        rows.append({
            "order_id": order["id"],
            "amount": amount_rupees,
            "currency": "INR",
            "created_at": order["created_at"],
            "status": order["status"],
            "receipt": order["receipt"],
        })

    with OUTPUT_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["order_id", "amount", "currency", "created_at", "status", "receipt"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nSaved {len(rows)} Razorpay test order IDs to {OUTPUT_PATH.name}")


if __name__ == "__main__":
    main()
