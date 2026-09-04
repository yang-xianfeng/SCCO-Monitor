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

### 1. Date / Timezone / DST (时区与冬夏令时规范)
- **为什么核心逻辑必须使用美东时间（ET, `America/New_York`）？**
  - 美股纽交所（NYSE）和纳斯达克（NASDAQ）的交易时间在当地是**绝对恒定**的：09:30 准时开盘，16:00 准时收盘。
  - 美股实行夏令时（EDT, UTC-4）与冬令时（EST, UTC-5）：
    - **夏令时（3月至11月）**：对应北京时间 21:30 - 次日 04:00；对应 UTC 13:30 - 20:00。
    - **冬令时（11月至次年3月）**：对应北京时间 22:30 - 次日 05:00；对应 UTC 14:30 - 21:00。
  - Python 标准库 `zoneinfo.ZoneInfo("America/New_York")` 自带 IANA 全球时制历史数据库，会自动随具体日期无缝切换 EDT/EST。
  - ⚠️ **AI 必须严格遵守**：所有业务调度与时间槽判定**必须统一使用 ET**，严禁擅自改用北京时间或 UTC（否则每年 3 月和 11 月冬夏令时切换时代码必须人工修改一次）。
- `fetch_market_data()`: 用 `copper_hist.index[-1]`（yfinance 数据日期），非 `datetime.now()`
- `build_html()`: header 显示 `数据 {slot} ET · 更新 {deploy} ET / {北京时间} 北京时间`；K 线 badge 显示最后一条 bar 的 ET 时间
- `_get_display_label()`: 有 intraday 时解析 `intraday[-1]["datetime"]`；无 intraday 时回退 `cur_data["date"]` → `daily[-1]["date"]` → `datetime.now()`

### 2. Schedule Table Design (`_SCHEDULE_ET` 调度表设计意图)
- ⚠️ **重要规范（故意为之）**：调度表 `_SCHEDULE_ET` 严格保留现有的**分段式时间槽显式元组定义**：
  - 盘前试盘：`09:00 - 09:25`（每 5 分钟）
  - 密集 I 早盘：`09:30 - 12:30`（每 5 分钟）
  - 过渡期午盘：`12:45 - 15:15`（每 15 分钟）
  - 密集 II 尾盘：`15:30 - 16:00`（每 5 分钟）
- **此结构为故意为之的设计意图**，便于精确对齐各盘中监控节奏。**后续任何 AI 严禁擅自合并、删减或改成数学步长函数**！
- **状态感知与幂等性**：`data/.last_slot` 记录今日最新部署槽位；已完成槽位跳过，未完成槽位立即执行
- **容忍延迟与追赶**：GitHub cron 启动延迟会自动匹配当前应执行的最新槽位，永不漏跑

### 3. Holidays & Non-trading Days (节假日与非交易日标准)
- **专业休市判定原则**：
  1. **周末必休**：`dt.weekday() >= 5` 直接跳过。
  2. **法定假日动态计算**：严禁使用易过期的静态年份字典；采用标准公历/复活节算法动态计算 10 个纽交所法定休市日及顺延法则。
  3. **数据源为最高权威**：遇到紧急停市或未知休市时，yfinance 数据源无当日数据返回 `cur_data is None`，触发本地非交易日安全兜底（使用上一日数据，不写入新数据，标记 `[Offline]`），杜绝抛错中断。

### 4. Deployment Speed & Performance (部署性能与依赖极简)
- **极速与健壮依赖管理**：CI 环境使用 GitHub 官方 `actions/setup-python@v5` 配合内置 `cache: 'pip'`，在保证 100% 权限健壮性的前提下实现秒级依赖复用，杜绝第三方 Action 权限或外部受管环境冲突报错。
- **快照式轻量行情**：`fetcher.py` 优先使用 `fast_info.shares` 获取股本（配合 `DEFAULT_SHARES` 兜底），严禁在高频盘中调用全量财务档案 `Ticker.info`，消除 3~8 秒慢请求及 429 限流风险。
- **高频链路解耦**：历史 Runs 清理任务剥离至独立的周常 workflow (`cleanup.yml`)，避免在每 5 分钟的主监控流程中浪费 20~30 秒。

### Git SOP（每次功能修改后必须执行）

```bash
git add -A && git commit -m "scope: concise description" && git pull --rebase && git push
```

1. `git status` 确认只改预期文件
2. 一条命令内完成 stage → commit → rebase pull → push
3. rebase 冲突则解决后继续，无需来回交互

## Workflow (.github/workflows/run.yml)

- **cron 永远 UTC**，与 GitHub 账号地区无关
- **cron**: `*/5 13-22 * * 1-5`（覆盖 EDT/EST 冬夏令时全时段及 GitHub 排队延迟）
- **调度**: `scheduler.py` 的 `check_schedule()` 状态感知当前槽位是否已部署
- **Retry**: 遇到异常或数据源延迟时，重试 8 次（至少 6-8 次），间隔 10 秒，直到成功部署
- **Concurrency**: `cancel-in-progress: false`，排队部署，避免新 cron 意外中断正在部署的任务
- **Deploy**: `data/` `docs/` 先 `git-auto-commit`（`[skip ci]`）→ `configure-pages` + `upload-pages-artifact` + `deploy-pages`
- **push / workflow_dispatch**: 触发 `FORCE_RUN=1`，强制立即获取最新行情并部署
- **Cleanup**: 独立的 `.github/workflows/cleanup.yml` 每周日清理保留最近 50 条

### ET → 北京时间换算（以 EDT 夏令时为例）

| UTC | EDT | 北京时间 |
|-----|-----|---------|
| 13:30 | 09:30 开盘 | 21:30 |
| 20:00 | 16:00 收盘 | 04:00+1 |

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
