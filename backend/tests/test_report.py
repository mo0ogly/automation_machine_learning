"""
Tests for the downloadable HTML model report — routes_report / pipeline.report.
Dedicated module (test_api.py is at budget). No network.
"""

import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import app  # noqa: E402

client = TestClient(app)


def test_report_is_self_contained_html_download():
    sid = client.post("/api/session/start-demo/kev_exploit.csv").json()["session_id"]
    client.post(f"/api/session/{sid}/autorun")
    r = client.get(f"/api/session/{sid}/report")
    assert r.status_code == 200, r.text
    assert "text/html" in r.headers["content-type"]
    assert "attachment" in r.headers["content-disposition"]
    h = r.text
    assert h.startswith("<!doctype")
    assert "data:image" in h                       # figures embedded (self-contained)
    assert "Point de fonctionnement" in h          # operating point section
    assert "Verdict" in h                           # assessment section
    assert "http" not in h.split("<body>")[1].replace("data:image", "")  # no external asset URLs


def test_report_is_print_to_pdf_ready():
    sid = client.post("/api/session/start-demo/kev_exploit.csv").json()["session_id"]
    client.post(f"/api/session/{sid}/autorun")
    h = client.get(f"/api/session/{sid}/report").text
    assert "window.print()" in h                   # one-click print / save-as-PDF button
    assert "@media print" in h                       # print-optimised layout
    assert "no-print" in h                           # the button hides when printing


def test_report_requires_trained_model():
    sid = client.post("/api/session/start-demo/breastcancer.csv").json()["session_id"]
    assert client.get(f"/api/session/{sid}/report").status_code == 409


def test_report_regression_has_no_operating_point_section():
    sid = client.post("/api/session/start-demo/house_price_data.csv").json()["session_id"]
    client.post(f"/api/session/{sid}/autorun")
    h = client.get(f"/api/session/{sid}/report").text
    assert "Performance" in h
    assert "Point de fonctionnement" not in h      # regression -> no binary operating point
