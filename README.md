# SCCO Monitor · 相关性系数

> 🤖 AI 助手请先阅读 `AGENTS.md`

监控 SCCO（南方铜业）市值与铜价锚定市值之间的比率，衡量估值偏离度。

**纯系数参考** — 无持仓、无成本、无交易建议。

---

## 核心公式

```
相关性系数 = SCCO实际市值 / 铜价锚定市值
铜价锚定市值 = (当前铜价 / 4.2) × 900 × 1e8
SCCO实际市值 = SCCO股价 × 流通股数（~7.73亿股）
```

## 信号区间

| 信号 | 系数 | 含义 |
|------|------|------|
| 🟢 安全 | ≤ `THRESHOLD_SAFE` (1.08) | 相对铜价低估 |
| 🟡 关注 | ~ `THRESHOLD_WATCH` (1.18) | 合理区间 |
| 🟠 偏热 | ~ `THRESHOLD_HOT` (1.28) | 估值偏高 |
| 🔴 过热 | ≥ `THRESHOLD_HOT` (1.28) | 显著高估 |

## 架构

```
main.py → fetcher(yfinance) → core(计算) → chart(Plotly) → docs/index.html
                                        ↕
                                   storage(CSV)
                                   notifier(飞书/Telegram)
```

数据源：yfinance — `HG=F`（铜期货）、`SCCO`（南方铜业）

## 输出

| 文件 | 说明 | 策略 |
|------|------|------|
| `data/history.csv` | 日线 OHLCV + 系数 | 按日 upsert |
| `data/intraday.csv` | 日内 15min K 线 | 追加 |
| `docs/index.html` | Plotly 面板（GitHub Pages） | 每次重新生成 |

## 本地运行（必须使用虚拟环境）

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python main.py
python -m pytest tests/ -v
```

## GitHub Actions 部署

1. Fork → Settings → Pages → Source: **GitHub Actions**
2. 自动触发：美股交易日 Mon-Fri 09:00-16:00 ET

| 阶段 | 频率 | ET 时段 | 说明 |
|------|------|---------|------|
| 盘前 | 每 5min | 09:00-09:25 | 盘前监控 |
| 密集 I | 每 5min | 09:30-12:30 | 开盘与早盘活跃期 |
| 过渡 | 每 15min | 12:45-15:15 | 午间平稳期 |
| 密集 II | 每 5min | 15:30-16:00 | 尾盘与收盘确认 |

- 严格遵循 ET 时间槽调度（`_SCHEDULE_ET` 故意保留分段设计），未部署槽位自动重试 8 次直至成功
- 状态记录防止重复部署，cron 延迟自动追赶最新槽位
- 采用 `setup-uv` 极速安装环境，总流程耗时由数分钟压缩至 20~30 秒
- 成功后将数据自动提交回仓库并部署到 GitHub Pages
- 独立的周常任务自动清理旧记录（保留最近 50 条），不在高频主链路中耽搁
- cron 覆盖 UTC 13-22，全天候自适应 EDT/EST 夏冬令时与动态计算纽交所法定假日

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `THRESHOLD_SAFE` | 1.08 | 安全阈值 |
| `THRESHOLD_WATCH` | 1.18 | 关注阈值 |
| `THRESHOLD_HOT` | 1.28 | 偏热阈值 |
| `FEISHU_WEBHOOK` | — | 飞书推送（可选） |
| `TELEGRAM_BOT_TOKEN` | — | Telegram 推送（可选） |
| `TELEGRAM_CHAT_ID` | — | Telegram 聊天 ID |

## 非交易日

`fetch_market_data()` 返回 `None` 时自动降级：使用最后已知 CSV 行、不写新数据、通知标记 `[Offline]`。首次运行且非交易日则直接退出。

## 时区

GitHub Actions cron 跑在 UTC。页面右上角同时显示 **ET** 和 **北京时间**；K 线图显示 **ET** 本地时间。

| 概念 | 值 |
|------|-----|
| EDT（夏令，约 3-11 月） | UTC-4 |
| EST（冬令，约 11-3 月） | UTC-5 |
| 北京时间 | UTC+8 |

例：`09:30 EDT = 21:30 北京时间`，`16:00 EDT = 04:00+1 北京时间`

## 项目结构

```
main.py                 # 入口
scco_monitor/
├── config.py           # 全局配置
├── models.py           # 数据模型
├── fetcher.py          # yfinance 采集
├── core.py             # 系数计算 + 信号
├── storage.py          # CSV 读写
├── zone.py             # 区间扫描
├── notifier.py         # 推送
├── chart.py            # Plotly 渲染
└── template.html       # HTML 模板
data/                   # CSV 数据
docs/                   # 页面
tests/                  # 测试
```

## 设计原则

- **纯系数参考** — 无持仓、无成本、无交易建议
- **零冗余依赖** — 仅 yfinance / requests / pandas
- **CSV 即数据仓库** — 无需数据库
- **非交易日兜底** — 节假日自动降级
