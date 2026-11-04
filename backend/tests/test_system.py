def test_health_and_status(client):
    assert client.get("/api/health").json() == {"status": "ok"}
    assert client.get("/api/system/status").json()["app"] == "rutrackarr"


def test_url_base(make_client):
    client = make_client(url_base="/rutrackarr/")
    assert client.get("/rutrackarr/api/health").status_code == 200
    assert client.get("/api/health").status_code == 404
