# Architecture

```text
User
  |
  v
Streamlit UI
  |
  +--> CSV/Excel seed/upload data
  |
  v
Data processing
  |
  v
Local SQLite (demo) / PostgreSQL or Supabase (future)
  |
  v
Deterministic validation engine
  |
  v
Discrepancy store
  |
  +--> Dashboard
  |
  +--> Controlled natural-language query layer
          |
          +--> Optional Gemini/OpenAI provider
```

## Why deterministic validation?

Leave conflicts, billing comparisons and arithmetic conditions have clear rules and should not depend on an LLM.

## Why an AI layer?

An LLM can add conversational access to structured operational data. In the enhanced version it should use read-only tools to retrieve actual records and then explain them.
