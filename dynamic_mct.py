#!/usr/bin/env python3
"""智中转 2.0 · 动态 MCT 测算器（点估计版）复现。
只实现 Excel 表内公式，不发明 Log-Normal σ，不补包外数字。
"""
from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from typing import Literal

Flow = Literal["E-C", "E-D"]
YesNo = Literal["是", "否"]
Stand = Literal["近机位", "远机位", "远远机位"]
AcType = Literal["窄体", "宽体"]
SeatZone = Literal["前舱", "中舱", "后舱"]
Period = Literal["早", "中", "晚", "凌晨"]
Nation = Literal["国内", "外籍"]


@dataclass(frozen=True)
class Inputs:
    flow: Flow = "E-D"
    through: YesNo = "否"
    carry_on_only: YesNo = "否"  # 免提
    stand: Stand = "远机位"
    ac_type: AcType = "窄体"
    seat_zone: SeatZone = "后舱"
    period: Period = "中"
    nation: Nation = "外籍"
    window_min: float = 55.0


@dataclass(frozen=True)
class Node:
    name: str
    included: int  # 0/1
    p50: float
    p90: float
    source: str


def pace_coef(period: Period) -> float:
    # B14: =IF(OR(B11="早",B11="中"),1,IF(B11="晚",1.09,1.33))
    if period in ("早", "中"):
        return 1.0
    if period == "晚":
        return 1.09
    return 1.33  # 凌晨


def deplane_p50(ac_type: AcType, seat_zone: SeatZone) -> float:
    # C19=IF(窄体, IF(前舱,3,IF(中舱,7,12)), IF(前舱,5,IF(中舱,8,13)))
    if ac_type == "窄体":
        return {"前舱": 3, "中舱": 7, "后舱": 12}[seat_zone]
    return {"前舱": 5, "中舱": 8, "后舱": 13}[seat_zone]


def nodes(inp: Inputs) -> list[Node]:
    b14 = pace_coef(inp.period)

    taxi = Node("滑行入位", 1, 3, 4, "平台预入位")

    c19 = deplane_p50(inp.ac_type, inp.seat_zone)
    deplane = Node("座位区域下机", 1, c19, round(c19 * 1.5, 0), "附件3")

    if inp.stand == "近机位":
        bus_inc, bus_p50, bus_p90 = 0, 0.0, 0.0
    elif inp.stand == "远机位":
        bus_inc, bus_p50, bus_p90 = 1, 6.0, 9.0
    else:  # 远远机位
        bus_inc, bus_p50, bus_p90 = 1, 13.0, 18.0
    bus = Node("远机位摆渡", bus_inc, bus_p50, bus_p90, "附件4")

    if inp.nation == "外籍":
        imm_p50, imm_p90 = 5.0, 15.0
    else:
        imm_p50, imm_p90 = 2.5, 6.0
    imm = Node("进港边防", 1, imm_p50, imm_p90, "附件2")

    customs = Node("海关", 1, 2, 5, "附件2")

    bag_inc = 1 if inp.carry_on_only == "否" else 0
    bag = Node("提取行李", bag_inc, 10, 22, "平台行李 (非免提)")

    proc_inc = 1 if (inp.through == "否" and inp.carry_on_only == "否") else 0
    proc = Node("I-D办理手续", proc_inc, 10, 25, "附件2 (非通程)")

    walk_base = 9 if inp.flow == "E-D" else 6
    walk_p50 = float(round(walk_base * b14, 0))
    walk = Node("楼内步行", 1, walk_p50, walk_p50 + 4, "附件1 距离÷步速")

    apm_p50 = 8.0 if inp.flow == "E-D" else 6.0
    apm = Node("捷运及固定段", 1, apm_p50, apm_p50 + 2, "测算器")

    if inp.period in ("早", "中"):
        sec_p50, sec_p90 = 7.0, 16.0
    elif inp.period == "晚":
        sec_p50, sec_p90 = 5.0, 11.0
    else:
        sec_p50, sec_p90 = 4.0, 10.0
    sec = Node("国内安检", 1, sec_p50, sec_p90, "附件2")

    return [taxi, deplane, bus, imm, customs, bag, proc, walk, apm, sec]


def risk_and_action(window: float, p50: float, p90: float, p95: float) -> tuple[str, str]:
    if window >= p95:
        return "低风险", "正常衔接，观察"
    if window >= p90:
        return "可控风险", "进入预警池，准备触达"
    if window >= p50:
        return "高风险", "飞行中预警 + 落地前方案确认"
    return "极高风险", "预改签 / 急转 / 专人保障"


def compute(inp: Inputs) -> dict:
    ns = nodes(inp)
    included = [n for n in ns if n.included == 1]
    c28 = sum(n.p50 for n in included)  # SUMPRODUCT(计入, 节点P50)
    e28 = sum((n.p90 - n.p50) ** 2 for n in included)  # SUMPRODUCT(计入, (P90-P50)^2)
    p50 = c28
    p90 = c28 + sqrt(e28)
    p95 = c28 + 1.2852 * sqrt(e28)
    risk, action = risk_and_action(inp.window_min, p50, p90, p95)
    return {
        "inputs": inp,
        "pace_coef": pace_coef(inp.period),
        "nodes": ns,
        "C28": c28,
        "E28": e28,
        "P50": p50,
        "P90": p90,
        "P95": p95,
        "risk": risk,
        "action": action,
        "included_count": len(included),
    }


if __name__ == "__main__":
    r = compute(Inputs())
    print("P50", r["P50"])
    print("P90", r["P90"])
    print("P95", round(r["P95"], 2))
    print("E28", r["E28"])
    print("risk", r["risk"])
    print("action", r["action"])
    print("included", r["included_count"])
    for n in r["nodes"]:
        print(f"{n.name}\tinc={n.included}\tP50={n.p50}\tP90={n.p90}")
