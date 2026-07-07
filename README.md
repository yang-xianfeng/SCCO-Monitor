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

- **自动**: 美股交易日（Mon-Fri 9:30-16:00 ET）
  - 开盘密集 **5 min**：覆盖首 2.5h
  - 盘中常规 **15 min**
  - 收盘密集 **5 min**：覆盖最后 1h+
  - *非交易日自动兜底，不报错*
- **手动**: Actions → SCCO Monitor → Run workflow

> **时区说明：** GitHub Actions cron 运行在 UTC，不支持 DST 自动切换。
> 夏令时 (EDT=UTC-4) 与冬令时 (EST=UTC-5) 下 ET 对应时间如下：
>
> | cron (UTC) | 夏令时 EDT | 冬令时 EST | 说明 |
> |---|---|---|---|
> | `30-55/5 13` | 9:30-9:55 | 8:30-8:55 | 开盘首 25min |
> | `*/5 14-15` | 10:00-11:55 | 9:00-10:55 | 开盘第 1-2.5h |
> | `*/15 16-18` | 12:00-14:55 | 11:00-13:55 | 盘中 |
> | `*/5 19-20` | 15:00-16:55 | 14:00-15:55 | 收盘最后 1h+ |

### 4. 失败通知

Workflow 运行失败时，默认会发送通知邮件到 GitHub 账号绑定邮箱。
如需关闭：**GitHub Settings → Notifications → Actions** 取消勾选。

### 5. 访问

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
├── models.py           # 数据模型（TypedDict + 信号枚举）
├── fetcher.py          # 数据采集（yfinance 日线 + 15min 日内）
├── core.py             # 相关性系数计算 + 信号判定
├── storage.py          # CSV 读写（日线 upsert + 日内追加）
├── zone.py             # 系数区间转换记录
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
