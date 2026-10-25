"""
Idempotency against a real PostgreSQL. Skipped unless DATABASE_URL is set:

    docker compose up -d db
    DATABASE_URL=postgresql://user:password@localhost:5432/listings pytest tests/test_store.py
"""

import os
import uuid
from pathlib import Path

import pytest

from scorer_engine import signals, store
from scorer_engine.combiner import combine

SQL = (Path(__file__).resolve().parent.parent / "sql" / "risk_scores.sql").read_text()


@pytest.fixture
def conn():
    if not os.environ.get("DATABASE_URL"):
        pytest.skip("DATABASE_URL not set")
    import psycopg
    with psycopg.connect(os.environ["DATABASE_URL"]) as c:
        c.execute(SQL)
        c.commit()
        yield c


def _score(listing):
    sig, facts = signals.compute(listing)
    return combine(sig, facts), store.input_hash(listing)


def _row(conn, listing_id):
    return conn.execute(
        "SELECT score, input_hash, computed_at FROM risk_scores WHERE listing_id = %s", (listing_id,)
    ).fetchone()


def test_hash_is_stable(make_listing, sample):
    # same data, different key order -> same hash
    reordered = dict(reversed(list(sample.items())))
    assert store.input_hash(make_listing()) == store.input_hash(make_listing(**reordered))


def test_hash_changes_with_cluster_median(make_listing):
    assert store.input_hash(make_listing()) != store.input_hash(make_listing(cluster_price_median_sgd=400))


def test_hash_ignores_fetched_at(make_listing):
    a = make_listing(fetched_at="2026-10-25T03:00:00Z")
    b = make_listing(fetched_at="2026-10-26T03:00:00Z")
    assert store.input_hash(a) == store.input_hash(b)


def test_replay_is_noop(conn, make_listing):
    l = make_listing(listing_id=f"test:{uuid.uuid4()}")
    result, h = _score(l)
    assert store.upsert(conn, l, result, h) is True
    conn.commit()
    first = _row(conn, l.listing_id)
    for _ in range(50):
        assert store.upsert(conn, l, result, h) is False
    conn.commit()
    assert _row(conn, l.listing_id) == first
    conn.execute("DELETE FROM risk_scores WHERE listing_id = %s", (l.listing_id,))
    conn.commit()


def test_moved_median_rescores(conn, make_listing):
    lid = f"test:{uuid.uuid4()}"
    l = make_listing(listing_id=lid, price_sgd=50, cluster_price_median_sgd=55)
    r1, h1 = _score(l)
    store.upsert(conn, l, r1, h1)
    conn.commit()
    l = make_listing(listing_id=lid, price_sgd=50, cluster_price_median_sgd=200)
    r2, h2 = _score(l)
    assert store.upsert(conn, l, r2, h2) is True
    conn.commit()
    score, hash_, _ = _row(conn, l.listing_id)
    assert hash_ == h2 and score == pytest.approx(r2.score, abs=1e-4)
    conn.execute("DELETE FROM risk_scores WHERE listing_id = %s", (l.listing_id,))
    conn.commit()
