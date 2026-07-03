# SCCO Monitor · Cola 铜价系数模型

监控 SCCO（南方铜业）相对铜价的杠杆率系数，自动生成 K 线图表与交易信号。

## 快速开始

```bash
pip install -r requirements.txt
python main.py
```

首次运行后查看 `data/history.csv` 和 `docs/index.html`。

## 原理

Cola 铜价系数 = 实际市值 / 锚定市值

| 系数区间 | 信号 | 操作建议 |
|----------|------|----------|
| ≤ 1.10 | 🟢 安全 | 逢低分批买入 |
| 1.10 ~ 1.20 | 🟡 合理 | 持有观望 |
| 1.20 ~ 1.50 | 🟠 偏热 | 停止加仓 |
| ≥ 1.50 | 🔴 减仓 | 分批减仓 |

锚定市值反映"当前铜价下 SCCO 应有的合理市值"，实际市值是市场给的估值，两者比值衡量偏离度。

## 输出

| 文件 | 说明 |
|------|------|
| `data/history.csv` | 每日 OHLCV + 系数 + 参考价，可直接用于回测 |
| `docs/index.html` | Plotly K 线图 + P₁.₁₀/P₁.₂₀/P₁.₅₀ 参考线，GitHub Pages 查看 |

## GitHub Actions 部署（完整指南）

### 1. 首次配置

Fork 或 clone 此仓库后，需要完成以下 GitHub 侧配置：

#### A. GitHub Pages 设置

1. 进入仓库 **Settings → Pages**
2. **Source**: 选择 **GitHub Actions**
3. 无需额外配置 — 工作流会自动构建并部署

> ⚠️ 不要选择 "Deploy from a branch" — 本项目使用 Actions 部署方式，工作流中已包含完整的 Pages 部署步骤。选择 branch 方式会导致 404。

#### B. 环境变量（可选）

| 变量 | 类型 | 位置 | 说明 |
|------|------|------|------|
| `USER_COST` | Variables | Settings → Secrets and variables → Actions | 持仓成本价，用于计算浮亏百分比 |
| `FEISHU_WEBHOOK` | Secrets | 同上 (Secrets) | 飞书机器人 Webhook URL |
| `TELEGRAM_BOT_TOKEN` | Secrets | 同上 (Secrets) | Telegram Bot Token |
| `TELEGRAM_CHAT_ID` | Secrets | 同上 (Secrets) | Telegram Chat ID |

通知渠道均为可选，不配则静默运行，仅更新图表。

### 2. 触发方式

- **自动**: 每个美股交易日 UTC 14:00（开盘后）和 UTC 20:30（收盘后）各运行一次
- **手动**: 在 Actions 页面点击 **Run workflow** → `workflow_dispatch`

### 3. 部署流程（工作流说明）

每次运行，GitHub Actions 自动执行：

```
checkout → pip install → python main.py → upload docs/ → deploy Pages → git commit
```

1. `python main.py` — 采集数据、计算系数、更新 CSV、生成 HTML
2. `actions/configure-pages` — 配置 Pages 环境
3. `actions/upload-pages-artifact` — 将 `docs/` 目录上传为 Pages 构建产物
4. `actions/deploy-pages` — 部署到 GitHub Pages
5. `git-auto-commit-action` — 将 `data/` 和 `docs/` 提交回仓库（保留历史记录）

### 4. 验证部署

1. 工作流运行成功后，在 Actions 页面确认 ✅ 绿色勾
2. 进入 **Settings → Pages**，查看 "Active deployment" 信息
3. 访问 `https://yang-xianfeng.github.io/scco-monitor/`（替换为你的 GitHub 用户名）

> 首次部署后可能需要等待 1-2 分钟 DNS 生效。如果仍显示 404，请检查：
> - ✅ Pages Source 是否为 **GitHub Actions**（而非 "Deploy from a branch"）
> - ✅ 工作流是否运行成功（绿色勾）
> - ✅ `docs/index.html` 是否已在仓库中存在（非空文件）
> - ✅ `docs/.nojekyll` 是否存在（防止 Jekyll 处理问题）

### 5. 本地测试

```bash
# 安装依赖
pip install -r requirements.txt

# 单次运行（生成 CSV + HTML）
python main.py

# 运行测试
pip install pytest pytest-mock
python -m pytest tests/ -v
```

## 项目结构

```
scco-monitor/
├── .github/workflows/run.yml   # GitHub Actions 部署流水线
├── data/
│   ├── .gitkeep
│   └── history.csv              # 日频 OHLCV + Cola 系数（同日期覆盖）
├── docs/
│   ├── .nojekyll                # 禁用 Jekyll，必须保留
│   ├── .gitkeep
│   └── index.html               # Plotly 图表（工作流自动生成）
├── tests/
│   └── test_main.py             # 39 个测试
├── .env.example                 # 本地环境变量模板
├── .gitignore
├── AGENTS.md                    # Cursor/opencode 代理说明
├── main.py                      # 单文件核心逻辑（~300 行）
├── requirements.txt
└── README.md
```

## 测试

```bash
pip install pytest pytest-mock
python -m pytest tests/ -v
```

## 设计原则

- **单文件优先** — 整个逻辑在 `main.py`，无包/框架/数据库
- **CSV 即数据仓库** — 不引入数据库，CSV 可直接导入回测
- **无技术分析指标** — Cola 系数本身就是策略，MACD/RSI 等不增加价值
- **通知非必需** — 不配置 Webhook 则只更新图表，零干扰
- **Pages as a Service** — 静态 HTML 通过 GitHub Pages 托管，零服务器成本

## 参考设计文档

原始需求文档 [`项目开发初始需求文档（需进一步更改）.md`](项目开发初始需求文档（需进一步更改）.md) 保留了完整策略背景与远期扩展思路。
