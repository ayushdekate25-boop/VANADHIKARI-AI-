import json
import os
import sqlite3
import urllib.error
import urllib.request
from urllib.parse import quote
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "fra_monitoring.db"
FRONTEND_DIR = BASE_DIR / "frontend"


def load_local_env():
    env_file = BASE_DIR / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_local_env()

app = FastAPI(title="VANADHIKAR AI", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:8000"],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


class ClaimExplanationRequest(BaseModel):
    claim_id: str


class QuestionRequest(BaseModel):
    question: str
    history: list[dict[str, str]] = Field(default_factory=list)


def llm_settings():
    provider = os.getenv("LLM_PROVIDER", "openai").lower()
    return {
        "provider": provider,
        "api_key": os.getenv("LLM_API_KEY", ""),
        "base_url": os.getenv("LLM_BASE_URL", "https://api.openai.com/v1/chat/completions"),
        "model": os.getenv("LLM_MODEL", "gpt-4o-mini") if provider != "gemini" else os.getenv("GEMINI_MODEL", "gemini-2.0-flash"),
    }


def load_data_context(db):
    summary = db.execute("""
        SELECT COUNT(*) AS total, SUM(status = 'PENDING') AS pending,
               SUM(status = 'APPROVED') AS approved, SUM(status = 'REJECTED') AS rejected
        FROM claims
    """).fetchone()
    top_states = db.execute("""
        SELECT state, COUNT(*) AS pending FROM claims WHERE status = 'PENDING'
        GROUP BY state ORDER BY pending DESC LIMIT 5
    """).fetchall()
    return {
        "claims": dict(summary),
        "pending_by_state": [dict(row) for row in top_states],
        "top_districts": district_risk_rows(db)[:5],
        "priority_cases": priority_case_rows(db, 5),
    }

def retrieve_context(db, question: str):
    """Retrieve a small, relevant evidence set from SQLite for grounded AI answers."""
    context = load_data_context(db)
    normalized = question.strip().lower()
    terms = [term for term in normalized.replace("?", " ").replace(",", " ").split() if len(term) >= 4]
    rows = []
    if terms:
        clauses = []
        params = []
        for term in terms[:8]:
            pattern = f"%{term}%"
            clauses.append("(c.claim_id LIKE ? OR c.state LIKE ? OR c.district LIKE ? OR c.village LIKE ? OR c.status LIKE ? OR a.anomaly_type LIKE ?)")
            params.extend([pattern] * 6)
        rows = db.execute(f"""
            SELECT c.claim_id, c.state, c.district, c.village, c.status,
                   c.claim_type, c.area_claimed, c.submission_date, c.last_updated,
                   l.recorded_area, l.survey_reference, a.anomaly_type, a.severity,
                   a.evidence, a.description
            FROM claims c
            LEFT JOIN land_records l ON l.claim_id = c.claim_id
            LEFT JOIN anomalies a ON a.claim_id = c.claim_id
            WHERE {' OR '.join(clauses)}
            ORDER BY CASE a.severity WHEN 'HIGH' THEN 1 WHEN 'MEDIUM' THEN 2 WHEN 'LOW' THEN 3 ELSE 4 END,
                     c.claim_id
            LIMIT 20
        """, params).fetchall()
    context["retrieved_records"] = records(rows)
    context["retrieval_note"] = "Only these records were retrieved from SQLite for this question. Do not invent facts outside this evidence."
    return context


def call_llm(question: str, history: list[dict[str, str]], context: dict[str, Any]):
    settings = llm_settings()
    if not settings["api_key"]:
        return None
    system_prompt = "You are VANADHIKAR AI, a helpful ChatGPT-style assistant. Answer general questions clearly and honestly. For FRA questions, use only the retrieved database evidence and say when information is unavailable. Potential anomalies are signals for administrative verification, never proof of fraud, corruption, illegality, or guilt. Keep answers concise unless the user asks for detail. When discussing a claim, include the evidence and a suggested administrative verification step.\n\nRetrieved FRA database context:\n" + json.dumps(context, default=str)
    if settings["provider"] == "gemini":
        contents = [{"role": "user" if item["role"] == "user" else "model", "parts": [{"text": item["content"]}]} for item in history[-10:] if item.get("role") in ("user", "assistant")]
        contents.append({"role": "user", "parts": [{"text": question}]})
        payload = json.dumps({"systemInstruction": {"parts": [{"text": system_prompt}]}, "contents": contents, "generationConfig": {"temperature": 0.2}}).encode("utf-8")
        base_url = os.getenv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta").rstrip("/")
        endpoint = f"{base_url}/models/{quote(settings['model'])}:generateContent?key={quote(settings['api_key'])}"
        request = urllib.request.Request(endpoint, data=payload, method="POST", headers={"Content-Type": "application/json"})
    else:
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend({"role": item["role"], "content": item["content"]} for item in history[-10:] if item.get("role") in ("user", "assistant"))
        messages.append({"role": "user", "content": question})
        payload = json.dumps({"model": settings["model"], "messages": messages, "temperature": 0.2}).encode("utf-8")
        request = urllib.request.Request(settings["base_url"], data=payload, method="POST", headers={"Authorization": f"Bearer {settings['api_key']}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            result = json.loads(response.read().decode("utf-8"))
        if settings["provider"] == "gemini":
            return result["candidates"][0]["content"]["parts"][0]["text"].strip()
        return result["choices"][0]["message"]["content"].strip()
    except (urllib.error.URLError, urllib.error.HTTPError, KeyError, IndexError, json.JSONDecodeError):
        return None


def connection():
    if not DB_PATH.exists():
        raise HTTPException(status_code=503, detail="Monitoring database is unavailable")
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    return db


def records(rows):
    return [dict(row) for row in rows]


def risk_score(row):
    total = row["total_claims"] or 0
    if not total:
        return 0.0, "LOW"
    density = ((row["high_anomalies"] or 0) * 3 + (row["medium_anomalies"] or 0) * 2 + (row["low_anomalies"] or 0)) / total
    score = round(min(70, density * 700) + min(30, (row["pending_claims"] or 0) / total * 100), 2)
    return score, "HIGH" if score >= 60 else "MEDIUM" if score >= 30 else "LOW"


def district_risk_rows(db, state: Optional[str] = None):
    where = "WHERE s.state_name = ?" if state else ""
    params = (state,) if state else ()
    rows = db.execute(
        f"""
        SELECT d.district_id, d.district_name AS district, s.state_name AS state,
               d.latitude, d.longitude, COUNT(DISTINCT c.claim_id) AS total_claims,
               SUM(c.status = 'PENDING') AS pending_claims,
               SUM(c.status = 'APPROVED') AS approved_claims,
               SUM(c.status = 'REJECTED') AS rejected_claims,
               SUM(c.status = 'UNDER_REVIEW') AS under_review_claims,
               COUNT(DISTINCT CASE WHEN a.severity = 'HIGH' THEN a.anomaly_id END) AS high_anomalies,
               COUNT(DISTINCT CASE WHEN a.severity = 'MEDIUM' THEN a.anomaly_id END) AS medium_anomalies,
               COUNT(DISTINCT CASE WHEN a.severity = 'LOW' THEN a.anomaly_id END) AS low_anomalies
        FROM districts d JOIN states s ON s.state_id = d.state_id
        LEFT JOIN claims c ON c.district = d.district_name AND c.state = s.state_name
        LEFT JOIN anomalies a ON a.claim_id = c.claim_id
        {where}
        GROUP BY d.district_id
        """,
        params,
    ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["risk_score"], item["risk_level"] = risk_score(row)
        item["anomalies"] = sum(item[key] or 0 for key in ("high_anomalies", "medium_anomalies", "low_anomalies"))
        item["anomaly_count"] = item["anomalies"]
        item["district_name"] = item["district"]
        item["state_name"] = item["state"]
        result.append(item)
    return sorted(result, key=lambda item: (-item["risk_score"], -item["anomalies"], item["district"]))


def claim_record(db, claim_id: str):
    claim = db.execute("SELECT * FROM claims WHERE claim_id = ?", (claim_id,)).fetchone()
    if not claim:
        raise HTTPException(status_code=404, detail=f"Claim {claim_id} was not found")
    land = db.execute("SELECT * FROM land_records WHERE claim_id = ?", (claim_id,)).fetchone()
    anomalies = db.execute("SELECT * FROM anomalies WHERE claim_id = ? ORDER BY anomaly_id", (claim_id,)).fetchall()
    return {"claim": dict(claim), "land_record": dict(land) if land else None, "anomalies": records(anomalies)}


def priority_case_rows(db, limit: int = 10):
    today = date.today()
    rows = db.execute("""
        SELECT c.claim_id, c.state, c.district, c.status, c.claim_type,
               c.area_claimed, c.submission_date, c.last_updated,
               l.recorded_area, l.survey_reference,
               MAX(CASE a.severity WHEN 'HIGH' THEN 3 WHEN 'MEDIUM' THEN 2 WHEN 'LOW' THEN 1 ELSE 0 END) AS severity_weight,
            CASE WHEN MAX(CASE WHEN a.severity = 'HIGH' THEN 1 ELSE 0 END) = 1 THEN 'HIGH'
                WHEN MAX(CASE WHEN a.severity = 'MEDIUM' THEN 1 ELSE 0 END) = 1 THEN 'MEDIUM'
                WHEN MAX(CASE WHEN a.severity = 'LOW' THEN 1 ELSE 0 END) = 1 THEN 'LOW'
                ELSE NULL END AS severity,
            GROUP_CONCAT(DISTINCT a.anomaly_type) AS anomaly_types,
               GROUP_CONCAT(DISTINCT a.evidence) AS evidence,
               d_risk.risk_score, d_risk.risk_level
        FROM claims c
        LEFT JOIN land_records l ON l.claim_id = c.claim_id
        LEFT JOIN anomalies a ON a.claim_id = c.claim_id
        LEFT JOIN (
            SELECT d.district_name, s.state_name,
                   COUNT(DISTINCT c2.claim_id) AS total_claims,
                   SUM(c2.status = 'PENDING') AS pending_claims,
                   COUNT(DISTINCT CASE WHEN a2.severity = 'HIGH' THEN a2.anomaly_id END) AS high_anomalies,
                   COUNT(DISTINCT CASE WHEN a2.severity = 'MEDIUM' THEN a2.anomaly_id END) AS medium_anomalies,
                   COUNT(DISTINCT CASE WHEN a2.severity = 'LOW' THEN a2.anomaly_id END) AS low_anomalies,
                   0.0 AS risk_score, 'LOW' AS risk_level
            FROM districts d JOIN states s ON s.state_id = d.state_id
            LEFT JOIN claims c2 ON c2.district = d.district_name AND c2.state = s.state_name
            LEFT JOIN anomalies a2 ON a2.claim_id = c2.claim_id
            GROUP BY d.district_id
        ) d_risk ON d_risk.district_name = c.district AND d_risk.state_name = c.state
        GROUP BY c.claim_id
    """).fetchall()
    district_rows = {f"{row['state']}|{row['district']}": row for row in district_risk_rows(db)}
    cases = []
    for row in rows:
        item = dict(row)
        district = district_rows.get(f"{item['state']}|{item['district']}", {})
        submitted = None
        if item["submission_date"]:
            try:
                submitted = datetime.strptime(item["submission_date"], "%Y-%m-%d").date()
            except ValueError:
                pass
        pending_days = max(0, (today - submitted).days) if submitted and item["status"] == "PENDING" else 0
        mismatch_percent = 0
        if item["area_claimed"] and item["recorded_area"] is not None:
            mismatch_percent = round(abs(item["area_claimed"] - item["recorded_area"]) / item["area_claimed"] * 100, 1)
        stale_days = 0
        if item["last_updated"]:
            try:
                stale_days = max(0, (today - datetime.strptime(item["last_updated"], "%Y-%m-%d").date()).days)
            except ValueError:
                pass
        has_signal = bool(item["anomaly_types"])
        if not has_signal and pending_days <= 365 and mismatch_percent < 30 and stale_days <= 365:
            continue
        score = min(40, pending_days / 45) + (item["severity_weight"] or 0) * 10 + min(20, mismatch_percent / 2) + min(10, stale_days / 90) + (district.get("risk_score", 0) or 0) * .2
        reasons = []
        if pending_days > 365: reasons.append(f"Pending for {pending_days:,} days")
        if mismatch_percent >= 30: reasons.append(f"Land area differs by {mismatch_percent}%")
        if item["severity"]: reasons.append(f"{item['severity']} severity signal")
        if stale_days > 365: reasons.append(f"No recent update for {stale_days:,} days")
        action = "Review processing history and confirm the current administrative stage."
        if mismatch_percent >= 30: action = "Verify the claimed area against the latest land record and survey documentation."
        elif item["severity"] == "MEDIUM": action = "Check the case file for missing decision-stage information and update the record."
        cases.append({
            "claim_id": item["claim_id"], "state": item["state"], "district": item["district"], "status": item["status"],
            "severity": item["severity"] or "REVIEW", "priority_score": round(min(100, score), 1),
            "problem": reasons[0] if reasons else "Unusual record pattern", "reasons": reasons,
            "evidence": item["evidence"].replace(",", " | ") if item["evidence"] else None, "pending_days": pending_days, "mismatch_percent": mismatch_percent,
            "area_claimed": item["area_claimed"], "recorded_area": item["recorded_area"], "suggested_action": action,
        })
    return sorted(cases, key=lambda item: (-item["priority_score"], item["claim_id"]))[:limit]


@app.get("/api/dashboard")
def dashboard():
    with connection() as db:
        summary = db.execute("""
            SELECT COUNT(*) AS total_claims,
                   SUM(status = 'APPROVED') AS approved,
                   SUM(status = 'PENDING') AS pending,
                   SUM(status = 'REJECTED') AS rejected,
                   SUM(status = 'UNDER_REVIEW') AS under_review,
                   (SELECT COUNT(*) FROM anomalies) AS anomalies,
                   SUM(status IN ('APPROVED', 'REJECTED') AND decision_date IS NULL) AS missing_decisions
            FROM claims
        """).fetchone()
        risk = district_risk_rows(db)
        state_rows = records(db.execute("""
            SELECT c.state, COUNT(*) AS total_claims,
                   SUM(status = 'APPROVED') AS approved_claims,
                   SUM(status = 'PENDING') AS pending_claims,
                   SUM(status = 'UNDER_REVIEW') AS review_claims,
                   COUNT(DISTINCT CASE WHEN a.anomaly_id IS NOT NULL THEN c.claim_id END) AS flagged_claims
            FROM claims c LEFT JOIN anomalies a ON a.claim_id = c.claim_id
            GROUP BY c.state ORDER BY flagged_claims DESC, total_claims DESC
        """))
        severity_rows = records(db.execute("SELECT severity, COUNT(*) AS count FROM anomalies GROUP BY severity"))
        recent_rows = records(db.execute("""
            SELECT a.claim_id, a.state, a.district, a.anomaly_type, a.severity,
                   a.description, a.evidence, c.status, c.area_claimed,
                   l.recorded_area, c.submission_date
            FROM anomalies a JOIN claims c ON c.claim_id = a.claim_id
            LEFT JOIN land_records l ON l.claim_id = c.claim_id
            ORDER BY CASE a.severity WHEN 'HIGH' THEN 1 WHEN 'MEDIUM' THEN 2 ELSE 3 END,
                     a.anomaly_id DESC LIMIT 80
        """))
        return {
            **dict(summary),
            "high_risk_districts": sum(item["risk_level"] == "HIGH" for item in risk),
            "top_districts": risk[:8],
            "summary": {"total_claims": summary["total_claims"], "approved_claims": summary["approved"], "pending_claims": summary["pending"], "review_claims": summary["under_review"], "missing_decisions": summary["missing_decisions"]},
            "anomalies": severity_rows,
            "states": state_rows,
            "districts": risk,
            "recent_anomalies": recent_rows,
        }


@app.get("/api/states")
def states():
    with connection() as db:
        return records(db.execute("""
            SELECT state, COUNT(*) AS total_claims,
                   SUM(status = 'APPROVED') AS approved,
                   SUM(status = 'PENDING') AS pending,
                   SUM(status = 'REJECTED') AS rejected,
                   SUM(status = 'UNDER_REVIEW') AS under_review,
                   ROUND(100.0 * SUM(status = 'APPROVED') / COUNT(*), 1) AS approval_percent
            FROM claims GROUP BY state ORDER BY state
        """))


@app.get("/api/search")
def search(q: str = Query("", min_length=1)):
    term = f"%{q}%"
    with connection() as db:
        rows = db.execute("""
            SELECT c.claim_id, c.state, c.district, c.village, c.status,
                   c.claim_type, a.anomaly_type, a.severity
            FROM claims c LEFT JOIN anomalies a ON a.claim_id = c.claim_id
            WHERE c.claim_id LIKE ? OR c.state LIKE ? OR c.district LIKE ?
               OR c.village LIKE ? OR c.status LIKE ?
            ORDER BY c.claim_id LIMIT 50
        """, (term, term, term, term, term)).fetchall()
    return {"results": records(rows)}


@app.get("/api/districts/{state}")
def districts(state: str):
    with connection() as db:
        return district_risk_rows(db, state)


@app.get("/api/district-risk")
def district_risk():
    with connection() as db:
        return district_risk_rows(db)


@app.get("/api/priority-cases")
def priority_cases(limit: int = Query(10, ge=1, le=50)):
    with connection() as db:
        return {"cases": priority_case_rows(db, limit)}


@app.get("/api/claims")
def claims(state: Optional[str] = None, district: Optional[str] = None, status: Optional[str] = None, claim_type: Optional[str] = None, severity: Optional[str] = None, search: Optional[str] = None, limit: int = Query(100, ge=1, le=1000)):
    filters, params = [], []
    for column, value in (("c.state", state), ("c.district", district), ("c.status", status), ("c.claim_type", claim_type), ("a.severity", severity)):
        if value:
            filters.append(f"{column} = ?")
            params.append(value)
    if search:
        filters.append("(c.claim_id LIKE ? OR c.village LIKE ? OR c.district LIKE ?)")
        params.extend([f"%{search}%"] * 3)
    where = "WHERE " + " AND ".join(filters) if filters else ""
    with connection() as db:
        return records(db.execute(f"""
            SELECT c.*, l.recorded_area, a.anomaly_type, a.severity, a.description, a.evidence
            FROM claims c LEFT JOIN land_records l ON l.claim_id = c.claim_id
            LEFT JOIN anomalies a ON a.claim_id = c.claim_id {where}
            ORDER BY CASE a.severity WHEN 'HIGH' THEN 1 WHEN 'MEDIUM' THEN 2 WHEN 'LOW' THEN 3 ELSE 4 END, c.claim_id
            LIMIT ?
        """, (*params, limit)))


@app.get("/api/claims/{claim_id}")
def claim_details(claim_id: str):
    with connection() as db:
        result = claim_record(db, claim_id)
        district = district_risk_rows(db, result["claim"]["state"])
        result["risk"] = next((item for item in district if item["district"] == result["claim"]["district"]), None)
        return result


@app.get("/api/anomalies")
def anomalies(severity: Optional[str] = None, state: Optional[str] = None, district: Optional[str] = None, anomaly_type: Optional[str] = None):
    filters, params = [], []
    for column, value in (("a.severity", severity), ("a.state", state), ("a.district", district), ("a.anomaly_type", anomaly_type)):
        if value:
            filters.append(f"{column} = ?")
            params.append(value)
    where = "WHERE " + " AND ".join(filters) if filters else ""
    with connection() as db:
        return records(db.execute(f"SELECT a.*, c.status, c.area_claimed, l.recorded_area FROM anomalies a JOIN claims c ON c.claim_id = a.claim_id LEFT JOIN land_records l ON l.claim_id = c.claim_id {where} ORDER BY a.anomaly_id DESC", params))


@app.get("/api/anomalies/{claim_id}")
def claim_anomalies(claim_id: str):
    with connection() as db:
        if not db.execute("SELECT 1 FROM claims WHERE claim_id = ?", (claim_id,)).fetchone():
            raise HTTPException(status_code=404, detail=f"Claim {claim_id} was not found")
        return records(db.execute("SELECT * FROM anomalies WHERE claim_id = ? ORDER BY anomaly_id", (claim_id,)))


@app.get("/api/map/claims")
def map_claims():
    with connection() as db:
        rows = db.execute("""
            SELECT c.claim_id, c.state, c.district, c.claim_type, c.status, c.latitude, c.longitude,
                   a.severity, a.anomaly_type
            FROM claims c LEFT JOIN anomalies a ON a.claim_id = c.claim_id
            WHERE c.latitude IS NOT NULL AND c.longitude IS NOT NULL
        """).fetchall()
    return {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": {"type": "Point", "coordinates": [row["longitude"], row["latitude"]]}, "properties": {key: row[key] for key in row.keys()}} for row in rows]}


def explanation(data):
    claim = data["claim"]
    anomalies = data["anomalies"]
    if not anomalies:
        return {"summary": "No potential anomaly is currently recorded for this claim.", "evidence": [f"Status: {claim['status']}", f"Claimed area: {claim['area_claimed']} ha"], "recommended_action": "Continue routine administrative monitoring."}
    anomaly = anomalies[0]
    evidence = [anomaly["evidence"]]
    if data["land_record"]:
        evidence.append(f"Survey reference: {data['land_record']['survey_reference']}")
    messages = {"LAND_MISMATCH": "Potential land-record mismatch identified. The claimed area differs significantly from the corresponding recorded area.", "DELAYED_CLAIM": "This pending claim has remained unresolved beyond the monitoring threshold.", "MISSING_DECISION_DATE": "The claim has a final status but no recorded decision date.", "MISSING_UPDATE": "The claim does not contain a last-updated date."}
    return {"summary": messages.get(anomaly["anomaly_type"], "A potential data inconsistency requires administrative review."), "evidence": evidence, "recommended_action": "Verify the claim against the latest available land record, survey reference, and case file before further administrative processing."}


@app.post("/api/ai/explain")
def ai_explain(request: ClaimExplanationRequest):
    with connection() as db:
        data = claim_record(db, request.claim_id)
    return {"claim_id": request.claim_id, **explanation(data), "provider": "deterministic evidence fallback"}


@app.post("/api/ai/query")
def ai_query(request: QuestionRequest):
    question = request.question.lower()
    with connection() as db:
        risk = district_risk_rows(db)
        context = retrieve_context(db, request.question)
        deterministic = True
        if "pending" in question and "state" in question:
            row = db.execute("SELECT state, COUNT(*) AS count FROM claims WHERE status = 'PENDING' GROUP BY state ORDER BY count DESC LIMIT 1").fetchone()
            answer = f"{row['state']} has the most pending claims, with {row['count']:,} currently pending."
            support = [dict(row)]
        elif "high-risk" in question or "attention" in question:
            answer = "The districts requiring attention first are " + ", ".join(f"{item['district']} ({item['risk_score']})" for item in risk[:3]) + ". These scores combine anomaly density and pending-claim rate."
            support = risk[:3]
        elif "approved" in question and "decision" in question:
            row = db.execute("SELECT COUNT(*) AS count FROM claims WHERE status IN ('APPROVED', 'REJECTED') AND decision_date IS NULL").fetchone()
            answer = f"{row['count']:,} claims have a final status but no recorded decision date."
            support = [dict(row)]
        else:
            deterministic = False
            row = db.execute("SELECT COUNT(*) AS count FROM claims WHERE status = 'PENDING'").fetchone()
            answer = f"There are {row['count']:,} pending claims in the current monitoring dataset. Ask about high-risk districts, pending claims by state, or missing decision dates for a focused answer."
            support = [dict(row)]
        provider = "deterministic database answer"
        if not deterministic:
            settings = llm_settings()
            llm_answer = call_llm(request.question, request.history, context)
            if llm_answer:
                answer = llm_answer
                provider = f"{settings['model']} via secure backend"
            elif settings["api_key"]:
                answer += " The configured AI provider is temporarily unavailable or has reached its usage limit, so this evidence-based fallback is being shown."
                provider = "configured LLM unavailable (deterministic fallback)"
            else:
                answer += " General questions require an LLM_API_KEY configured on the backend."
                provider = "deterministic fallback (LLM not configured)"
    return {"question": request.question, "answer": answer, "supporting_data": support, "provider": provider}


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(FRONTEND_DIR / "index.html")


app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
