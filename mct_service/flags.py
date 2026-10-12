"""Assemble flags / labels per io_v0.2 §2.3 (+ sample-compatible aliases)."""
from __future__ import annotations

from typing import Any


def assemble_flags(
    *,
    inputs: dict[str, Any],
    nodes: list[dict[str, Any]],
    mode: str,
    mode_flags: dict[str, Any],
    normalize_flags: dict[str, Any],
    normalize_labels: list[str],
) -> dict[str, Any]:
    labels: list[str] = list(normalize_labels)
    flags: dict[str, Any] = {}

    # Always-on honesty flags (demo / contract + sample aliases)
    flags["flow_ec_ed_meaning_unconfirmed"] = True
    flags["flow_i2d_eq_ed_unconfirmed"] = True
    labels.append("【未确认】E-C/E-D 业务含义；I转D 是否≡E-D")

    flags["window_clock_unconfirmed"] = True
    labels.append("【未确认】窗口时钟（截载/登机口关闭/关舱）")

    if float(inputs.get("window_min", 0)) == 55.0:
        flags["window_55_not_in_t3_pack"] = True
        labels.append("【缺项】默认窗55非 T3 包字段")

    flags["degrade_flow_unconfirmed"] = True
    flags["degrade_static_mct_unconfirmed"] = True
    labels.append("【未确认】降级静态 MCT 对应流向/通程；本版不返回静态分钟")

    flags["baggage_in_engine_scope_unconfirmed"] = True
    labels.append("【未确认】行李是否入引擎：免提开关已入，细档行李模式未入")

    flags["blank_nation_eq_domestic_unconfirmed"] = True
    flags["seat_zone_vs_row_unconfirmed"] = True
    labels.append("【未确认】空白国籍是否=国内")
    labels.append("【未确认】座位行↔舱位切分")

    flags["period_bins_unconfirmed"] = True
    labels.append("【未确认】时段切分；Hybrid 安检用 overall")

    bus_included = any(n["id"] == "bus" and n["included"] == 1 for n in nodes)
    if bus_included or mode_flags.get("bus_p90_not_from_t3"):
        flags["bus_p90_not_from_t3"] = True
        labels.append("【缺项】摆渡无分布，P90 非来自 T3")

    flags["walk_path_unconfirmed"] = True
    labels.append("【未确认】步行路径拼法")

    # Sample / report: nodes with no T3 sample (excel fallback)
    flags["missing_nodes"] = ["taxi_in", "baggage", "apm"]
    labels.append("【缺项】无 T3 样本节点: taxi_in, baggage, apm")

    for k, v in normalize_flags.items():
        if k == "defaults_applied":
            flags["defaults_applied"] = v
        elif k == "deprecated_keys_used":
            flags["deprecated_keys_used"] = v
        elif k == "passenger_type_ambiguous":
            flags["passenger_type_ambiguous"] = v
        elif k != "labels":
            flags[k] = v

    for k, v in mode_flags.items():
        if v:
            flags[k] = v

    seen: set[str] = set()
    uniq: list[str] = []
    for lab in labels:
        if lab not in seen:
            seen.add(lab)
            uniq.append(lab)
    flags["labels"] = uniq
    return flags
