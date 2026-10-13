"""Default-used labels and HEAD / support."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient

from mct_service import estimate
from serve import app

client = TestClient(app)


def test_empty_body_labels_every_default():
    r = client.post("/v1/mct/estimate", json={})
    assert r.status_code == 200
    f = r.json()["flags"]
    assert "已用默认 window_min=55" in f["labels"]
    assert "已用默认 period=中" in f["labels"]
    assert "已用默认 mode=hybrid_t3" in f["labels"]
    assert set(f["defaults_applied"]) >= {"window_min", "period", "mode", "flow"}


def test_partial_body_only_missing_labelled():
    r = client.post("/v1/mct/estimate", json={"window_min": 55})
    assert r.status_code == 200
    f = r.json()["flags"]
    assert "window_min" not in f["defaults_applied"]
    assert not any(l.startswith("已用默认 window_min") for l in f["labels"])
    assert "已用默认 mode=hybrid_t3" in f["labels"]


def test_defaults_do_not_change_values():
    a = estimate({})["summary"]
    assert abs(a["p50_min"] - 74.40) <= 0.02 and abs(a["p95_min"] - 99.87) <= 0.02


def test_root_head_and_get():
    h = client.head("/", follow_redirects=False)
    assert h.status_code == 307
    g = client.get("/", follow_redirects=False)
    assert g.status_code == 307 and g.headers["location"] == "/min-loop.html"
