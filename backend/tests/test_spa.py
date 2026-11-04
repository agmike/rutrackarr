from pathlib import Path

from fastapi.testclient import TestClient

from rutrackarr.app import create_app
from rutrackarr.config import BootstrapSettings


def _static(tmp_path: Path) -> Path:
    tmp_path.mkdir(parents=True)
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "app.js").write_text("console.log(1)")
    (tmp_path / "index.html").write_text('<html><head><base href="/" /></head></html>')
    return tmp_path


def test_spa_base_href_and_fallback(tmp_path):
    app = create_app(
        BootstrapSettings(
            url_base="/rutrackarr", static_dir=_static(tmp_path / "s"), data_dir=tmp_path / "d"
        )
    )
    client = TestClient(app)
    page = client.get("/rutrackarr/settings")
    assert page.status_code == 200
    assert '<base href="/rutrackarr/" />' in page.text
    assert client.get("/rutrackarr/assets/app.js").text == "console.log(1)"
    assert client.get("/rutrackarr/api/nope").status_code == 404


def test_spa_without_url_base(tmp_path):
    settings = BootstrapSettings(static_dir=_static(tmp_path / "s"), data_dir=tmp_path / "d")
    client = TestClient(create_app(settings))
    assert '<base href="/" />' in client.get("/").text
