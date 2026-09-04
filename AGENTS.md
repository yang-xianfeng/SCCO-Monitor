# AGENTS.md — AI Agent Guide

## Project Identity

**SCCO Monitor** — 相关性系数监控面板。
计算 SCCO（南方铜业）市值与铜价锚定市值之间的比率，
衡量估值偏离度（纯系数参考，无持仓、无成本、无交易建议）。

公式：`相关性系数 = SCCO实际市值 / 铜价锚定市值`
其中 `铜价锚定市值 = (当前铜价 / 4.2) × 900 × 1e8`

## Commands

```bash
python main.py                        # 本地运行（需要 yfinance 数据）
python -m pytest tests/ -v            # 34 测试，无需配置文件
```

## Architecture

```
main.py  ← 入口，编排流程
  │
  ├─ fetcher.py    yfinance → MarketData / IntradayBar / None
  ├─ core.py       calculate_ratio() → RatioResult + get_signal()
  ├─ storage.py    CSV 读写（日线 upsert + 日内 append）
  ├─ chart.py      Plotly JSON → template.html → docs/index.html
  ├─ notifier.py   飞书 / Telegram 推送（可选）
  └─ zone.py       区间转换历史扫描
```

### Data Flow

```
yfinance (HG=F, SCCO)
  │
  ├─ fetch_market_data() → MarketData (or None on holiday)
  │     │
  │     ├─ calculate_ratio() → ratio + 阈值参考价
  │     ├─ append_csv() → data/history.csv（按日 upsert）
  │     └─ 传入 build_html()
  │
  ├─ fetch_intraday_data() → list[IntradayBar]（仅当日 K 线）
  │     └─ 传入 build_html()
  │
  └─ fetch_daily_data() → list[MarketData]（回填历史，仅首次）
        └─ append_csv() → data/history.csv

build_html(daily, intraday, cur_data, ratio)
  ├─ build_chart_json() → Plotly candlestick + threshold lines
  ├─ build_history_chart_json() → Plotly 3-line history
  ├─ 模板填充 → 双时区 (ET / 北京时间)
  └─ docs/index.html
```

## Key Rules

### Date / Time
- `fetch_market_data()`: 用 `copper_hist.index[-1]`（yfinance 数据日期），非 `datetime.now()`
- `build_html()`: header 显示 `数据 {slot} ET · 更新 {deploy} ET / {北京时间} 北京时间`；K 线 badge 显示最后一条 bar 的 ET 时间
- `_get_display_label()`: 有 intraday 时解析 `intraday[-1]["datetime"]`；无 intraday 时回退 `cur_data["date"]` → `daily[-1]["date"]` → `datetime.now()`

### Non-trading Day
- `fetch_market_data()` 返回 `None` → `main.py` 用最后 CSV 行，不写新数据
- 通知标记 `[Offline]`
- 首次运行且非交易日 → 直接退出，无空报告

### Schedule (scheduler.py)
- 严格遵循 `_SCHEDULE_ET` 时间表，覆盖美股交易日全时段（开盘前 09:00-09:25，密集I 09:30-12:30，过渡 12:45-15:15，密集II 15:30-16:00）
- **状态感知与幂等性**：`data/.last_slot` 记录今日最新部署槽位；已完成槽位跳过，未完成槽位立即执行
- **容忍延迟与追赶**：GitHub cron 启动延迟会自动匹配当前应执行的最新槽位，永不漏跑
- **纽交所假期检测**：内置 `_NYSE_HOLIDAYS` 假日表，节假日自动跳过

### Git SOP（每次功能修改后必须执行）

```bash
git add -A && git commit -m "scope: concise description" && git pull --rebase && git push
```

1. `git status` 确认只改预期文件
2. 一条命令内完成 stage → commit → rebase pull → push
3. rebase 冲突则解决后继续，无需来回交互

## Workflow (.github/workflows/run.yml)

- **cron 永远 UTC**，与 GitHub 账号地区无关
- **cron**: `*/5 13-21 * * 1-5`（覆盖 EDT/EST 有效交易时段，每 5 分钟触发）
- **调度**: `scheduler.py` 的 `check_schedule()` 状态感知当前槽位是否已部署
- **Retry**: 遇到异常或数据源延迟时，重试 8 次（至少 6-8 次），间隔 10 秒，直到成功部署
- **Concurrency**: `cancel-in-progress: false`，排队部署，避免新 cron 意外中断正在部署的任务
- **Deploy**: `data/` `docs/` 先 `git-auto-commit`（`[skip ci]`）→ `configure-pages` + `upload-pages-artifact` + `deploy-pages`
- **push / workflow_dispatch**: 触发 `FORCE_RUN=1`，强制立即获取最新行情并部署
- **Cleanup**: 每次运行后保留最近 50 条 workflow runs

### ET → 北京时间换算（以 EDT 夏令时为例）

| UTC | EDT | 北京时间 |
|-----|-----|---------|
| 13:30 | 09:30 开盘 | 21:30 |
| 20:55 | 16:55 收盘 | 04:55+1 |

EDT(夏令) = UTC-4，北京 = UTC+8 → 差 12h
EST(冬令) = UTC-5，北京 = UTC+8 → 差 13h

## Config Rules

所有硬编码值必须去 `config.py`，包括：
- tickers (`HG=F`, `SCCO`)
- 时区 (`America/New_York`, `Asia/Shanghai`)
- API bases, 阈值, 锚定参数, timeout, plotly 版本, CSV 路径, 天数

## v3.0 Changelog

- 纯系数参考（移除 `USER_COST`、持仓建议、回测）
- 阈值 1.08/1.18/1.28（环境变量配置）
- 单职责模块重构
- 双时区显示
- 非交易日兜底

## v1.0 Refactor

- `models.py` — TypedDict models + Signal enum
- `backtest.py` → `zone.py`
- 全模块类型标注
- CSV→数值转换移入 `storage.py:row_to_numeric`
