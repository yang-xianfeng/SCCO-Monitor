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
- **精确匹配**：`total == slot_total`，无 ± 偏差
- 仅允许 GitHub Actions 启动延迟，由重试循环覆盖
- 交易日 Mon-Fri 09:30-16:00 ET
- 首个槽位 09:00 ET，全部槽位见 `scheduler.py`

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
- **调度**: `scheduler.py` 的 `check_schedule()` 匹配 `[槽位, 槽位+BUFFER]` 窗口，`BUFFER=4`（`config.SCHEDULE_BUFFER_MINUTES`），吸收 GitHub cron 启动延迟
- **Retry**: cron 周期内 5 分钟时间预算持续重试 main.py，非槽位/异常均继续尝试；未命中则退出（不报失败）
- **Deploy**: `data/` `docs/` 先 `git-auto-commit`（`[skip ci]`）→ `configure-pages` + `upload-pages-artifact` + `deploy-pages`
- **push / workflow_dispatch**: 直接部署仓库现有 `docs/`（数据已提交的场景）
- **Cleanup**: 每次运行后保留最近 50 条 workflow runs

### 时间触发约束（不可违反）

1. **绝不修改时间槽** `scco_monitor/scheduler.py::_SCHEDULE_ET`（这是唯一权威调度依据）
2. **严格按时间表执行，每个小时至少执行一次**（槽位覆盖 9:00-16:55，每小时都有槽位）
3. **少发失败邮件，多多尝试部署**：cron 周期内靠 BUFFER + 持续重试提高命中率；未命中槽位一律 `exit 0` 不触发失败邮件

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
