"""HTML 图表 — 相关性系数监控面板.

Plotly 深色主题:
  1. 头部三栏: 铜价, SCCO 股价, 相关性系数
  2. 日内 15min K 线图 (仅当日) + 阈值点标注
  3. 60 日历史走势 (铜价 / SCCO 股价 / 系数)
"""

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from typing import Any

from .config import (
    ANCHOR_COPPER_BASE,
    ANCHOR_MCAP_FACTOR,
    ANCHOR_MCAP_UNIT,
    DAYS_HISTORICAL,
    DEFAULT_SHARES,
    DOCS_DIR,
    HTML_PATH,
    INTRADAY_INTERVAL,
    PLOTLY_VERSION,
    THRESHOLD_HOT,
    THRESHOLD_SAFE,
    THRESHOLD_WATCH,
    TIMEZONE,
)
from .core import get_signal

_HERE = Path(__file__).parent
_ET = ZoneInfo(TIMEZONE)


def _load_template() -> str:
    return (_HERE / "template.html").read_text(encoding="utf-8")


def _compute_threshold_prices(ref_copper: float, shares: float) -> dict[str, float]:
    """根据铜价计算阈值对应的 SCCO 股价."""
    anchor = ref_copper / ANCHOR_COPPER_BASE * ANCHOR_MCAP_FACTOR * ANCHOR_MCAP_UNIT
    return {
        "p_safe": round(THRESHOLD_SAFE * anchor / shares, 2),
        "p_watch": round(THRESHOLD_WATCH * anchor / shares, 2),
        "p_hot": round(THRESHOLD_HOT * anchor / shares, 2),
    }


def build_chart_json(intraday: list[dict], cur_data: dict, cur_ratio: dict) -> str:
    """日内 15min K 线图 + 阈值线."""
    if not intraday:
        return json.dumps({"data": [], "layout": {}, "config": {"responsive": True}},
                           ensure_ascii=False, default=str)

    dates, opn, high, low, close, vol = [], [], [], [], [], []
    for r in intraday:
        dates.append(r["datetime"])
        opn.append(float(r["scco_open"]))
        high.append(float(r["scco_high"]))
        low.append(float(r["scco_low"]))
        close.append(float(r["scco_close"]))
        vol.append(float(r["scco_volume"]) / 1_000)

    ref_copper = float(intraday[0].get("copper_ref", cur_data.get("copper", 0)))
    shares = float(cur_data.get("shares", DEFAULT_SHARES) or DEFAULT_SHARES)
    threshold_prices = _compute_threshold_prices(ref_copper, shares)

    data: list[dict[str, Any]] = [
        {"type": "candlestick", "x": dates, "open": opn, "high": high, "low": low,
         "close": close, "name": "SCCO",
         "increasing": {"line": {"color": "#26a69a"}, "fillcolor": "#26a69a"},
         "decreasing": {"line": {"color": "#ef5350"}, "fillcolor": "#ef5350"}},
        {"type": "bar", "x": dates, "y": vol, "name": "成交量 (千股)", "yaxis": "y2",
         "marker": {"color": vol, "colorscale": [[0, "#1a237e"], [1, "#26a69a"]],
                    "showscale": False}, "opacity": 0.4},
    ]

    thresholds = [
        (threshold_prices["p_safe"], f"P<sub>{THRESHOLD_SAFE}</sub> 安全", "#26a69a"),
        (threshold_prices["p_watch"], f"P<sub>{THRESHOLD_WATCH}</sub> 关注", "#ffa726"),
        (threshold_prices["p_hot"], f"P<sub>{THRESHOLD_HOT}</sub> 偏热", "#ef5350"),
    ]
    for price, label, color in thresholds:
        data.append({
            "type": "scatter", "x": dates, "y": [price] * len(dates),
            "name": label, "mode": "lines+markers",
            "line": {"color": color, "dash": "dash", "width": 1},
            "marker": {"size": 5, "color": color, "symbol": "diamond"},
        })

    layout = {
        "paper_bgcolor": "#0d1117", "plot_bgcolor": "#0d1117",
        "font": {"color": "#c9d1d9",
                 "family": "-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,sans-serif",
                 "size": 11},
        "margin": {"l": 4, "r": 4, "t": 28, "b": 28},
        "xaxis": {"domain": [0, 1], "gridcolor": "#21262d", "zerolinecolor": "#21262d",
                  "type": "date", "rangeslider": {"visible": False},
                  "tickformat": "%H:%M", "hoverformat": "%Y/%m/%d %H:%M"},
        "yaxis": {"domain": [0.25, 1], "gridcolor": "#21262d", "zerolinecolor": "#21262d",
                  "title": "", "side": "right", "automargin": True},
        "yaxis2": {"domain": [0, 0.2], "gridcolor": "#21262d", "zerolinecolor": "#21262d",
                   "title": "", "side": "right", "automargin": True},
        "legend": {"orientation": "h", "y": 1.02, "x": 0, "font": {"size": 10},
                   "bgcolor": "rgba(0,0,0,0)"},
        "hovermode": "x unified",
    }
    return json.dumps({"data": data, "layout": layout,
                        "config": {"responsive": True, "displayModeBar": False, "scrollZoom": False}},
                       ensure_ascii=False, default=str)


def build_history_chart_json(daily: list[dict]) -> str:
    """历史走势图 (铜价, SCCO 股价, 相关性系数)."""
    daily_slice = daily[-DAYS_HISTORICAL:] if len(daily) > DAYS_HISTORICAL else daily
    if len(daily_slice) < 2:
        return "null"

    dates = [r["date"] for r in daily_slice]
    copper = [float(r["copper"]) for r in daily_slice]
    scco = [float(r["scco_close"]) for r in daily_slice]
    ratio = [float(r.get("ratio", 0)) for r in daily_slice]

    colors = ["#ffa726", "#58a6ff", "#26a69a"]

    data = [
        {"type": "scatter", "x": dates, "y": ratio, "name": "Corr",
         "mode": "lines", "line": {"color": colors[2], "width": 2},
         "yaxis": "y", "xaxis": "x",
         "hovertemplate": "%{x|%Y%m%d}<br>Corr: %{y:.4f}<extra></extra>"},
        {"type": "scatter", "x": dates, "y": copper, "name": "Cu",
         "mode": "lines", "line": {"color": colors[0], "width": 2},
         "yaxis": "y2", "xaxis": "x2",
         "hovertemplate": "%{x|%Y%m%d}<br>Cu: $%{y:.4f}<extra></extra>"},
        {"type": "scatter", "x": dates, "y": scco, "name": "SCCO",
         "mode": "lines", "line": {"color": colors[1], "width": 2},
         "yaxis": "y3", "xaxis": "x2",
         "hovertemplate": "%{x|%Y%m%d}<br>SCCO: $%{y:.2f}<extra></extra>"},
    ]

    layout = {
        "paper_bgcolor": "#0d1117", "plot_bgcolor": "#0d1117",
        "font": {"color": "#c9d1d9",
                 "family": "-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,sans-serif",
                 "size": 11},
        "margin": {"l": 48, "r": 72, "t": 12, "b": 48},
        "grid": {"rows": 2, "columns": 1, "pattern": "independent"},
        "xaxis": {"domain": [0, 1], "showticklabels": False,
                  "gridcolor": "#21262d", "zerolinecolor": "#21262d", "type": "date"},
        "xaxis2": {"domain": [0, 1], "matches": "x",
                   "gridcolor": "#21262d", "zerolinecolor": "#21262d", "type": "date",
                   "tickformat": "%Y%m%d"},
        "yaxis": {"title": {"text": "Corr", "font": {"color": colors[2], "size": 14}},
                  "side": "right", "gridcolor": "#21262d", "zerolinecolor": "#21262d",
                  "automargin": True},
        "yaxis2": {"title": {"text": "Cu ($)", "font": {"color": colors[0], "size": 14}},
                   "side": "left", "gridcolor": "#21262d", "zerolinecolor": "#21262d",
                   "automargin": True},
        "yaxis3": {"title": {"text": "SCCO ($)", "font": {"color": colors[1], "size": 14}},
                   "side": "right", "overlaying": "y2",
                   "gridcolor": "#21262d", "zerolinecolor": "#21262d",
                   "automargin": True},
        "legend": {"orientation": "h", "y": 1.02, "x": 0, "font": {"size": 10},
                   "bgcolor": "rgba(0,0,0,0)"},
        "hovermode": "x unified",
    }
    return json.dumps({"data": data, "layout": layout,
                        "config": {"responsive": True, "displayModeBar": False}},
                       ensure_ascii=False, default=str)


def _get_display_date(intraday: list[dict], cur_data: dict, daily: list[dict]) -> str:
    """确定标题栏显示的交易日日期.

    优先级: intraday 数据来源日期 > fetch 市场数据日期 > CSV 最后日期.
    """
    if intraday:
        return intraday[-1]["datetime"][:10]
    if cur_data.get("date"):
        return str(cur_data["date"])
    if daily:
        return str(daily[-1]["date"])
    return datetime.now(_ET).strftime("%Y-%m-%d")


def build_html(daily: list[dict], intraday: list[dict], cur_data: dict, cur_ratio: dict) -> None:
    """生成完整 HTML."""
    DOCS_DIR.mkdir(parents=True, exist_ok=True)

    sig_key, sig_tag = get_signal(cur_ratio["ratio"])
    now = datetime.now(_ET)

    chart_json = build_chart_json(intraday, cur_data, cur_ratio)
    history_chart_json = build_history_chart_json(daily)
    trade_date_compact = _get_display_date(intraday, cur_data, daily).replace("-", "")

    template = _load_template()
    html = template % {
        "updated": now.strftime("%Y-%m-%d %H:%M"),
        "sig_key": sig_key,
        "sig_tag": sig_tag,
        "ratio": cur_ratio["ratio"],
        "copper": cur_data["copper"],
        "scco_close": cur_data["scco_close"],
        "chart_json": chart_json,
        "history_chart_json": history_chart_json,
        "intraday_interval": INTRADAY_INTERVAL,
        "days_historical": DAYS_HISTORICAL,
        "trade_date": trade_date_compact,
        "plotly_version": PLOTLY_VERSION,
    }
    HTML_PATH.write_text(html, encoding="utf-8")
    print(f"  HTML 生成 (日内 {len(intraday)} 根 · 历史 {len(daily)} 日)")
