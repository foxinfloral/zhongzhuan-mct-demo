---
title: 智·中转 演示
emoji: ✈️
colorFrom: blue
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
---

# 智·中转 演示

- **决策辅助演示，非正式生产。**
- **中转成功几率约为 N%（N 为演示估算值）（约 · 未校准 · quantile_anchor_proxy · 估算、非正式承诺），不能理解为保证赶上。**
- **推荐不等于派单，不自动改签。**

## 访问

- `/` → 跳转到 `/min-loop.html`
- `/index.html` 演示页
- `POST /v1/mct/estimate`、`POST /v1/mct/feedback` 接口（由本站演示服务提供）

## 说明

- 反馈写入容器内临时目录（默认 `/tmp/mct-feedback`），容器重启后清空。
- 页面样式通过 CDN 加载 Tailwind，需要联网。

## 估算接口输入字段（`POST /v1/mct/estimate`，io_v0.2）

取值以 `mct_service/normalize.py` 为准，严格匹配，不接受别名。字段缺省（缺失 / `null` / 空串）时使用默认值，HTTP 仍为 200，并在 `flags.defaults_applied` 列出字段名、`flags.labels` 追加「已用默认 字段=值」。

| 字段 | 允许值 | 默认 |
|---|---|---|
| `flow` | `E-C` / `E-D`（业务含义【未确认】） | `E-D` |
| `nation` | `国内` / `外籍` | `外籍` |
| `stand` | `近机位` / `远机位` / `远远机位` | `远机位` |
| `period` | `早` / `中` / `晚` / `凌晨` | `中` |
| `through` | `是` / `否` | `否` |
| `carry_on_only` | `是` / `否` | `否` |
| `ac_type` | `窄体` / `宽体` | `窄体` |
| `seat_zone` | `前舱` / `中舱` / `后舱` | `后舱` |
| `window_min` | 数字，> 0 | `55` |
| `mode` | `excel_default` / `hybrid_t3` | `hybrid_t3` |
| `request_id` | 可选字符串，原样回显；缺省时返回 `null`；不校验唯一性 | — |

其它取值返回 HTTP 400。

废弃键：`through_check`→`through`、`hand_baggage_free`→`carry_on_only`、`aircraft`→`ac_type` 目前仍会被映射（并带 `flags.deprecated_keys_used` 与【废弃】标签），新接入请勿使用；`passenger_type` 不做映射：未同时提供 `nation`+`seat_zone` 时返回 400，同时提供时被忽略。
