---
name: binance-event-horizon
description: Generate a futuristic Binance Event Horizon report that fuses spot, futures, Alpha, Web3 social hype, smart money signals, launchpad meme flows, and official Binance announcements into scenario cards, catalyst lanes, gravity alerts, orbit watchlists, and reusable broadcast packs. Use this skill when users ask for a multi-source Binance opportunity map, forward-looking market scenarios, catalyst tracking, leverage heat, Alpha early signals, meme launch attention, or a focused Event Horizon analysis on a single token or trading pair.
---

# 币安事件地平线

## 用途

这套 skill 不做“下单执行”，而是做“未来情景推演”。

当用户需要下面这些能力时，应该使用它：

- 把币安生态多个公开信号整合成一份高概念的市场驾驶舱
- 识别当前最强的官方催化、杠杆热区、聪明钱迁跃和 Alpha 前沿
- 输出未来 6 小时 / 24 小时的高优先级场景
- 给某个代币或交易对做聚焦分析
- 直接生成适合演示、发帖、做复盘的内容封包

## 核心工作流

1. 运行 `scripts/binance_event_horizon.py`
2. 优先读取生成后的 `JSON`
3. `Markdown` 和 `HTML` 只负责展示，不要把它们当作唯一事实源
4. 如果部分接口失败，保留其他模块，明确在 `warnings` 中暴露缺失

## 推荐命令

生成最新报告：

```powershell
py -3 scripts/binance_event_horizon.py `
  --config config.example.json `
  --json-output output/latest_report.json `
  --markdown-output output/latest_report.md `
  --html-output output/latest_report.html
```

生成 demo：

```powershell
py -3 scripts/binance_event_horizon.py `
  --config config.example.json `
  --json-output demo/sample_report.json `
  --markdown-output demo/sample_report.md `
  --html-output demo/index.html
```

聚焦单个资产：

```powershell
py -3 scripts/binance_event_horizon.py `
  --config config.example.json `
  --focus-symbol BTCUSDT `
  --json-output output/latest_report.json `
  --markdown-output output/latest_report.md `
  --html-output output/latest_report.html
```

## 复用规则

- 其他 Agent / OpenClaw 优先消费 `JSON`
- 不要重新手工拼接多源数据，除非用户明确要求原始接口级别的排查
- 用户要“最新”“刚刚”“今天”的内容时，优先重新生成报告
- 用户点名单个代币时，优先使用 `--focus-symbol`
- 如果没有聚焦资产，默认把当前最高优先级轨道作为 `focus_asset`

## 行为约束

- 这套 skill 的价值是“多源折叠后的情景判断”，不是单接口排行榜转述
- 遇到高波动、高杠杆、低流动性或审计风险时，要在 `gravity_alerts` 明确提示
- 公告和催化路径要保留标题、时间和链接
- 对匿名迷因 / 低流动性代币，不要把高热度直接等同于高质量机会

## 附带资源

### `scripts/`

- `binance_event_horizon.py`：主生成脚本，负责抓取多源数据并生成 JSON / Markdown / HTML

### `references/`

- `product-logic.md`：产品结构、评分逻辑、相位规则、场景生成逻辑
- `data-sources.md`：本项目使用的主要公开接口与字段说明

### `assets/`

- `report_template.html`：演示页面模板，深色赛博驾驶舱风格
