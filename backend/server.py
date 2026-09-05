import json
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "fra_monitoring.db"
FRONTEND_DIR = BASE_DIR / "frontend"


def get_connection():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def rows_to_dict(rows):
    return [dict(row) for row in rows]


def dashboard_data():
    with get_connection() as connection:
        summary = connection.execute(
            """
            SELECT
                COUNT(*) AS total_claims,
                SUM(status = 'APPROVED') AS approved_claims,
                SUM(status = 'PENDING') AS pending_claims,
                SUM(status = 'UNDER_REVIEW') AS review_claims,
                SUM(status IN ('APPROVED', 'REJECTED') AND decision_date IS NULL) AS missing_decisions
            FROM claims
            """
        ).fetchone()
        anomalies = connection.execute(
            """
            SELECT severity, COUNT(*) AS count
            FROM anomalies
            GROUP BY severity
            ORDER BY CASE severity WHEN 'HIGH' THEN 1 WHEN 'MEDIUM' THEN 2 ELSE 3 END
            """
        ).fetchall()
        states = connection.execute(
            """
            SELECT
                state,
                COUNT(*) AS total_claims,
                SUM(status = 'APPROVED') AS approved_claims,
                SUM(status = 'PENDING') AS pending_claims,
                SUM(status = 'UNDER_REVIEW') AS review_claims,
                COUNT(DISTINCT CASE WHEN a.anomaly_id IS NOT NULL THEN c.claim_id END) AS flagged_claims
            FROM claims c
            LEFT JOIN anomalies a ON a.claim_id = c.claim_id
            GROUP BY state
            ORDER BY flagged_claims DESC, total_claims DESC
            """
        ).fetchall()
        districts = connection.execute(
            """
            SELECT
                d.district_id,
                d.district_name,
                s.state_name,
                d.latitude,
                d.longitude,
                COUNT(DISTINCT c.claim_id) AS total_claims,
                SUM(c.status = 'PENDING') AS pending_claims,
                COUNT(DISTINCT a.anomaly_id) AS anomaly_count,
                SUM(a.severity = 'HIGH') AS high_anomalies
            FROM districts d
            JOIN states s ON s.state_id = d.state_id
            LEFT JOIN claims c ON c.district = d.district_name AND c.state = s.state_name
            LEFT JOIN anomalies a ON a.claim_id = c.claim_id
            GROUP BY d.district_id
            ORDER BY anomaly_count DESC, total_claims DESC
            """
        ).fetchall()
        recent_anomalies = connection.execute(
            """
            SELECT a.claim_id, a.state, a.district, a.anomaly_type, a.severity,
                   a.description, a.evidence, c.status, c.area_claimed,
                   l.recorded_area, c.submission_date
            FROM anomalies a
            JOIN claims c ON c.claim_id = a.claim_id
            LEFT JOIN land_records l ON l.claim_id = c.claim_id
            ORDER BY CASE a.severity WHEN 'HIGH' THEN 1 WHEN 'MEDIUM' THEN 2 ELSE 3 END,
                     a.anomaly_id DESC
            LIMIT 80
            """
        ).fetchall()
    return {
        "summary": dict(summary),
        "anomalies": rows_to_dict(anomalies),
        "states": rows_to_dict(states),
        "districts": rows_to_dict(districts),
        "recent_anomalies": rows_to_dict(recent_anomalies),
    }


def search_claims(query):
    term = f"%{query}%"
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT c.claim_id, c.state, c.district, c.village, c.status,
                   c.claim_type, c.area_claimed, c.submission_date,
                   c.latitude, c.longitude, a.anomaly_type, a.severity,
                   a.description, a.evidence, l.recorded_area
            FROM claims c
            LEFT JOIN anomalies a ON a.claim_id = c.claim_id
            LEFT JOIN land_records l ON l.claim_id = c.claim_id
            WHERE c.claim_id LIKE ? OR c.state LIKE ? OR c.district LIKE ?
               OR c.village LIKE ? OR c.status LIKE ?
            ORDER BY CASE WHEN a.severity = 'HIGH' THEN 1 WHEN a.severity = 'MEDIUM' THEN 2 ELSE 3 END
            LIMIT 50
            """,
            (term, term, term, term, term),
        ).fetchall()
    return rows_to_dict(rows)


class Handler(BaseHTTPRequestHandler):
    def send_json(self, payload, status=200):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/dashboard":
            self.send_json(dashboard_data())
            return
        if parsed.path == "/api/search":
            query = parse_qs(parsed.query).get("q", [""])[0].strip()
            self.send_json({"results": search_claims(query)} if query else {"results": []})
            return
        file_path = FRONTEND_DIR / ("index.html" if parsed.path == "/" else parsed.path.lstrip("/"))
        if file_path.is_file() and FRONTEND_DIR in file_path.parents:
            content_type = "text/html; charset=utf-8" if file_path.suffix == ".html" else "text/css; charset=utf-8" if file_path.suffix == ".css" else "application/javascript; charset=utf-8"
            body = file_path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_json({"error": "Not found"}, 404)

    def log_message(self, format, *args):
        print(f"{self.address_string()} - {format % args}")


if __name__ == "__main__":
    port = 8000
    print(f"VANADHIKAR AI running at http://localhost:{port}")
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
