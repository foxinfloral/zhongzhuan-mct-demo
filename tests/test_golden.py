"""Golden tests: default scene excel + hybrid within ±0.02."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mct_service import estimate

DEFAULT = {
    "flow": "E-D",
    "through": "否",
    "carry_on_only": "否",
    "stand": "远机位",
    "ac_type": "窄体",
    "seat_zone": "后舱",
    "period": "中",
    "nation": "外籍",
    "window_min": 55,
}

TOL = 0.02


def _near(a, b, tol=TOL):
    assert abs(float(a) - float(b)) <= tol, f"{a} != {b} (±{tol})"


def test_excel_default_golden():
    r = estimate({**DEFAULT, "mode": "excel_default", "request_id": "t-excel"})
    s = r["summary"]
    _near(s["p50_min"], 72.00)
    _near(s["p90_min"], 97.00)
    _near(s["p95_min"], 104.13)
    assert s["risk_level"] == "极高风险"
    assert s["action"] == "预改签 / 急转 / 专人保障"
    assert s["included_count"] == 10
    _near(s["e28"], 625.0)
    assert r["contract_version"] == "io_v0.2"
    c = r["compare"]["excel_default"]
    _near(c["p50_min"], 72.00)
    _near(c["p90_min"], 97.00)
    _near(c["p95_min"], 104.13)
    assert c["risk_level"] == "极高风险"


def test_hybrid_t3_golden():
    r = estimate({**DEFAULT, "mode": "hybrid_t3", "request_id": "t-hybrid"})
    s = r["summary"]
    _near(s["p50_min"], 74.40)
    _near(s["p90_min"], 94.22)
    _near(s["p95_min"], 99.87)
    assert s["risk_level"] == "极高风险"
    assert s["action"] == "预改签 / 急转 / 专人保障"
    assert s["included_count"] == 10
    _near(s["e28"], 392.89)
    c = r["compare"]["hybrid_t3"]
    _near(c["p50_min"], 74.40)
    _near(c["p90_min"], 94.22)
    _near(c["p95_min"], 99.87)
    assert c["risk_level"] == "极高风险"
    # sample-aligned hybrid node sources
    by_id = {n["id"]: n for n in r["nodes"]}
    assert by_id["deplane"]["source"] == "t3_empirical"
    assert by_id["imm"]["p50_min"] == 10.1
    assert by_id["customs"]["p50_min"] == 1.5
    assert by_id["id_process"]["p50_min"] == 5.3
    assert by_id["security"]["p50_min"] == 10.5
    assert by_id["bus"]["source"] == "excel_fallback_no_dist"
    assert "taxi_in" in r["flags"]["missing_nodes"]


def test_compare_both_modes_on_default():
    r = estimate({**DEFAULT, "mode": "hybrid_t3"})
    _near(r["compare"]["excel_default"]["p50_min"], 72.0)
    _near(r["compare"]["hybrid_t3"]["p50_min"], 74.4)


def test_passenger_type_ambiguous_without_split():
    import pytest
    from mct_service.normalize import NormalizeError

    body = {
        "flow": "E-D",
        "through": "否",
        "carry_on_only": "否",
        "stand": "远机位",
        "ac_type": "窄体",
        "period": "中",
        "window_min": 55,
        "mode": "hybrid_t3",
        "passenger_type": "外籍",
    }
    with pytest.raises(NormalizeError) as e2:
        estimate(body)
    assert e2.value.flags.get("passenger_type_ambiguous") is True


def test_passenger_type_ignored_when_split_present():
    r = estimate({**DEFAULT, "passenger_type": "whatever", "mode": "hybrid_t3"})
    assert r["flags"].get("passenger_type_ambiguous") is True
    _near(r["summary"]["p50_min"], 74.40)
