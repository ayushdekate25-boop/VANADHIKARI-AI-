# VANADHIKAR AI

AI-Powered Forest Rights Act Monitoring & Decision Support System.
https://vanadhikar-gov.onrender.com/

VANADHIKAR AI is a demo-ready decision-support platform for reviewing synthetic FRA monitoring data. It surfaces potential anomalies and unusual patterns for human administrative verification. It does not determine fraud, corruption, illegality, or guilt.

## Run

From `D:\origin`:

```powershell
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

Open `http://localhost:8000`. The frontend is served by FastAPI, so no separate Node installation is required for the working MVP. For local-only development, use `--host 127.0.0.1` instead.

Fallback server:

```powershell
python backend/server.py
```

## Features

- Live KPI dashboard backed by `data/fra_monitoring.db`
- State progress and district risk ranking
- Leaflet map with claim and district points
- Claim, village, district, state, status, and severity filters through the API
- Anomaly evidence and claim detail endpoints
- Deterministic AI explanation and natural-language database query fallback
- Optional ChatGPT-style general assistant through a server-side OpenAI-compatible LLM
- Retrieval-augmented generation (RAG) that retrieves relevant SQLite evidence before AI answers
- Synthetic-data disclaimer and verification-first language

## API

- `GET /api/dashboard`
- `GET /api/states`
- `GET /api/districts/{state}`
- `GET /api/district-risk`
- `GET /api/claims`
- `GET /api/claims/{claim_id}`
- `GET /api/anomalies`
- `GET /api/anomalies/{claim_id}`
- `GET /api/map/claims`
- `POST /api/ai/explain` with `{ "claim_id": "FRA-10018" }`
- `POST /api/ai/query` with `{ "question": "Which districts need attention first?" }`

The AI assistant uses RAG: a question is matched against the live claims, land records, anomalies, states, districts, and priority cases in SQLite. Only the retrieved evidence is sent to Gemini for explanation. The database remains the source of truth; the model does not train on or permanently store claim data.

### Enable general AI answers

Copy `.env.example` to `.env` and set `LLM_API_KEY`. For Gemini, use `LLM_PROVIDER=gemini` and `GEMINI_MODEL=gemini-2.0-flash`. For OpenAI-compatible providers, use `LLM_PROVIDER=openai`, `LLM_BASE_URL`, and `LLM_MODEL`. The key is used only by the backend and is never sent to the browser. Without it, FRA questions still work through deterministic database logic and unsupported questions receive a transparent fallback.

## Data workflow

```powershell
python scripts/generate_data.py
python scripts/detect_anomalies.py
python scripts/database.py
python scripts/test_database.py
python scripts/district_risk.py
```

Do not run the generation/database commands unless you intend to replace or append the existing demo data. The current database is already populated and tested.

The original district map upload was corrupt binary data. `data/geo/india_districts.geojson` is currently a valid point GeoJSON generated from the district coordinates in the database, and `scripts/repair_geojson.py` can recreate it if needed.

## Data disclaimer

Claim-level records shown in this demonstration are synthetic/mock data created for the hackathon. FRA implementation context and official reference material are based on Government of India Ministry of Tribal Affairs resources. Potential signals are not findings of fraud or illegality.
