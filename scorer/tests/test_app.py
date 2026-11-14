import pytest
from fastapi.testclient import TestClient

from scorer_engine.app import app


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with TestClient(app) as c:
        yield c


def test_normaliser_sample_scored(client, sample):
    r = client.post("/", json=sample, headers={"ce-type": "listing.normalised"})
    assert r.status_code == 202
    body = r.json()
    assert body["listing_id"] == "store_a:A-1001" and body["saved"] is None
    assert body["band"] == "low" and body["reasons"] == []


def test_suspect_has_reasons(client, sample):
    sample.update(title="Sony WH-1000XM5 1:1 replica", price_sgd=199.0, seller_age_days=12)
    body = client.post("/", json=sample).json()
    assert body["band"] == "high"
    assert {x["signal"] for x in body["reasons"]} == {"price_dev", "title_kw", "seller_age"}


def test_structured_cloudevent_scored(client, sample):
    r = client.post("/", json={"specversion": "1.0", "type": "x", "source": "y", "id": "1", "data": sample})
    assert r.status_code == 202


def test_invalid_listing_is_400(client):
    assert client.post("/", json={"listing_id": "x"}).status_code == 400
    assert client.post("/", content=b"not json").status_code == 400


def test_health_and_metrics(client):
    assert client.get("/healthz").json()["status"] == "ok"
    assert "scorer_scored_total" in client.get("/metrics/").text
