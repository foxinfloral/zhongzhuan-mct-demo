# 演示怎么点

- 范围：estimate 为 io_v0.2；决策层为 v0.3 设计稿，**未实现**
- 成熟度：演示可跑 · **非投产**

---

## 开场三句（建议照念）

1. 「这是最小闭环演示：测算数字可当场对表复核，不是投产系统。」
2. 「几率只说『约为 xx%、未校准、非正式承诺』；缺项和未人工确认都标在脸上，不装成已定。」
3. 「回灌只落盘给人事后看，不会自动改公式、不会自动派单。」

---

## 1. URL

| 用途 | 地址 |
|---|---|
| **汇报主页** | `https://zhongzhuan-mct-demo.onrender.com/min-loop.html` |
| API | `https://zhongzhuan-mct-demo.onrender.com`（estimate 默认 **v0.2** + feedback） |
| 对照页（勿当唯一汇报页） | `https://zhongzhuan-mct-demo.onrender.com/index.html` |

```bash
curl -s https://zhongzhuan-mct-demo.onrender.com/v1/health
# 期望：ok:true · contract_version:io_v0.2 · feedback_enabled:true
```

---

## 2. 默认场景怎么点

1. 打开 **min-loop.html**。页面**不会自动测算**，10 项输入都是必填，未填完不出结果。
2. 二选一：手动填完 10 项（默认场景为 E-D / 否 / 否 / 远机位 / 窄体 / 后舱 / 中 / 外籍 / window_min=55 / hybrid_t3），或点 **「填入演示默认场景」**。这个按钮只填值，不会出结果。
3. 再点 **「测算」**，结果才出来。
4. 金标（可复核）：hybrid **P50/P90/P95 = 74.4 / 94.22 / 99.87 · 极高风险**。决策层（前端 v0.3 设计稿，尚未实现）显示推荐 `dedicated_assist`，成功几率约 37%（未校准代理）（**约为 / 未校准 / 非正式承诺**；推荐≠派单；S1=20【未确认】）。

讲法：不要说「打开就有结果」，要说「先填写（或一键填入演示场景），再测算」。

```bash
curl -s https://zhongzhuan-mct-demo.onrender.com/v1/mct/estimate -H 'content-type: application/json' \
  -d '{"flow":"E-D","through":"否","carry_on_only":"否","stand":"远机位","ac_type":"窄体","seat_zone":"后舱","period":"中","nation":"外籍","window_min":55,"mode":"hybrid_t3","request_id":"report-demo"}'
```

---

## 3. 点哪看什么

| 看什么 | 点/看哪里 | 防挑刺 |
|---|---|---|
| **几率** | 成功概率 / 旅客视图 · 「约为 xx%」 | 同框：**约 / 未校准 / 非正式承诺**；禁「保证赶上」 |
| **余量** | `slack_min`（window−p50）；旁有 p90/p95 余量 | 窗55 → 约 −19.4 |
| **梯队** | `action_ladder` 五档列表 + 推荐高亮 | **推荐≠派单**；S1=20 仅草案【未确认】 |
| **回灌** | 右侧 feedback 面板 · 同 `request_id` 提交 | 只写 JSONL；不改引擎 |

未人工确认（超时 A/B/C、S1 正式值、rush 单列、L5/L2）：只标【未确认】；**禁止**超时自动升 `pre_rebook`。

---
