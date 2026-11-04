from fastapi.testclient import TestClient

from rutrackarr.app import create_app
from rutrackarr.config import BootstrapSettings


def test_health_and_status():
    client = TestClient(create_app(BootstrapSettings()))
    assert client.get("/api/health").json() == {"status": "ok"}
    assert client.get("/api/system/status").json()["app"] == "rutrackarr"


def test_url_base():
    client = TestClient(create_app(BootstrapSettings(url_base="/rutrackarr/")))
    assert client.get("/rutrackarr/api/health").status_code == 200
    assert client.get("/api/health").status_code == 404
