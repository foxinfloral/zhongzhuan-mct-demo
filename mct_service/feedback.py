"""Feedback ingest: validate / normalize / append-only JSONL (feedback_v0.1).

Action codes map to v0.3 ladder ids (design gate passed):
observe / watch_pool / inflight_warn_confirm / dedicated_assist / pre_rebook.
Demo aliases warn_pool / inflight_warn still accepted. rush_transfer 【未确认】.
Does NOT change estimate formulas, io_v0.2, or golden path (v0.3 estimate = separate gate).
Canonical: contract/io_v0.3.fields.json feedback_action_codes; see feedback_action_map_v0.3.md.
"""
from __future__ import annotations

import json
import re
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .normalize import CONTRACT_VERSION, ENGINE_VERSION, NormalizeError

SCHEMA_VERSION = "feedback_v0.1"
TZ_SH = ZoneInfo("Asia/Shanghai")

# Display labels; five ladder ids design-gated — see feedback_action_map_v0.3.md
ACTION_LABELS: dict[str, str] = {
    "observe": "正常衔接观察",
    "warn_pool": "进入预警池",
    "watch_pool": "进入预警池，准备触达",
    "inflight_warn": "飞行中预警",
    "inflight_warn_confirm": "飞行中预警 + 落地前方案确认",
    "pre_rebook": "预改签",
    "rush_transfer": "急转",
    "dedicated_assist": "专人保障",
    "other": "其他",
    "unknown": "未知",
}

# raw code → normalized_code (v0.3 ladder id; rush_transfer still unconfirmed)
ACTION_NORMALIZE: dict[str, str] = {
    "observe": "observe",
    "warn_pool": "watch_pool",
    "watch_pool": "watch_pool",
    "inflight_warn": "inflight_warn_confirm",
    "inflight_warn_confirm": "inflight_warn_confirm",
    "dedicated_assist": "dedicated_assist",
    "pre_rebook": "pre_rebook",
    "rush_transfer": "dedicated_assist",  # NOT a sixth ladder rung; keep raw=rush_transfer
    "other": "other",
    "unknown": "unknown",
}

ENUM_ALIGN_FLAG = (
    "动作枚举对齐 v0.3 ladder 五档（设计闸已过）；"
    "演示别名 warn_pool/inflight_warn 兼容；estimate v0.3 实现另闸"
)
RUSH_TRANSFER_FLAG = (
    "【未确认】rush_transfer 单列前与 dedicated_assist 同挂；非已拍板第六档"
)
TIMESTAMP_CLOCK_FLAG = (
    "【未确认】timestamps 相对截载/关舱/登机（与 estimate 窗口时钟同一未确认）"
)

PII_KEYS = frozenset({"name", "id_number", "passport", "phone", "pnr"})
PAX_KEY_RE = re.compile(r"^[A-Za-z0-9._:-]{1,64}$")
# spaces or CJK → reject as formal code (estimate summary.action long strings)
_INVALID_CODE_RE = re.compile(r"[\s\u4e00-\u9fff]")
TIMESTAMP_KEYS = ("in_ata", "out_atd_or_gate_close", "connection_declared_at")
OPERATOR_NOTE_MAX = 500

_MISSING = object()

_MCT_ROOT = Path(__file__).resolve().parents[1]
FEEDBACK_DIR = _MCT_ROOT / "data" / "feedback"

_write_lock = threading.Lock()


def _now_shanghai() -> datetime:
    return datetime.now(TZ_SH)


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def _date_str(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d")


def _feedback_id(dt: datetime) -> str:
    return f"fb-{dt.strftime('%Y%m%d')}-{uuid.uuid4().hex[:8]}"


def _relative_path(day: str) -> str:
    return f"data/feedback/{day}.jsonl"


def _absolute_path(day: str) -> Path:
    return FEEDBACK_DIR / f"{day}.jsonl"


class FeedbackError(NormalizeError):
    """Reuse NormalizeError shape for app.py 400 handling."""


def _dedupe_labels(labels: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for lab in labels:
        if lab not in seen:
            seen.add(lab)
            out.append(lab)
    return out


def normalize_action_item(item: dict[str, Any], labels: list[str], flag_bits: dict[str, Any]) -> dict[str, Any]:
    """Enrich one actions_taken item with normalized_code + enum_status=unconfirmed."""
    raw_code = item.get("code")
    label_in = item.get("label")
    at_in = item.get("at")

    code_str: str | None
    if raw_code is None:
        code_str = None
    elif isinstance(raw_code, str):
        code_str = raw_code.strip() if raw_code.strip() else None
    else:
        code_str = str(raw_code)

    invalid_as_code = False
    if code_str is not None and _INVALID_CODE_RE.search(code_str):
        # Chinese long strings / spaces from estimate summary.action — not enum codes
        invalid_as_code = True
        flag_bits["action_code_unconfirmed"] = True
        labels.append("【未确认】action_code_unconfirmed")
        labels.append("【未确认】actions_taken.code 含空格/CJK，不可作枚举码")

    if code_str is None or invalid_as_code:
        normalized = "unknown"
        kept_code = code_str if code_str is not None else "unknown"
        if code_str is None:
            flag_bits["action_code_unconfirmed"] = True
            labels.append("【未确认】action_code_unconfirmed")
    elif code_str in ACTION_NORMALIZE:
        normalized = ACTION_NORMALIZE[code_str]
        kept_code = code_str
        if code_str == "rush_transfer":
            labels.append(RUSH_TRANSFER_FLAG)
    else:
        normalized = "unknown"
        kept_code = code_str
        flag_bits["action_code_unconfirmed"] = True
        labels.append("【未确认】action_code_unconfirmed")

    display = label_in if isinstance(label_in, str) and label_in.strip() else None
    if display is None:
        display = ACTION_LABELS.get(kept_code) or ACTION_LABELS.get(normalized)

    out: dict[str, Any] = {
        "code": kept_code,
        "normalized_code": normalized,
        "enum_status": "unconfirmed",
    }
    if display is not None:
        out["label"] = display
    if isinstance(at_in, str) and at_in.strip():
        out["at"] = at_in.strip()
    elif at_in is not None and not isinstance(at_in, str):
        out["at"] = str(at_in)
    return out


def process_feedback(body: dict[str, Any]) -> dict[str, Any]:
    """Validate, normalize, append JSONL. Returns API response dict.

    Raises FeedbackError / NormalizeError on hard validation failure (400).
    """
    if not isinstance(body, dict):
        raise FeedbackError(
            "request must be a JSON object",
            flags={"labels": ["【缺项】请求体须为对象"]},
        )

    labels: list[str] = []
    flag_bits: dict[str, Any] = {}
    raw = dict(body)

    # --- PII: strip known keys ---
    stripped: list[str] = []
    for k in list(raw.keys()):
        if k in PII_KEYS:
            raw.pop(k)
            stripped.append(k)
    for nested_key in ("outcome", "timestamps", "estimate_echo"):
        nested = raw.get(nested_key)
        if isinstance(nested, dict):
            for k in list(nested.keys()):
                if k in PII_KEYS:
                    nested.pop(k)
                    stripped.append(f"{nested_key}.{k}")
    if stripped:
        flag_bits["pii_stripped"] = True
        flag_bits["pii_keys_stripped"] = stripped
        labels.append("【缺项】pii_stripped")

    # --- request_id (required) ---
    request_id = raw.get("request_id")
    if request_id is None or (isinstance(request_id, str) and not request_id.strip()):
        raise FeedbackError(
            "request_id is required",
            flags={"labels": ["【缺项】request_id"]},
        )
    if not isinstance(request_id, str):
        raise FeedbackError(
            "request_id must be a string",
            flags={"labels": ["【缺项】request_id"]},
        )
    request_id = request_id.strip()

    # --- recorded_at ---
    now = _now_shanghai()
    recorded_at = raw.get("recorded_at")
    if recorded_at is None or recorded_at == "":
        recorded_at = _iso(now)
    elif not isinstance(recorded_at, str):
        raise FeedbackError(
            "recorded_at must be an ISO8601 string",
            flags={"labels": ["【缺项】recorded_at"]},
        )

    # --- outcome.made_connection ---
    outcome_in = raw.get("outcome")
    outcome: dict[str, Any] = {}
    if isinstance(outcome_in, dict):
        outcome = dict(outcome_in)
        mc = outcome.get("made_connection", _MISSING)
        if mc is _MISSING:
            labels.append("【缺项】outcome.made_connection")
            flag_bits["outcome_unknown"] = True
            labels.append("【缺项】outcome_unknown")
        elif mc is None:
            labels.append("【缺项】outcome.made_connection")
            flag_bits["outcome_unknown"] = True
            labels.append("【缺项】outcome_unknown")
            outcome["made_connection"] = None
        elif not isinstance(mc, bool):
            if isinstance(mc, str) and mc.lower() in ("true", "false"):
                outcome["made_connection"] = mc.lower() == "true"
            else:
                labels.append("【缺项】outcome.made_connection")
                flag_bits["outcome_unknown"] = True
                labels.append("【缺项】outcome_unknown")
        if "outcome_note" in outcome and isinstance(outcome["outcome_note"], str):
            outcome["outcome_note"] = outcome["outcome_note"][:OPERATOR_NOTE_MAX]
    else:
        labels.append("【缺项】outcome.made_connection")
        flag_bits["outcome_unknown"] = True
        labels.append("【缺项】outcome_unknown")
        if outcome_in is not None and not isinstance(outcome_in, dict):
            labels.append("【缺项】outcome")

    # --- actions_taken (CRITICAL enrichment) ---
    actions_in = raw.get("actions_taken")
    actions_out: list[dict[str, Any]] = []
    if actions_in is None:
        labels.append("【缺项】actions_taken")
    elif not isinstance(actions_in, list):
        labels.append("【缺项】actions_taken")
    elif len(actions_in) == 0:
        labels.append("【缺项】actions_taken")
    else:
        for item in actions_in:
            if not isinstance(item, dict):
                continue
            actions_out.append(normalize_action_item(item, labels, flag_bits))
        labels.append(ENUM_ALIGN_FLAG)

    # --- timestamps ---
    labels.append(TIMESTAMP_CLOCK_FLAG)
    ts_in = raw.get("timestamps")
    timestamps: dict[str, Any] = {}
    if not isinstance(ts_in, dict):
        for k in TIMESTAMP_KEYS:
            labels.append(f"【缺项】timestamps.{k}")
            timestamps[k] = None
    else:
        timestamps = dict(ts_in)
        for k in TIMESTAMP_KEYS:
            if k not in timestamps or timestamps[k] is None:
                labels.append(f"【缺项】timestamps.{k}")
                if k not in timestamps:
                    timestamps[k] = None

    # --- pax_key ---
    pax_key = raw.get("pax_key")
    if pax_key is None or pax_key == "":
        labels.append("【缺项】pax_key")
        pax_key = None
    else:
        if not isinstance(pax_key, str) or not PAX_KEY_RE.fullmatch(pax_key):
            raise FeedbackError(
                "pax_key must match ^[A-Za-z0-9._:-]{1,64}$",
                flags={"labels": ["【缺项】pax_key 格式非法"]},
            )

    # --- estimate_echo ---
    estimate_echo = raw.get("estimate_echo")
    if estimate_echo is None:
        labels.append("【缺项】estimate_echo")
    elif not isinstance(estimate_echo, dict):
        labels.append("【缺项】estimate_echo")
        estimate_echo = None

    # --- source / operator_note ---
    source = raw.get("source") or "occ_demo_ui"
    if not isinstance(source, str):
        source = "occ_demo_ui"
    operator_note = raw.get("operator_note")
    if isinstance(operator_note, str):
        operator_note = operator_note[:OPERATOR_NOTE_MAX]
    elif operator_note is not None:
        operator_note = str(operator_note)[:OPERATOR_NOTE_MAX]

    payload: dict[str, Any] = {
        "request_id": request_id,
        "recorded_at": recorded_at,
        "outcome": outcome,
        "actions_taken": actions_out,
        "timestamps": timestamps,
        "source": source,
    }
    if pax_key is not None:
        payload["pax_key"] = pax_key
    if estimate_echo is not None:
        payload["estimate_echo"] = estimate_echo
    if operator_note is not None:
        payload["operator_note"] = operator_note

    uniq_labels = _dedupe_labels(labels)
    flags_out: dict[str, Any] = {**flag_bits, "labels": uniq_labels}

    received_at = _iso(now)
    day = _date_str(now)
    fid = _feedback_id(now)
    rel = _relative_path(day)

    disk_line = {
        "feedback_id": fid,
        "schema_version": SCHEMA_VERSION,
        "received_at": received_at,
        "engine_version": ENGINE_VERSION,
        "contract_version": CONTRACT_VERSION,
        "payload": payload,
        "flags": flags_out,
    }

    abs_path = _absolute_path(day)
    with _write_lock:
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        with abs_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(disk_line, ensure_ascii=False) + "\n")
            f.flush()

    return {
        "ok": True,
        "feedback_id": fid,
        "request_id": request_id,
        "recorded_at": recorded_at,
        "path": rel,
        "flags": {"labels": uniq_labels, **{k: v for k, v in flag_bits.items()}},
    }


def export_feedback_day(date: str) -> str:
    """Return JSONL text for YYYY-MM-DD, or empty string if no file."""
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
        raise FeedbackError(
            "date must be YYYY-MM-DD",
            flags={"labels": ["【缺项】date"]},
        )
    path = _absolute_path(date)
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8")
