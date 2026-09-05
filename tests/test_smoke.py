from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


def test_root_and_dashboard():
    root = client.get("/")
    assert root.status_code == 200

    dashboard = client.get("/api/dashboard")
    assert dashboard.status_code == 200
    assert dashboard.headers["content-type"].startswith("application/json")
