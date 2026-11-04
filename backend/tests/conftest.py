import pytest
from fastapi.testclient import TestClient

from rutrackarr.app import create_app
from rutrackarr.config import BootstrapSettings


@pytest.fixture
def make_client(tmp_path):
    def _make(**kw) -> TestClient:
        kw.setdefault("data_dir", tmp_path / "data")
        kw.setdefault("static_dir", tmp_path / "no-static")
        return TestClient(create_app(BootstrapSettings(**kw)))

    return _make


@pytest.fixture
def client(make_client) -> TestClient:
    return make_client()
