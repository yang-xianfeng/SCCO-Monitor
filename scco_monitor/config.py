"""全局配置 — 统一管理常量与环境变量."""

import os
from pathlib import Path


def _env_float(key: str, default: float) -> float:
    """读取环境变量并转为 float，空值/缺省时返回 default."""
    val = os.getenv(key)
    if val is None or val.strip() == "":
        return default
    return float(val)


# ── 标的 ───────────────────────────────────────────
COPPER_TICKER = "HG=F"
SCCO_TICKER = "SCCO"
DEFAULT_SHARES = 773_000_000

# ── 相关性系数阈值（从配置文件读取, 可按需调整）──
THRESHOLD_SAFE = _env_float("THRESHOLD_SAFE", 1.08)
THRESHOLD_WATCH = _env_float("THRESHOLD_WATCH", 1.18)
THRESHOLD_HOT = _env_float("THRESHOLD_HOT", 1.28)

# ── 锚定市值公式参数 ──────────────────────────────
ANCHOR_COPPER_BASE = _env_float("ANCHOR_COPPER_BASE", 4.2)
ANCHOR_MCAP_FACTOR = _env_float("ANCHOR_MCAP_FACTOR", 900)

# ── 路径 ──────────────────────────────────────────
DATA_DIR = Path("data")
DOCS_DIR = Path("docs")
CSV_PATH = DATA_DIR / "history.csv"
CSV_INTRADAY_PATH = DATA_DIR / "intraday.csv"
HTML_PATH = DOCS_DIR / "index.html"

# ── GitHub Pages ──────────────────────────────────
GITHUB_REPOSITORY = os.getenv("GITHUB_REPOSITORY", "yang-xianfeng/scco-monitor")
PAGES_URL = (
    f"https://{GITHUB_REPOSITORY.split('/')[0]}.github.io/"
    f"{GITHUB_REPOSITORY.split('/')[1]}/"
)

# ── 飞书 / Telegram ──────────────────────────────
FEISHU_WEBHOOK = os.getenv("FEISHU_WEBHOOK", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# ── 图表 ─────────────────────────────────────────
DAYS_HISTORICAL = 60
INTRADAY_INTERVAL = "15m"
INTRADAY_PERIOD = "5d"
