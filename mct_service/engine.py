"""Excel + hybrid_t3 compute. Formulas from dynamic_mct.py — not invented."""
from __future__ import annotations

import sys
from math import sqrt
from pathlib import Path
from typing import Any

# Import excel calculator without modifying it
_MCT_ROOT = Path(__file__).resolve().parent.parent
if str(_MCT_ROOT) not in sys.path:
    sys.path.insert(0, str(_MCT_ROOT))

from dynamic_mct import Inputs, compute as excel_compute  # noqa: E402

from .flags import assemble_flags
from .normalize import (
    CONTRACT_VERSION,
    ENGINE_VERSION,
    NormalizeError,
    normalize,
)

# Stable node ids in excel nodes() order
NODE_IDS = [
    "taxi_in",
    "deplane",
    "bus",
    "imm",
    "customs",
    "baggage",
    "id_process",
    "walk",
    "apm",
    "security",
]

# Hybrid overrides from io_v0.2 §3 / out/report.md (1 decimal as reported)
HYBRID_DEPLANE_NARROW_REAR = (11.0, 13.0, 36)  # 窄体+后舱
HYBRID_IMM_FOREIGN = (10.1, 21.3, 175)  # 外籍
HYBRID_CUSTOMS = (1.5, 2.7, 112)
HYBRID_ID_PROCESS = (5.3, 12.9, 112)
HYBRID_SECURITY = (10.5, 16.0, 112)  # overall; period bins unconfirmed


def _r2(x: float) -> float:
    return round(float(x), 2)


def _summarize(
    p50: float, p90: float, p95: float, e28: float, window: float, included_count: int, risk: str, action: str
) -> dict[str, Any]:
    return {
        "p50_min": _r2(p50),
        "p90_min": _r2(p90),
        "p95_min": _r2(p95),
        "window_min": int(window) if float(window) == int(float(window)) else float(window),
        "risk_level": risk,
        "action": action,
        "included_count": included_count,
        "e28": _r2(e28),
    }


def _compare_block(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "p50_min": summary["p50_min"],
        "p90_min": summary["p90_min"],
        "p95_min": summary["p95_min"],
        "risk_level": summary["risk_level"],
    }


def _excel_nodes_list(inp: Inputs) -> list[dict[str, Any]]:
    result = excel_compute(inp)
    out: list[dict[str, Any]] = []
    for nid, n in zip(NODE_IDS, result["nodes"]):
        out.append(
            {
                "id": nid,
                "name": n.name,
                "included": int(n.included),
                "p50_min": float(n.p50),
                "p90_min": float(n.p90),
                "source": "excel_default",
                "source_n": None,
                "note": None,
            }
        )
    # light notes for excel mode
    for node in out:
        if node["id"] == "imm":
            node["note"] = "外籍" if inp.nation == "外籍" else "国内"
        if node["id"] == "security":
            if inp.period in ("早", "中"):
                node["note"] = "早/中"
            elif inp.period == "晚":
                node["note"] = "晚"
            else:
                node["note"] = "凌晨"
    return out


def _aggregate(nodes: list[dict[str, Any]], window: float) -> tuple[dict[str, Any], float, float, float, float]:
    included = [n for n in nodes if n["included"] == 1]
    p50 = sum(n["p50_min"] for n in included)
    e28 = sum((n["p90_min"] - n["p50_min"]) ** 2 for n in included)
    p90 = p50 + sqrt(e28)
    p95 = p50 + 1.2852 * sqrt(e28)
    # reuse excel risk rule
    from dynamic_mct import risk_and_action

    risk, action = risk_and_action(window, p50, p90, p95)
    summary = _summarize(p50, p90, p95, e28, window, len(included), risk, action)
    return summary, p50, p90, p95, e28


def _apply_hybrid(excel_nodes: list[dict[str, Any]], inp: Inputs) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Start from excel nodes; override p50/p90 when hybrid data applies."""
    nodes = [dict(n) for n in excel_nodes]
    extra_flags: dict[str, Any] = {}
    by_id = {n["id"]: n for n in nodes}

    # deplane: only 窄体+后舱 → hybrid; else excel + flag
    deplane = by_id["deplane"]
    if deplane["included"] == 1:
        if inp.ac_type == "窄体" and inp.seat_zone == "后舱":
            p50, p90, n = HYBRID_DEPLANE_NARROW_REAR
            deplane["p50_min"] = p50
            deplane["p90_min"] = p90
            deplane["source"] = "t3_empirical"
            deplane["source_n"] = n
            deplane["note"] = "窄体后舱；座位≥21切分【未确认】"
        else:
            deplane["source"] = "excel_default"
            deplane["source_n"] = 0
            deplane["note"] = "非窄体后舱，无确认 Hybrid 映射，回退 Excel"
            extra_flags["seat_zone_vs_row_unconfirmed"] = True

    # imm
    imm = by_id["imm"]
    if imm["included"] == 1:
        if inp.nation == "外籍":
            p50, p90, n = HYBRID_IMM_FOREIGN
            imm["p50_min"] = p50
            imm["p90_min"] = p90
            imm["source"] = "t3_empirical"
            imm["source_n"] = n
            imm["note"] = None
        else:
            # 国内 → keep excel; blank≠domestic
            imm["source"] = "excel_default"
            imm["source_n"] = None
            imm["note"] = "国内无确认 T3 映射，回退 Excel；空白国籍≠国内【未确认】"
            extra_flags["blank_nation_eq_domestic_unconfirmed"] = True

    # customs always hybrid in hybrid mode
    customs = by_id["customs"]
    if customs["included"] == 1:
        p50, p90, n = HYBRID_CUSTOMS
        customs["p50_min"] = p50
        customs["p90_min"] = p90
        customs["source"] = "t3_empirical"
        customs["source_n"] = n
        customs["note"] = None

    # id_process when included
    idp = by_id["id_process"]
    if idp["included"] == 1:
        p50, p90, n = HYBRID_ID_PROCESS
        idp["p50_min"] = p50
        idp["p90_min"] = p90
        idp["source"] = "t3_empirical"
        idp["source_n"] = n
        idp["note"] = None

    # security overall hybrid
    sec = by_id["security"]
    if sec["included"] == 1:
        p50, p90, n = HYBRID_SECURITY
        sec["p50_min"] = p50
        sec["p90_min"] = p90
        sec["source"] = "t3_empirical"
        sec["source_n"] = n
        sec["note"] = "overall；时段切分【未确认】"
        extra_flags["period_bins_unconfirmed"] = True

    # bus: excel + flag when included
    bus = by_id["bus"]
    if bus["included"] == 1:
        bus["source"] = "excel_fallback_no_dist"
        bus["source_n"] = 10
        bus["note"] = "T3仅标准点值不能估P90"
        extra_flags["bus_p90_not_from_t3"] = True

    # taxi_in / baggage / apm: excel missing T3
    for nid, sn in (("taxi_in", 0), ("baggage", 0), ("apm", 0)):
        node = by_id[nid]
        if node["source"] != "t3_empirical":
            node["source"] = "excel_default"
            node["source_n"] = sn

    # walk: excel + path unconfirmed
    walk = by_id["walk"]
    walk["source"] = "excel_default"
    walk["source_n"] = None
    walk["note"] = None  # path unconfirmed flagged in flags.walk_path_unconfirmed
    extra_flags["walk_path_unconfirmed"] = True

    return nodes, extra_flags


def _run_mode(inp: Inputs, mode: str) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    excel_nodes = _excel_nodes_list(inp)
    mode_flags: dict[str, Any] = {}
    if mode == "excel_default":
        nodes = excel_nodes
        # honesty flags still relevant for bus/walk when included
        if any(n["id"] == "bus" and n["included"] == 1 for n in nodes):
            mode_flags["bus_p90_not_from_t3"] = True
        mode_flags["walk_path_unconfirmed"] = True
        mode_flags["period_bins_unconfirmed"] = True
    elif mode == "hybrid_t3":
        nodes, mode_flags = _apply_hybrid(excel_nodes, inp)
    else:
        raise NormalizeError(f"unknown mode={mode!r}")

    summary, *_ = _aggregate(nodes, float(inp.window_min))
    return summary, nodes, mode_flags


def estimate(request_dict: dict[str, Any]) -> dict[str, Any]:
    """Pure function: request_dict -> response_dict (io_v0.2). Raises NormalizeError on 400."""
    meta = normalize(request_dict)
    inputs = meta["inputs"]
    inp = Inputs(
        flow=inputs["flow"],
        through=inputs["through"],
        carry_on_only=inputs["carry_on_only"],
        stand=inputs["stand"],
        ac_type=inputs["ac_type"],
        seat_zone=inputs["seat_zone"],
        period=inputs["period"],
        nation=inputs["nation"],
        window_min=float(inputs["window_min"]),
    )
    mode = inputs["mode"]

    # Always compute both modes into compare; summary uses request mode
    excel_summary, excel_nodes, excel_flags = _run_mode(inp, "excel_default")
    hybrid_summary, hybrid_nodes, hybrid_flags = _run_mode(inp, "hybrid_t3")

    if mode == "excel_default":
        summary, nodes, mode_flags = excel_summary, excel_nodes, excel_flags
    else:
        summary, nodes, mode_flags = hybrid_summary, hybrid_nodes, hybrid_flags

    flags = assemble_flags(
        inputs=inputs,
        nodes=nodes,
        mode=mode,
        mode_flags=mode_flags,
        normalize_flags=meta["normalize_flags"],
        normalize_labels=meta["normalize_labels"],
    )

    return {
        "request_id": meta["request_id"],
        "contract_version": CONTRACT_VERSION,
        "engine_version": ENGINE_VERSION,
        "mode": mode,
        "inputs": {
            "flow": inputs["flow"],
            "through": inputs["through"],
            "carry_on_only": inputs["carry_on_only"],
            "stand": inputs["stand"],
            "ac_type": inputs["ac_type"],
            "seat_zone": inputs["seat_zone"],
            "period": inputs["period"],
            "nation": inputs["nation"],
            "window_min": inputs["window_min"]
            if float(inputs["window_min"]) != int(float(inputs["window_min"]))
            else int(float(inputs["window_min"])),
        },
        "summary": summary,
        "compare": {
            "excel_default": _compare_block(excel_summary),
            "hybrid_t3": _compare_block(hybrid_summary),
        },
        "nodes": nodes,
        "flags": flags,
        "engine": {
            "formula": "point_estimate_v0",
            "p90": "P50+sqrt(sum((P90-P50)^2))",
            "p95": "P50+1.2852*sqrt(sum((P90-P50)^2))",
            "no_lognormal_sigma": True,
            "no_sum_of_p90": True,
        },
    }
