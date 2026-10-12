"""Request key mapping / validation (io_v0.2)."""
from __future__ import annotations

from typing import Any

CONTRACT_VERSION = "io_v0.2"
ENGINE_VERSION = "mct-svc-0.1-demo"

CANONICAL_DEFAULTS: dict[str, Any] = {
    "flow": "E-D",
    "through": "否",
    "carry_on_only": "否",
    "stand": "远机位",
    "ac_type": "窄体",
    "seat_zone": "后舱",
    "period": "中",
    "nation": "外籍",
    "window_min": 55,
    "mode": "hybrid_t3",
}

ENUMS: dict[str, set[str]] = {
    "flow": {"E-C", "E-D"},
    "through": {"是", "否"},
    "carry_on_only": {"是", "否"},
    "stand": {"近机位", "远机位", "远远机位"},
    "ac_type": {"窄体", "宽体"},
    "seat_zone": {"前舱", "中舱", "后舱"},
    "period": {"早", "中", "晚", "凌晨"},
    "nation": {"国内", "外籍"},
    "mode": {"excel_default", "hybrid_t3"},
}

DEPRECATED_MAP = {
    "through_check": "through",
    "hand_baggage_free": "carry_on_only",
    "aircraft": "ac_type",
}


class NormalizeError(Exception):
    def __init__(self, message: str, flags: dict[str, Any] | None = None):
        super().__init__(message)
        self.message = message
        self.flags = flags or {}


def normalize(request_dict: dict[str, Any]) -> dict[str, Any]:
    """Map deprecated keys, apply defaults, validate. Returns canonical inputs + meta."""
    if not isinstance(request_dict, dict):
        raise NormalizeError("request must be a JSON object")

    raw = dict(request_dict)
    flags: dict[str, Any] = {}
    labels: list[str] = []
    deprecated_used: list[str] = []

    # passenger_type: never map
    has_passenger_type = "passenger_type" in raw
    nation_provided = "nation" in raw
    seat_zone_provided = "seat_zone" in raw
    if has_passenger_type:
        if not (nation_provided and seat_zone_provided):
            raise NormalizeError(
                "passenger_type is ambiguous; provide nation and seat_zone explicitly",
                flags={
                    "passenger_type_ambiguous": True,
                    "labels": [
                        "【未确认】passenger_type 歧义，禁止静默映射；请提供 nation + seat_zone"
                    ],
                },
            )
        # both nation and seat_zone present → ignore passenger_type
        flags["passenger_type_ambiguous"] = True
        labels.append("【废弃】忽略 passenger_type（已提供 nation+seat_zone）")
        raw.pop("passenger_type", None)

    # map deprecated keys
    for old, new in DEPRECATED_MAP.items():
        if old in raw:
            deprecated_used.append(old)
            if new not in raw:
                raw[new] = raw[old]
            else:
                labels.append(f"【废弃】同时提供 {old} 与 {new}，以正式 key {new} 为准")
            raw.pop(old, None)

    if deprecated_used:
        flags["deprecated_keys_used"] = True
        labels.append(f"【废弃】已映射键: {', '.join(deprecated_used)}")

    # apply defaults for missing optional
    defaults_applied: list[str] = []
    canonical: dict[str, Any] = {}
    for key, default in CANONICAL_DEFAULTS.items():
        if key not in raw or raw[key] is None or raw[key] == "":
            canonical[key] = default
            defaults_applied.append(key)
        else:
            canonical[key] = raw[key]

    if defaults_applied:
        flags["defaults_applied"] = defaults_applied
        labels.append(f"【缺项】已套用默认: {', '.join(defaults_applied)}")

    # validate enums / types
    for key, allowed in ENUMS.items():
        val = canonical[key]
        if val not in allowed:
            raise NormalizeError(
                f"invalid {key}={val!r}; expected one of {sorted(allowed)}",
                flags={"labels": [f"【缺项】非法枚举 {key}={val!r}"]},
            )

    try:
        canonical["window_min"] = float(canonical["window_min"])
    except (TypeError, ValueError) as e:
        raise NormalizeError(
            f"window_min must be a number > 0, got {canonical['window_min']!r}",
            flags={"labels": ["【缺项】window_min 非法"]},
        ) from e
    if canonical["window_min"] <= 0:
        raise NormalizeError(
            "window_min must be > 0",
            flags={"labels": ["【缺项】window_min 必须 > 0"]},
        )

    request_id = raw.get("request_id")
    if request_id is not None:
        request_id = str(request_id)

    return {
        "inputs": canonical,
        "request_id": request_id,
        "normalize_flags": flags,
        "normalize_labels": labels,
    }
