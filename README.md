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
- **中转成功几率约为 xx%，未校准，非承诺。**
- **推荐不等于派单，不自动改签。**

## 访问

- `/` → 跳转到 `/min-loop.html`
- `/index.html` 演示页
- `POST /v1/mct/estimate`、`POST /v1/mct/feedback` 接口（与页面同源）

## 说明

- 反馈写入容器内临时目录（默认 `/tmp/mct-feedback`），容器重启后清空。
- 页面样式通过 CDN 加载 Tailwind，需要联网。
