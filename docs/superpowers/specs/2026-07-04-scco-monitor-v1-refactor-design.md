# SCCO Monitor v1.0 — 重构设计文档

## 概述

SCCO Monitor 是一个相关性系数监控工具，计算 SCCO 市值与铜价锚定公平市值的比值，
通过 GitHub Actions 每日自动运行，生成 Plotly HTML 图表发布到 GitHub Pages。

本次重构定位为 **1.0 版本**，目标是解决命名误导、裸 dict 数据模型、模块职责模糊等问题，
打造一个类型安全、命名自文档化的代码库。

**保持不动：** 功能逻辑、HTML 模板、GitHub Actions 配置、通知渠道、数据格式。

---

## 问题清单

| 问题 | 位置 | 影响 |
|---|---|---|
| `backtest.py` 名不副实 | `scco_monitor/backtest.py` | 实际做区间追踪而非回测 |
| 裸 dict 满天飞 | 全部模块 | key 字符串在 6 个文件重复，无类型安全保障 |
| `core.py` 身兼二职 | `scco_monitor/core.py` | 锚定市值计算 + 信号判定绑在一起 |
| `_row_to_numeric` 散布 | `scco_monitor/main.py` | CSV 字符串→数值转换是 storage 的职责 |
| FIELDS 手写 | `scco_monitor/storage.py` | 与 fetcher 的 return key 重复，改一个忘一个 |

---

## 架构方案

### 模块结构（方案 A — 温和重构）

```
scco_monitor/
  __init__.py          # 包标识
  config.py            # 配置：dataclass + 环境变量（API 不变）
  models.py            # 【新增】数据模型：TypedDict + Signal 枚举
  fetcher.py           # 数据采集：返回类型化数据
  core.py              # 核心计算：锚定市值 + 相关系数
  storage.py           # CSV 持久化：读写类型化
  zone.py              # 【重命名】backtest → zone
  notifier.py          # 通知推送：不变
  chart.py             # Plotly + HTML：import 微调
  main.py              # 编排：删除 _row_to_numeric
```

### 数据流（不变）

```
回填历史 → 采集当日 → 计算系数 → 存储 CSV → 生成图表 → 推送通知
         ↘ 非交易日 → 使用最后已知数据
```

---

## 详细设计

### 1. `models.py` — 数据模型

```python
from typing import TypedDict
from enum import Enum

class Signal(str, Enum):
    SAFE = "safe"
    WATCH = "watch"
    HOT = "hot"
    DANGER = "danger"

class MarketData(TypedDict):
    date: str
    copper: float
    scco_open: float
    scco_high: float
    scco_low: float
    scco_close: float
    scco_volume: int
    shares: int

class IntradayBar(TypedDict):
    datetime: str
    copper_ref: float
    scco_open: float
    scco_high: float
    scco_low: float
    scco_close: float
    scco_volume: int

class RatioResult(TypedDict):
    ratio: float
    p_safe: float
    p_watch: float
    p_hot: float
```

TypedDict 是纯类型标注，运行时行为等同于 dict，零性能开销。

### 2. `zone.py` — 区间追踪（原 backtest.py）

- 重命名文件，函数 `run` → `scan_transitions`
- 内部逻辑不变
- import 更新为 `from .signal import get_signal`（见下文）

### 3. `core.py` — 核心计算

保持 `calculate_ratio` 和 `get_signal` 两个函数在同一文件（足够小，不需要拆成两个文件）。

改动：
- `get_signal` 返回值从 `tuple[str, str]` 改为 `tuple[Signal, str]`
- 条件比较使用 `Signal` 枚举

### 4. `fetcher.py` — 类型化返回

三个函数签名改为返回 TypedDict：

```python
def fetch_daily_data(period: str = "3mo") -> list[MarketData]: ...
def fetch_intraday_data() -> list[IntradayBar]: ...
def fetch_market_data() -> MarketData | None: ...
```

内部实现不变。

### 5. `storage.py` — 类型化 + 字段自动推导

- `FIELDS` / `INTRADAY_FIELDS` 不再手写，从 TypedDict 注解推导
- 读写入参/返回值用 TypedDict 标注
- `main.py` 的 `_row_to_numeric` 职责下沉至此

### 6. `main.py` — 编排清理

- 删除 `_row_to_numeric`
- storage 层保证 CSV 读出即类型正确
- import 更新（`zone`、`Signal`）
- 流程步骤不变

---

## 测试策略

现有 34 个测试基本覆盖核心逻辑，本次重构不改变功能，测试调整：

| 改动 | 涉及测试 |
|---|---|
| `backtest.run` → `zone.scan_transitions` | `TestBacktest` → 重命名 + import |
| `get_signal` 返回 `(Signal, str)` | `TestGetSignal` → 对比 `.value` |
| 新增 `models.py` | 无新增测试（纯类型，无运行时逻辑） |

目标：**所有现有测试通过，不降级覆盖率**。

---

## 不变项（防 scope creep）

- 功能逻辑：系数计算、阈值判定、非交易日兜底
- HTML 模板和 UI 样式
- GitHub Actions 流水线
- 通知内容格式
- CSV 数据格式和字段
- 依赖和 requirements.txt
