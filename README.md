# Settlement Control Room - AI Finance Controller (Razorpay AI Buildathon, Track 4)

Live demo: https://financial-reconciliation-agent-razorpay-ivhezws8zgfhqjrmopvn6x.streamlit.app
GitHub: https://github.com/krishnaasinghal/financial-reconciliation-agent-razorpay

## What this is

Settlement Control Room is an AI-assisted payment settlement reconciliation system for merchants. It traces a payment from customer order through gateway settlement to bank credit, calculates expected net settlement, detects exceptions, and gives finance teams an auditable review queue using synthetic Razorpay-style data.

## Architecture principle

**The LLM proposes, deterministic code disposes.** All money math, matching, tolerance checks, and anomaly labels are deterministic Python. AI only explains anomalies and cites payment-settlement policy rules; it never invents or calculates financial values.

## Actual evaluation results

Against the generated ground truth, the current Evaluation tab reports:

- Reconciliation accuracy: **70.7%**
- Anomaly precision: **100%**
- Anomaly recall: **100%**
- Anomaly F1: **100%**

The lower overall reconciliation accuracy reflects the stricter status-level comparison across normal, pending, duplicate, and unmatched records; anomaly detection is evaluated separately and is perfect on the generated batch.

## Razorpay test-mode touchpoint

The optional `fetch_real_razorpay_orders.py` integration creates real Razorpay test-mode orders through the live API when configured with test credentials. The current reconciliation batch remains synthetic so it is reproducible and safe to evaluate; no production credentials or proprietary Razorpay data are committed.

## Local run

```bash
pip install -r requirements.txt
python src/generate_data.py
python src/knowledge_base.py
python src/evaluate.py
streamlit run src/app.py
```

## Honest limitations

This is a synthetic-batch prototype validated against held-out ground truth, with a real Razorpay test-mode API touchpoint rather than live financial data. Live settlement webhook ingestion, production authentication, and operational settlement feeds are the natural next steps.

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
