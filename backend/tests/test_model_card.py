"""
Tests for the enriched model card — operating point + data-driven assessment
(pipeline.scoring.model_card). Dedicated module (test_api.py is at budget). No network.
"""

import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import app  # noqa: E402

client = TestClient(app)


def _card(dataset):
    sid = client.post(f"/api/session/start-demo/{dataset}").json()["session_id"]
    client.post(f"/api/session/{sid}/autorun")
    r = client.get(f"/api/session/{sid}/model-card")
    assert r.status_code == 200, r.text
    return r.json()


def test_card_binary_has_operating_point_and_assessment():
    card = _card("kev_exploit.csv")
    op = card["operating_point"]
    assert op is not None
    assert 0.0 <= op["threshold"] <= 1.0
    assert 0.0 <= op["recall"] <= 1.0 and 0.0 <= op["precision"] <= 1.0
    a = card["assessment"]
    assert a["verdict"] in ("Déployable", "À utiliser avec prudence", "Fragile")
    assert isinstance(a["strengths"], list) and isinstance(a["cautions"], list)
    assert any("dérive" in c for c in a["cautions"])          # always warns about drift


def test_card_regression_has_no_operating_point():
    card = _card("house_price_data.csv")
    assert card["operating_point"] is None
    assert card["assessment"] is not None


def test_card_assessment_reflects_leakage_free():
    card = _card("breastcancer.csv")
    strengths = " ".join(card["assessment"]["strengths"])
    assert "anti-fuite" in strengths                          # split-first pipeline is leakage-free
