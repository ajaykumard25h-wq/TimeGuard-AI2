# TimeGuard AI

**AI-Powered Timesheet Compliance & Workforce Analytics**

A portfolio-ready Streamlit MVP for detecting timesheet compliance issues, reviewing workload patterns, and querying structured workforce data.

## What changed in the enhanced version

- Polished dashboard UI with a product-style header, KPI cards, charts and review queue.
- Project and issue-status filters now affect the KPI cards, charts, employee activity table and discrepancy review.
- Broader local query understanding without an API key.
- Optional Gemini AI mode for genuinely free-form natural-language questions.
- Deterministic validation remains the source of truth for compliance findings.

## Run locally

```bash
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

## Query behaviour

### Smart local mode
Works without an API key and recognizes a broad set of phrasings around:
- leave conflicts
- billing/billable hours
- duplicate entries
- excess hours/overtime
- open/unresolved issues
- employee workload
- project workload
- discrepancy counts
- named employees and projects

It is still a rule-based intent layer, so it does **not** understand every possible English question.

### Gemini AI mode
Set `GEMINI_API_KEY` as an environment variable or Streamlit secret to enable broader natural-language questions. The app sends the synthetic dataset as context to Gemini and asks it to answer using only that data. Google’s current Python SDK is `google-genai`. See the official Gemini API documentation for API-key setup and SDK usage.

Never commit a real API key to GitHub.

## Architecture

```text
CSV / Excel
   ↓
Pandas processing
   ↓
SQLite (MVP) / PostgreSQL (production)
   ↓
Deterministic compliance engine
   ↓
Discrepancy store
   ↓
Dashboard + AI query layer
   ↓
Human review / correction / revalidation
```

## GitHub safety

Do not commit:
- `timeguard.db`
- `.env`
- API keys
- real employee/client data

The included CSVs are synthetic demo data.
