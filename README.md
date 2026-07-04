# SCCO Monitor · 相关性系数

监控 SCCO（南方铜业）相对铜价的**相关性系数**，自动生成信号区间与 K 线图表。
阈值与公式参数均可通过环境变量配置。

---

## 快速开始

```bash
pip install -r requirements.txt
python main.py
```

查看 `data/history.csv`（数据）和 `docs/index.html`（图表）。

---

## 核心指标

**相关性系数 = SCCO 实际市值 / 铜价锚定市值**

| 区间 | 系数范围 | 含义 |
|------|----------|------|
| 🟢 安全 | ≤ `THRESHOLD_SAFE` (1.08) | 相对铜价低估 |
| 🟡 关注 | `THRESHOLD_SAFE` ~ `THRESHOLD_WATCH` (1.18) | 合理区间 |
| 🟠 偏热 | `THRESHOLD_WATCH` ~ `THRESHOLD_HOT` (1.28) | 估值偏高 |
| 🔴 过热 | ≥ `THRESHOLD_HOT` (1.28) | 显著高估 |

---

## 非交易日兜底

系统在非交易日（周末/节假日）自动降级运行：

- `fetch_market_data()` 返回 `None`，使用 CSV 中最后一条已知行情
- 不写入新的 CSV 行，避免重复
- HTML 照常生成，通知中标注 `[Offline]`
- 首次运行且非交易日时直接退出，避免空报告

---

## 输出

| 文件 | 说明 |
|------|------|
| `data/history.csv` | 日线 OHLCV + 相关性系数 + 参考价（按日 upsert） |
| `data/intraday.csv` | 日内 15min 数据（追加） |
| `docs/index.html` | Plotly 监控面板（GitHub Pages） |

---

## GitHub Actions 部署

### 1. Fork → Settings → Pages → Source: **GitHub Actions**

### 2. 环境变量

**Variables:**
- `THRESHOLD_SAFE` — 安全区间上限（默认 1.08）
- `THRESHOLD_WATCH` — 关注区间上限（默认 1.18）
- `THRESHOLD_HOT` — 偏热区间上限（默认 1.28）
- `ANCHOR_COPPER_BASE` — 锚定铜价基准（默认 4.2）
- `ANCHOR_MCAP_FACTOR` — 锚定市值因子 / 亿（默认 900）

**Secrets:** `FEISHU_WEBHOOK` / `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID`

### 3. 触发

- **自动**: 美股交易日 UTC 14:00–20:30（每 15min）
- **手动**: Actions → SCCO Monitor → Run workflow

### 4. 访问

`https://<用户名>.github.io/SCCO-Monitor/`

---

## 本地开发

```bash
pip install -r requirements.txt
python main.py
pip install pytest && python -m pytest tests/ -v
```

---

## 项目结构

```
main.py                 # 入口
scco_monitor/
├── __init__.py         # 包信息
├── config.py           # 全局配置（阈值 / 路径 / 环境变量）
├── fetcher.py          # 数据采集（yfinance 日线 + 15min 日内）
├── core.py             # 相关性系数计算 + 信号判定
├── storage.py          # CSV 读写（日线 upsert + 日内追加）
├── backtest.py         # 系数区间转换记录
├── notifier.py         # 飞书 / Telegram 推送
├── chart.py            # Plotly 图表 + HTML 渲染
└── template.html       # HTML 模板
data/                   # CSV 数据存储
docs/                   # 静态 HTML 页面
tests/                  # 测试用例
```

---

## 设计原则

- **纯系数参考** — 无持仓、无成本、无交易建议
- **可配置阈值** — 所有阈值从环境变量读取，空值自动回退默认值
- **零冗余依赖** — 仅 yfinance / requests / pandas
- **CSV 即数据仓库** — 零运维成本
- **非交易日兜底** — 周末/节假日自动使用最后已知数据
