# AI-Powered Payment Settlement Reconciliation

A synthetic Razorpay-style payment settlement reconciliation system for merchant operations. The data is synthetic and inspired by real-world payment gateway workflows; it does not connect to or claim data from Razorpay proprietary systems.

## Core principle

The deterministic reconciliation engine calculates and verifies every monetary value. The AI layer is limited to anomaly explanations and human-readable summaries. It never invents or calculates financial values.

## Pipeline

`Customer order -> Payment gateway payment -> Expected settlement -> Actual settlement -> Bank credit -> Reconciliation and anomaly detection`

## Quickstart

```bash
pip install -r requirements.txt
python src/generate_data.py
python src/knowledge_base.py
python src/reconcile.py
python src/evaluate.py
python src/evaluate_kb.py
streamlit run src/app.py
```

The generator uses a fixed seed and creates 150 orders and payments with realistic INR amounts, UPI/CARD/NETBANKING/WALLET methods, and exact-match plus anomaly scenarios: fee mismatch, partial settlement, delayed settlement, missing settlement, unmatched bank credit, duplicate bank credit, and amount mismatch.

## Dashboard

The Streamlit app provides Overview, Reconciliation, Anomalies, Data Explorer, and Evaluation views. It runs without an API key. The anomaly cards show deterministic reasons alongside offline explanations.

## Project files

- `src/generate_data.py`: deterministic synthetic order, payment, settlement, bank-credit, and ground-truth generator.
- `src/reconcile.py`: three-stage deterministic reconciliation engine.
- `src/schema.py`: shared result schema and status/anomaly vocabulary.
- `src/evaluate.py`: accuracy, precision, recall, F1, and accuracy by anomaly type.
- `src/knowledge_base.py`: payment settlement policy corpus.
- `src/evaluate_kb.py`: policy coverage check.
- `src/app.py`: Streamlit operations dashboard.
- `src/agent.py`: explanation-only AI layer.

## Deployment

Paths are resolved relative to the project root. Do not commit `.env` or API keys. The application is designed to run on Streamlit Community Cloud with `streamlit run src/app.py`.
