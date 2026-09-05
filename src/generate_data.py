"""Generate deterministic synthetic Razorpay-style settlement data."""
from __future__ import annotations
import csv
import random
from datetime import date, timedelta
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
SEED = 42
NUM_ORDERS = 150
MERCHANTS = ["mrc_demo_001", "mrc_demo_002", "mrc_demo_003"]
PAYMENT_METHODS = ["UPI", "CARD", "NETBANKING", "WALLET"]
SCENARIOS = ["EXACT_MATCH", "FEE_MISMATCH", "PARTIAL_SETTLEMENT", "DELAYED_SETTLEMENT", "MISSING_SETTLEMENT", "UNMATCHED_BANK_CREDIT", "DUPLICATE_BANK_CREDIT", "AMOUNT_MISMATCH"]


def _money(value: float) -> float:
    return round(value, 2)


def _write(name: str, rows: list[dict], fields: list[str]) -> None:
    with (DATA_DIR / name).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def build() -> dict[str, list[dict]]:
    rng = random.Random(SEED)
    start = date(2026, 7, 1)
    orders, payments, settlements, credits, truth = [], [], [], [], []
    scenario_count = {name: 0 for name in SCENARIOS}
    scenarios = ["EXACT_MATCH"] * 108 + [name for name in SCENARIOS[1:] for _ in range(6)]
    rng.shuffle(scenarios)
    for index in range(NUM_ORDERS):
        order_id, payment_id = f"ord_{index + 1000:06d}", f"pay_{index + 1000:06d}"
        merchant_id = rng.choice(MERCHANTS)
        order_date = start + timedelta(days=rng.randint(0, 45))
        amount, scenario = _money(rng.uniform(249.50, 24999.75)), scenarios[index]
        scenario_count[scenario] += 1
        fee, tax = _money(amount * 0.0200), _money(amount * 0.0200 * 0.18)
        expected_net = _money(amount - fee - tax)
        orders.append({"order_id": order_id, "merchant_id": merchant_id, "customer_id": f"cus_{rng.randint(10000, 99999)}", "order_amount": amount, "currency": "INR", "order_date": order_date.isoformat(), "order_status": "PAID"})
        payments.append({"payment_id": payment_id, "order_id": order_id, "merchant_id": merchant_id, "amount": amount, "payment_method": rng.choice(PAYMENT_METHODS), "payment_status": "CAPTURED", "created_at": f"{order_date.isoformat()}T{rng.randint(8, 20):02d}:15:00"})
        settlement_id = bank_id = ""
        if scenario != "MISSING_SETTLEMENT":
            settlement_id = f"stl_{index + 1000:06d}"
            settlement_date = order_date + timedelta(days=7 if scenario == "DELAYED_SETTLEMENT" else rng.randint(0, 3))
            settlement_gross = _money(amount - rng.choice([125.50, 249.75, 501.25])) if scenario == "AMOUNT_MISMATCH" else amount
            settlement_fee, settlement_tax, settlement_net = fee, tax, _money(settlement_gross - fee - tax)
            if scenario == "FEE_MISMATCH":
                settlement_fee, settlement_tax = _money(fee * 1.35), _money(fee * 1.35 * 0.18)
                settlement_net = _money(amount - settlement_fee - settlement_tax)
            settlements.append({"settlement_id": settlement_id, "payment_id": payment_id, "merchant_id": merchant_id, "gross_amount": settlement_gross, "gateway_fee": settlement_fee, "tax_on_fee": settlement_tax, "net_amount": settlement_net, "settlement_date": settlement_date.isoformat(), "settlement_status": "PROCESSED"})
            if scenario != "UNMATCHED_BANK_CREDIT":
                bank_id = f"bnk_{index + 1000:06d}"
                credited = _money(settlement_net * 0.60) if scenario == "PARTIAL_SETTLEMENT" else settlement_net
                credits.append({"bank_transaction_id": bank_id, "settlement_id": settlement_id, "merchant_id": merchant_id, "credited_amount": credited, "credit_date": (settlement_date + timedelta(days=rng.randint(0, 2))).isoformat(), "bank_reference": f"UTR{rng.randint(10**11, 10**12 - 1)}"})
                if scenario == "DUPLICATE_BANK_CREDIT":
                    credits.append({"bank_transaction_id": f"bnk_dup_{index + 1000:06d}", "settlement_id": settlement_id, "merchant_id": merchant_id, "credited_amount": settlement_net, "credit_date": (settlement_date + timedelta(days=1)).isoformat(), "bank_reference": f"UTR{rng.randint(10**11, 10**12 - 1)}"})
        if scenario == "UNMATCHED_BANK_CREDIT":
            bank_id = f"bnk_orphan_{index + 1000:06d}"
            credits.append({"bank_transaction_id": bank_id, "settlement_id": f"stl_unknown_{index:04d}", "merchant_id": merchant_id, "credited_amount": _money(rng.uniform(500, 18000)), "credit_date": (order_date + timedelta(days=2)).isoformat(), "bank_reference": f"UTR{rng.randint(10**11, 10**12 - 1)}"})
        truth.append({"payment_id": payment_id, "settlement_id": settlement_id, "bank_transaction_id": bank_id, "expected_status": scenario, "anomaly_type": "" if scenario == "EXACT_MATCH" else scenario})
    return {"orders": orders, "payments": payments, "settlements": settlements, "credits": credits, "truth": truth, "scenario_count": scenario_count}


def write_all(world: dict[str, list[dict]]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    _write("merchant_orders.csv", world["orders"], ["order_id", "merchant_id", "customer_id", "order_amount", "currency", "order_date", "order_status"])
    _write("payments.csv", world["payments"], ["payment_id", "order_id", "merchant_id", "amount", "payment_method", "payment_status", "created_at"])
    _write("settlements.csv", world["settlements"], ["settlement_id", "payment_id", "merchant_id", "gross_amount", "gateway_fee", "tax_on_fee", "net_amount", "settlement_date", "settlement_status"])
    _write("bank_credits.csv", world["credits"], ["bank_transaction_id", "settlement_id", "merchant_id", "credited_amount", "credit_date", "bank_reference"])
    _write("ground_truth.csv", world["truth"], ["payment_id", "settlement_id", "bank_transaction_id", "expected_status", "anomaly_type"])


def main() -> None:
    world = build()
    write_all(world)
    print(f"Generated {len(world['orders'])} orders, {len(world['payments'])} payments, {len(world['settlements'])} settlements, {len(world['credits'])} bank credits.")
    print("Scenario distribution:", world["scenario_count"])


if __name__ == "__main__":
    main()
