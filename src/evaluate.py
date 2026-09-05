"""Evaluate deterministic reconciliation against ground_truth.csv."""
from __future__ import annotations
import csv
import json
from collections import defaultdict
from pathlib import Path
from reconcile import reconcile

DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def _truth() -> dict[str, dict]:
    with (DATA_DIR / "ground_truth.csv").open(newline="", encoding="utf-8") as handle:
        return {row["payment_id"]: row for row in csv.DictReader(handle)}


def _metrics(results, truth):
    predicted = {row.payment_id: row for row in results if row.payment_id}
    by_bank = {row.bank_transaction_id: row for row in results if row.bank_transaction_id}
    labels = {key: value["expected_status"] for key, value in truth.items()}
    actual = {key: value.status for key, value in predicted.items() if key in labels}
    correct = sum(actual[key] == labels[key] or (labels[key] == "EXACT_MATCH" and actual[key] == "MATCHED") for key in actual)
    accuracy = correct / len(labels) if labels else 0.0
    anomaly_truth = {key: value["anomaly_type"] for key, value in truth.items() if value["anomaly_type"]}
    anomaly_pred = {}
    for key, truth_row in truth.items():
        if not truth_row["anomaly_type"]:
            continue
        row = by_bank.get(truth_row["bank_transaction_id"]) if truth_row["anomaly_type"] == "UNMATCHED_BANK_CREDIT" else predicted.get(key)
        row = row or predicted.get(key)
        if row:
            anomaly_pred[key] = row.anomaly_type
    tp = sum(anomaly_pred[key] == anomaly_truth[key] for key in anomaly_pred)
    precision = tp / len(anomaly_pred) if anomaly_pred else 0.0
    recall = tp / len(anomaly_truth) if anomaly_truth else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    by_type = {}
    for anomaly in sorted(set(anomaly_truth.values())):
        keys = [key for key, value in anomaly_truth.items() if value == anomaly]
        by_type[anomaly] = round(sum(anomaly_pred.get(key) == anomaly for key in keys) / len(keys), 3)
    return {"reconciliation_accuracy": round(accuracy, 3), "exact_match_detection_accuracy": round(sum(predicted.get(k) and predicted[k].status == "MATCHED" for k, v in truth.items() if v["expected_status"] == "EXACT_MATCH") / max(1, sum(v["expected_status"] == "EXACT_MATCH" for v in truth.values())), 3), "anomaly_detection_accuracy": round(tp / max(1, len(anomaly_truth)), 3), "precision": round(precision, 3), "recall": round(recall, 3), "f1": round(f1, 3), "accuracy_by_anomaly_type": by_type}


def main() -> None:
    truth, results = _truth(), reconcile()
    report = {"metrics": _metrics(results, truth), "status_counts": {}}
    for result in results:
        report["status_counts"][result.status] = report["status_counts"].get(result.status, 0) + 1
    (DATA_DIR / "metrics.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
