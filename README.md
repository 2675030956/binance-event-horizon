# 币安事件地平线

`Binance Event Horizon`

这不是一套普通的数据看板，也不是交易前检查器。

它是一套面向币安生态的「未来情景引擎」：把现货、合约、Alpha、Web3 社媒热度、聪明钱信号、Launchpad/迷因冲击、官方公告催化这些分散信号，折叠成一个可复用的事件驾驶舱。

它输出的不是单点行情，而是：

- 当前市场处在哪个相位
- 哪些资产正在进入“引力井”
- 哪些主题正在形成“点火窗口”
- 接下来 6 小时 / 24 小时最值得盯的情景是什么
- 可以直接给 OpenClaw 复用的 JSON、可演示的 HTML、可发布的广播封包

## 核心模块

- `event_horizon`：市场相位、信号密度、催化压力、杠杆温度
- `signal_constellation`：多源信号星图，按赛道分层而不是按单一接口堆表
- `scenario_engine`：未来 6h / 24h 场景卡，给出触发条件与失效条件
- `catalyst_reactor`：官方公告与产品动作映射成催化路径
- `gravity_alerts`：高杠杆、高拥挤、低流动性、审计风险等坍缩预警
- `orbit_watchlist`：优先观察轨道，适合 OpenClaw 或人工盯盘接力
- `focus_asset`：支持指定一个代币 / 交易对做单独深挖
- `broadcast_pack`：自动生成 X / 币安广场 / 直播讲解要点

## 数据编排

本项目默认使用公开可访问的 Binance 相关数据源：

- 币安现货产品公开接口
- Binance USDⓈ-M Futures 公共接口
- Binance Alpha 公开列表
- Binance Web3 社媒热度 / 统一排行 / 聪明钱 / 信号接口
- Binance 官方公告 CMS 接口

这些数据会被统一归并到一个结构化 JSON，供其他 OpenClaw 直接消费。

## 项目结构

```text
binance-event-horizon/
├─ agents/openai.yaml
├─ assets/report_template.html
├─ demo/
│  ├─ index.html
│  ├─ sample_report.json
│  └─ sample_report.md
├─ output/
│  ├─ latest_report.json
│  ├─ latest_report.md
│  └─ latest_report.html
├─ references/
│  ├─ data-sources.md
│  └─ product-logic.md
├─ scripts/binance_event_horizon.py
├─ submission/
├─ config.example.json
├─ requirements.txt
└─ SKILL.md
```

## 运行方式

先安装依赖：

```powershell
py -3 -m pip install -r requirements.txt
```

生成一份最新报告：

```powershell
py -3 scripts/binance_event_horizon.py `
  --config config.example.json `
  --json-output output/latest_report.json `
  --markdown-output output/latest_report.md `
  --html-output output/latest_report.html
```

生成一份演示版 demo：

```powershell
py -3 scripts/binance_event_horizon.py `
  --config config.example.json `
  --json-output demo/sample_report.json `
  --markdown-output demo/sample_report.md `
  --html-output demo/index.html
```

指定一个资产做聚焦分析：

```powershell
py -3 scripts/binance_event_horizon.py `
  --config config.example.json `
  --focus-symbol BTCUSDT `
  --json-output output/latest_report.json `
  --markdown-output output/latest_report.md `
  --html-output output/latest_report.html
```

也可以只传基础代码：

- `BTC`
- `BNB`
- `PEPE`
- `KAT`

脚本会优先尝试映射到 `USDT` 交易对，其次回退到链上 / Alpha 信号。

## 输出文件说明

- `JSON`：给其他 OpenClaw / 机器人 / 自动化流程复用
- `Markdown`：适合复制给用户、发群、做日报
- `HTML`：适合 GitHub Pages 演示、录屏、比赛提交

## GitHub 提交建议

建议把下列内容一并提交：

- `agents/`
- `assets/`
- `demo/`
- `references/`
- `scripts/`
- `submission/`
- `README.md`
- `SKILL.md`
- `config.example.json`
- `requirements.txt`

## 其他 OpenClaw 如何接入

如果你的仓库已经公开，其他 OpenClaw 可以直接用一句话安装：

```text
请从 GitHub 仓库 https://github.com/<你的用户名>/binance-event-horizon 安装这个 skill，并使用 $binance-event-horizon 生成最新事件地平线报告。
```

安装后常用提示词：

- `使用 $binance-event-horizon 生成最新币安事件地平线报告`
- `使用 $binance-event-horizon 聚焦分析 BTCUSDT`
- `使用 $binance-event-horizon 输出今天最值得关注的 3 个场景`
- `使用 $binance-event-horizon 生成适合发到币安广场的广播封包`

## 适合比赛的亮点

- 概念感强：不是报表堆砌，而是未来情景驾驶舱
- 复用性强：JSON 可直接被其他 OpenClaw 消费
- 演示效果强：深色赛博风 + 轨道可视化 + 固定视窗切换，不需要长滚动
- 技术逻辑完整：公告催化、Alpha 前沿、杠杆热区、聪明钱迁跃、Launchpad 迷因冲击被统一到同一套评分和场景系统
