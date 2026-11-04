import sqlite3


def test_defaults_and_secret_masking(client):
    view = client.get("/api/settings").json()
    assert view["values"]["rutracker.base_url"] == "https://rutracker.org"
    assert view["values"]["rutracker.requests_per_minute"] == 10
    assert view["secrets"]["rutracker.password"] is False
    assert "rutracker.password" not in view["values"]


def test_update_values_and_secrets(client, tmp_path):
    r = client.put(
        "/api/settings",
        json={
            "values": {
                "rutracker.username": " mike ",
                "rutracker.password": "s3cret",
                "rutracker.requests_per_minute": "5",
            }
        },
    )
    assert r.status_code == 200, r.text
    view = r.json()
    assert view["values"]["rutracker.username"] == "mike"
    assert view["values"]["rutracker.requests_per_minute"] == 5
    assert view["secrets"]["rutracker.password"] is True
    assert "s3cret" not in r.text
    # stored encrypted
    raw = (
        sqlite3.connect(tmp_path / "data" / "rutrackarr.db")
        .execute("select value, is_secret from settings where key='rutracker.password'")
        .fetchone()
    )
    assert raw[1] == 1 and "s3cret" not in raw[0]
    # omitting a secret keeps it; empty string clears it
    client.put("/api/settings", json={"values": {"rutracker.username": "m2"}})
    assert client.get("/api/settings").json()["secrets"]["rutracker.password"] is True
    client.put("/api/settings", json={"values": {"rutracker.password": ""}})
    assert client.get("/api/settings").json()["secrets"]["rutracker.password"] is False


def test_validation_errors(client):
    r = client.put(
        "/api/settings",
        json={
            "values": {"rutracker.requests_per_minute": 0, "flaresolverr.url": "ftp://x", "nope": 1}
        },
    )
    assert r.status_code == 422
    errors = r.json()["detail"]["errors"]
    assert set(errors) == {"rutracker.requests_per_minute", "flaresolverr.url", "nope"}
    # nothing applied
    assert client.get("/api/settings").json()["values"]["flaresolverr.url"].startswith("http://")


def test_api_key_generated_and_regenerated(client):
    first = client.get("/api/settings/api-key").json()
    assert len(first["api_key"]) == 32 and first["pinned"] is False
    assert client.get("/api/settings/api-key").json()["api_key"] == first["api_key"]
    new = client.post("/api/settings/api-key/regenerate").json()["api_key"]
    assert new != first["api_key"]


def test_api_key_pinned(make_client):
    client = make_client(api_key="0123456789abcdef0123456789abcdef")
    view = client.get("/api/settings/api-key").json()
    assert view == {"api_key": "0123456789abcdef0123456789abcdef", "pinned": True}
    assert client.post("/api/settings/api-key/regenerate").status_code == 409
    assert client.get("/api/settings").json()["api_key_pinned"] is True


def test_settings_survive_restart(make_client):
    make_client().put("/api/settings", json={"values": {"rutracker.password": "p"}})
    assert make_client().get("/api/settings").json()["secrets"]["rutracker.password"] is True
