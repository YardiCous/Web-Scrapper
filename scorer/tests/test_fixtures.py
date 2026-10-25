import json
from pathlib import Path

import pytest

from scorer_engine import config
from scorer_engine.cli import load, score_all

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
FILES = sorted(FIXTURES.glob("*.json"))


def test_load_single_object_and_list(tmp_path, sample):
    one = tmp_path / "one.json"
    one.write_text(json.dumps(sample), encoding="utf-8")
    many = tmp_path / "many.json"
    many.write_text(json.dumps([sample, {**sample, "listing_id": "store_a:2"}]), encoding="utf-8")
    assert len(load(one)) == 1
    assert [l.listing_id for l in load([one, many])] == ["store_a:A-1001", "store_a:A-1001", "store_a:2"]


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.name)
def test_fixture_file_validates(path):
    assert load(path)


@pytest.fixture(scope="module")
def scores():
    return {l.listing_id: r for l, r in score_all(load(FILES))}


def test_synthetic_suspects_outscore_controls(scores):
    for cluster in ("mbp", "aj1", "apm"):
        assert scores[f"synthetic:{cluster}-suspect"].band == "high"
        assert scores[f"synthetic:{cluster}-official"].band == "low"
        assert scores[f"synthetic:{cluster}-reseller"].band == "low"


def test_every_signal_fires_somewhere(scores):
    fired = {k for r in scores.values() for k, v in r.signals.items() if v}
    assert fired == set(config.WEIGHTS)


def test_normaliser_sample_is_low(scores):
    assert scores["store_a:A-1001"].band == "low"
