"""Feedback ingest tests: validation, action enrichment, JSONL persist."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mct_service.feedback import (
    ENUM_ALIGN_FLAG,
    RUSH_TRANSFER_FLAG,
    FEEDBACK_DIR,
    FeedbackError,
    normalize_action_item,
    process_feedback,
)


@pytest.fixture(autouse=True)
def _isolate_feedback_dir(tmp_path, monkeypatch):
    """Redirect JSONL writes to tmp so tests do not pollute data/feedback."""
    import mct_service.feedback as fb

    monkeypatch.setattr(fb, "FEEDBACK_DIR", tmp_path / "feedback")
    (tmp_path / "feedback").mkdir(parents=True, exist_ok=True)
    yield


def _min_body(**overrides):
    body = {
        "request_id": "demo-fb-1",
        "recorded_at": "2026-09-02T01:20:00+08:00",
        "outcome": {"made_connection": True},
        "actions_taken": [{"code": "pre_rebook", "label": "预改签"}],
        "timestamps": {
            "in_ata": "2026-09-02T00:40:00+08:00",
            "out_atd_or_gate_close": "2026-09-02T01:05:00+08:00",
            "connection_declared_at": "2026-09-02T01:10:00+08:00",
        },
        "pax_key": "demo-pax-0001",
        "estimate_echo": {
            "mode": "hybrid_t3",
            "window_min": 55,
            "risk_level": "极高风险",
            "p50_min": 74.4,
        },
        "source": "occ_demo_ui",
        "operator_note": "【演示】",
    }
    body.update(overrides)
    return body


def test_missing_request_id_400():
    with pytest.raises(FeedbackError) as ei:
        process_feedback({"outcome": {"made_connection": True}})
    assert "【缺项】request_id" in ei.value.flags["labels"]


def test_minimal_ok_writes_jsonl(tmp_path):
    import mct_service.feedback as fb

    resp = process_feedback(_min_body())
    assert resp["ok"] is True
    assert resp["feedback_id"].startswith("fb-")
    assert resp["request_id"] == "demo-fb-1"
    assert "path" in resp
    day_file = fb.FEEDBACK_DIR / Path(resp["path"]).name
    assert day_file.is_file()
    line = day_file.read_text(encoding="utf-8").strip().splitlines()[-1]
    row = json.loads(line)
    assert row["schema_version"] == "feedback_v0.1"
    assert row["engine_version"] == "mct-svc-0.1-demo"
    assert row["contract_version"] == "io_v0.2"
    assert row["payload"]["request_id"] == "demo-fb-1"
    act = row["payload"]["actions_taken"][0]
    assert act["code"] == "pre_rebook"
    assert act["normalized_code"] == "pre_rebook"
    assert act["enum_status"] == "unconfirmed"
    assert ENUM_ALIGN_FLAG in row["flags"]["labels"]


def test_warn_pool_maps_to_watch_pool():
    labels: list[str] = []
    bits: dict = {}
    out = normalize_action_item({"code": "warn_pool"}, labels, bits)
    assert out["code"] == "warn_pool"
    assert out["normalized_code"] == "watch_pool"
    assert out["enum_status"] == "unconfirmed"


def test_watch_pool_identity():
    labels: list[str] = []
    bits: dict = {}
    out = normalize_action_item({"code": "watch_pool"}, labels, bits)
    assert out["normalized_code"] == "watch_pool"
    assert out["enum_status"] == "unconfirmed"


def test_inflight_warn_maps_to_confirm():
    labels: list[str] = []
    bits: dict = {}
    out = normalize_action_item({"code": "inflight_warn"}, labels, bits)
    assert out["code"] == "inflight_warn"
    assert out["normalized_code"] == "inflight_warn_confirm"


def test_rush_transfer_maps_dedicated_assist_keeps_raw():
    labels: list[str] = []
    bits: dict = {}
    out = normalize_action_item({"code": "rush_transfer"}, labels, bits)
    assert out["code"] == "rush_transfer"
    assert out["normalized_code"] == "dedicated_assist"
    assert out["enum_status"] == "unconfirmed"
    assert RUSH_TRANSFER_FLAG in labels

    resp = process_feedback(
        _min_body(actions_taken=[{"code": "rush_transfer", "label": "急转"}])
    )
    assert RUSH_TRANSFER_FLAG in resp["flags"]["labels"]
    assert ENUM_ALIGN_FLAG in resp["flags"]["labels"]


def test_unknown_code_flag():
    labels: list[str] = []
    bits: dict = {}
    out = normalize_action_item({"code": "totally_new"}, labels, bits)
    assert out["code"] == "totally_new"
    assert out["normalized_code"] == "unknown"
    assert bits.get("action_code_unconfirmed") is True


def test_cjk_action_string_not_accepted_as_code():
    """estimate summary.action Chinese long string → unknown + flag."""
    labels: list[str] = []
    bits: dict = {}
    chinese = "预改签 / 急转 / 专人保障"
    out = normalize_action_item({"code": chinese}, labels, bits)
    assert out["normalized_code"] == "unknown"
    assert out["code"] == chinese
    assert bits.get("action_code_unconfirmed") is True
    assert any("CJK" in lab or "空格" in lab for lab in labels)


def test_missing_made_connection_accepted_with_flag():
    body = _min_body()
    body["outcome"] = {"outcome_note": "unknown yet"}
    resp = process_feedback(body)
    assert resp["ok"] is True
    assert "【缺项】outcome.made_connection" in resp["flags"]["labels"]


def test_missing_estimate_echo_flag():
    body = _min_body()
    del body["estimate_echo"]
    resp = process_feedback(body)
    assert "【缺项】estimate_echo" in resp["flags"]["labels"]


def test_pii_stripped():
    body = _min_body(name="张三", phone="13800000000")
    resp = process_feedback(body)
    assert resp["ok"] is True
    assert "【缺项】pii_stripped" in resp["flags"]["labels"]
    assert resp["flags"].get("pii_stripped") is True


def test_bad_pax_key_400():
    with pytest.raises(FeedbackError):
        process_feedback(_min_body(pax_key="中文证件号"))


def test_operator_note_truncated():
    note = "x" * 600
    resp = process_feedback(_min_body(operator_note=note))
    assert resp["ok"] is True
    # read last line from redirected dir
    import mct_service.feedback as fb

    files = list(fb.FEEDBACK_DIR.glob("*.jsonl"))
    assert files
    row = json.loads(files[0].read_text(encoding="utf-8").strip().splitlines()[-1])
    assert len(row["payload"]["operator_note"]) == 500


def test_timestamps_missing_keys_flagged():
    body = _min_body(timestamps={})
    resp = process_feedback(body)
    labs = resp["flags"]["labels"]
    assert "【缺项】timestamps.in_ata" in labs
    assert "【缺项】timestamps.out_atd_or_gate_close" in labs
    assert "【缺项】timestamps.connection_declared_at" in labs


def test_export_day(tmp_path):
    from mct_service.feedback import export_feedback_day
    import mct_service.feedback as fb

    process_feedback(_min_body(request_id="exp-1"))
    # find which day was written
    files = list(fb.FEEDBACK_DIR.glob("*.jsonl"))
    assert files
    day = files[0].stem
    text = export_feedback_day(day)
    assert "exp-1" in text
    assert export_feedback_day("1999-01-01") == ""
