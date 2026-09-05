"""Evaluate coverage of the payment-settlement policy knowledge base."""
from __future__ import annotations
import json
from pathlib import Path
from knowledge_base import load

DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def main() -> None:
    kb = load()
    queries = ["payment captured settlement pending", "gateway fee tax calculation", "partial settlement", "duplicate bank credit", "unmatched bank credit", "settlement reserve delayed"]
    cited = sum(any(any(word in (doc["title"] + " " + doc["text"]).lower() for word in query.split()) for doc in kb) for query in queries)
    report = {"knowledge_base_documents": len(kb), "queries": len(queries), "citation_coverage": round(cited / len(queries), 3)}
    (DATA_DIR / "kb_metrics.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
