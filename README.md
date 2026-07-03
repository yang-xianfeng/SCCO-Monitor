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

## GitHub Actions 部署

### 分步配置（按顺序执行）

#### 1. Fork 或 Clone 此仓库

```bash
git clone git@github.com:你的用户名/scco-monitor.git
cd scco-monitor
```

#### 2. 启用 GitHub Pages（最关键一步）

进入仓库 **Settings → Pages**：

- **Source**: 必须选择 **GitHub Actions**（见下图示意）
- 不要选择 "Deploy from a branch" — 选择 branch 会导致 404，因为本项目由工作流构建并部署

```
Settings → Pages → Source: [GitHub Actions]  ← 选这个
```

#### 3. 配置环境变量（可选，但请注意 USER_COST）

进入 **Settings → Secrets and variables → Actions**，分两类配置：

**Variables（变量）**：
| 变量名 | 说明 | 是否必填 |
|--------|------|----------|
| `USER_COST` | 你的 SCCO 持仓成本价（如 184.36） | 选填，不设则默认 184.36 |

> ⚠️ **USER_COST 陷阱**：如果设置了该变量但值为**空**，脚本会因 `float('')` 崩溃。要么不设此变量，要么设一个有效数值。代码已做保护，但建议不设或设有效值。

**Secrets（密钥）**：
| 变量名 | 说明 | 是否必填 |
|--------|------|----------|
| `FEISHU_WEBHOOK` | 飞书机器人 Webhook URL | 选填 |
| `TELEGRAM_BOT_TOKEN` | Telegram Bot Token | 选填 |
| `TELEGRAM_CHAT_ID` | Telegram Chat ID | 选填 |

通知渠道均为可选，不配则静默运行，仅更新图表。

#### 4. 触发工作流

- **手动触发**：进入 **Actions** 页面 → 左侧点 **SCCO Monitor** → 点 **Run workflow** → 绿色按钮
- **自动触发**：每个美股交易日 UTC 14:00（开盘后）和 UTC 20:30（收盘后）各运行一次

#### 5. 验证部署

工作流运行成功后（绿色勾 ✅）：

1. 进入 **Settings → Pages**，查看 **"Active deployment"** 信息，确认有最近部署记录
2. 访问 `https://你的用户名.github.io/scco-monitor/`（例如 `https://yang-xianfeng.github.io/scco-monitor/`）
3. 页面应显示 K 线图和数据卡片

### 工作流内部流程

每次运行，GitHub Actions 自动按序执行：

```
checkout → pip install → python main.py → configure-pages → upload docs/ → deploy-pages → git-auto-commit
```

| 步骤 | 动作 | 说明 |
|------|------|------|
| 1 | `actions/checkout` | 拉取仓库代码 |
| 2 | `pip install -r requirements.txt` | 安装 Python 依赖 |
| 3 | `python main.py` | 采集数据、计算系数、更新 CSV、生成 HTML |
| 4 | `actions/configure-pages` | 配置 Pages 环境（若未启用则自动启用） |
| 5 | `actions/upload-pages-artifact` | 将 `docs/` 目录上传为 Pages 构建产物 |
| 6 | `actions/deploy-pages` | 将产物部署到 GitHub Pages |
| 7 | `git-auto-commit-action` | 将更新后的 `data/` 和 `docs/` 提交回仓库 |

### 404 排查清单

如果部署成功但页面 404，请逐一检查：

- [ ] **Settings → Pages → Source** 是否为 **GitHub Actions**（不是 "Deploy from a branch"）
- [ ] **Actions 页面的工作流运行日志** — 所有步骤是否绿色勾（尤其 `Upload artifact` 和 `Deploy to Pages`）
- [ ] **仓库中是否存在 `docs/index.html`** — 非空文件（初始提交已包含，工作流每次覆盖）
- [ ] **仓库中是否存在 `docs/.nojekyll`** — 必须存在，否则 Jekyll 可能干扰
- [ ] **访问的 URL 是否正确** — 格式为 `https://<owner>.github.io/<repo>/`，注意末尾斜杠和 repo 名大小写
- [ ] **首次部署后等待 1-2 分钟** — GitHub Pages 首次激活需要时间

### 本地测试

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
├── AGENTS.md                    # AI 代理说明文件
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
