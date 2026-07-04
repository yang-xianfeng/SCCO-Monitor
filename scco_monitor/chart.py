"""HTML 图表 — 相关性系数监控面板.

Plotly 深色主题, 包含:
  1. 信号卡片 + 系数展示
  2. 价格指标网格
  3. 组合 K 线 (60 日日线 + 当日 15min 日内)
  4. 系数区间历史回放 + 资金曲线
"""

import json
from datetime import datetime
from pathlib import Path

from .config import (
    ANCHOR_COPPER_BASE,
    ANCHOR_MCAP_FACTOR,
    DAYS_HISTORICAL,
    GITHUB_REPOSITORY,
    PAGES_URL,
    THRESHOLD_HOT,
    THRESHOLD_SAFE,
    THRESHOLD_WATCH,
)
from .core import get_signal

_HERE = Path(__file__).parent


def _load_template() -> str:
    return (_HERE / "template.html").read_text(encoding="utf-8")


def build_chart_json(daily, intraday, backtest, cur_data, cur_ratio) -> str:
    """构建 Plotly 图表配置."""
    daily_slice = daily[-DAYS_HISTORICAL:] if len(daily) > DAYS_HISTORICAL else daily

    dates, opn, high, low, close, vol = [], [], [], [], [], []
    p_safe, p_watch, p_hot = [], [], []

    for r in daily_slice:
        dates.append(r["date"] + "T16:00:00")
        opn.append(float(r["scco_open"]))
        high.append(float(r["scco_high"]))
        low.append(float(r["scco_low"]))
        close.append(float(r["scco_close"]))
        vol.append(float(r["scco_volume"]) / 1_000)

        c = float(r["copper"])
        s = float(r.get("shares", 773_000_000) or 773_000_000)
        anchor = c / ANCHOR_COPPER_BASE * ANCHOR_MCAP_FACTOR * 1e8
        p_safe.append(round(THRESHOLD_SAFE * anchor / s, 2))
        p_watch.append(round(THRESHOLD_WATCH * anchor / s, 2))
        p_hot.append(round(THRESHOLD_HOT * anchor / s, 2))

    i_start = len(dates)
    for r in intraday:
        dates.append(r["datetime"])
        opn.append(float(r["scco_open"]))
        high.append(float(r["scco_high"]))
        low.append(float(r["scco_low"]))
        close.append(float(r["scco_close"]))
        vol.append(float(r["scco_volume"]) / 1_000)

        ref = float(r.get("copper_ref", cur_data["copper"]) or cur_data["copper"])
        s = float(cur_data.get("shares", 773_000_000) or 773_000_000)
        anchor = ref / ANCHOR_COPPER_BASE * ANCHOR_MCAP_FACTOR * 1e8
        p_safe.append(round(THRESHOLD_SAFE * anchor / s, 2))
        p_watch.append(round(THRESHOLD_WATCH * anchor / s, 2))
        p_hot.append(round(THRESHOLD_HOT * anchor / s, 2))

    transitions = backtest.get("transitions", [])
    marker_data = {"up": {"x": [], "y": []}, "down": {"x": [], "y": []}}
    for t in transitions:
        dt = t[0] + "T16:00:00"
        key = "up" if t[2] in ("safe", "watch") else "down"
        marker_data[key]["x"].append(dt)
        marker_data[key]["y"].append(t[3])

    data = [
        {"type": "candlestick", "x": dates, "open": opn, "high": high, "low": low,
         "close": close, "name": "SCCO",
         "increasing": {"line": {"color": "#26a69a"}, "fillcolor": "#26a69a"},
         "decreasing": {"line": {"color": "#ef5350"}, "fillcolor": "#ef5350"}},
        {"type": "bar", "x": dates, "y": vol, "name": "成交量 (千股)", "yaxis": "y2",
         "marker": {"color": vol, "colorscale": [[0, "#1a237e"], [1, "#26a69a"]],
                    "showscale": False}, "opacity": 0.4},
    ]

    if p_safe:
        data.append({"type": "scatter", "x": dates, "y": p_safe,
                      "name": f"P<sub>{THRESHOLD_SAFE}</sub> 安全",
                      "line": {"color": "#26a69a", "dash": "dash", "width": 1}})
    if p_watch:
        data.append({"type": "scatter", "x": dates, "y": p_watch,
                      "name": f"P<sub>{THRESHOLD_WATCH}</sub> 关注",
                      "line": {"color": "#ffa726", "dash": "dash", "width": 1}})
    if p_hot:
        data.append({"type": "scatter", "x": dates, "y": p_hot,
                      "name": f"P<sub>{THRESHOLD_HOT}</sub> 偏热",
                      "line": {"color": "#ef5350", "dash": "dash", "width": 1}})

    if marker_data["up"]["x"]:
        data.append({"type": "scatter", "x": marker_data["up"]["x"],
                      "y": marker_data["up"]["y"], "mode": "markers",
                      "name": "区间下移", "marker": {"symbol": "triangle-down",
                      "size": 9, "color": "#26a69a", "line": {"color": "#fff", "width": 1}}})
    if marker_data["down"]["x"]:
        data.append({"type": "scatter", "x": marker_data["down"]["x"],
                      "y": marker_data["down"]["y"], "mode": "markers",
                      "name": "区间上移", "marker": {"symbol": "triangle-up",
                      "size": 9, "color": "#ef5350", "line": {"color": "#fff", "width": 1}}})

    if i_start > 0 and i_start < len(dates):
        y_min = min(low + close) * 0.95 if (low + close) else 100
        y_max = max(high + close) * 1.05 if (high + close) else 300
        data.append({"type": "scatter", "x": [dates[i_start], dates[i_start]],
                      "y": [y_min, y_max], "mode": "lines", "name": "日内",
                      "line": {"color": "#888", "dash": "dot", "width": 1},
                      "hoverinfo": "skip"})

    layout = {
        "paper_bgcolor": "#0d1117", "plot_bgcolor": "#0d1117",
        "font": {"color": "#c9d1d9", "family": "-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,sans-serif", "size": 11},
        "margin": {"l": 48, "r": 24, "t": 32, "b": 48},
        "xaxis": {"domain": [0, 1], "gridcolor": "#21262d", "zerolinecolor": "#21262d",
                  "type": "date", "rangeslider": {"visible": False}},
        "yaxis": {"domain": [0.25, 1], "gridcolor": "#21262d", "zerolinecolor": "#21262d",
                  "title": "价格 (USD)", "side": "right"},
        "yaxis2": {"domain": [0, 0.2], "gridcolor": "#21262d", "zerolinecolor": "#21262d",
                   "title": "成交量", "side": "right"},
        "legend": {"orientation": "h", "y": 1.02, "x": 0, "font": {"size": 10},
                   "bgcolor": "rgba(0,0,0,0)"},
        "hovermode": "x unified", "dragmode": "zoom",
    }
    return json.dumps({"data": data, "layout": layout, "config": {"responsive": True, "displayModeBar": False, "scrollZoom": True}},
                       ensure_ascii=False, default=str)


def build_bt_chart_json(backtest: dict, cur_price: float) -> str:
    """构建回测-系数区间资金曲线图."""
    zones = backtest.get("zone_history", [])
    if len(zones) < 2:
        return "null"

    dates = [z[0] + "T16:00:00" for z in zones]
    ratios = [z[2] for z in zones]
    prices = [z[3] for z in zones]
    zone_colors = {"safe": "#26a69a", "watch": "#ffa726", "hot": "#ff7043", "danger": "#ef5350"}

    trace = {
        "type": "scatter", "x": dates, "y": ratios,
        "mode": "lines+markers",
        "name": "相关性系数",
        "line": {"color": "#58a6ff", "width": 2},
        "marker": {"color": [zone_colors.get(z[1], "#888") for z in zones],
                   "size": 4},
        "hovertemplate": "%{x}<br>系数: %{y:.4f}<br>价格: $%{customdata:.2f}<extra></extra>",
        "customdata": prices,
    }

    shapes = []
    for i in range(len(dates) - 1):
        z = zones[i][1]
        shapes.append({
            "type": "rect", "xref": "x", "yref": "paper",
            "x0": dates[i], "x1": dates[i + 1],
            "y0": 0, "y1": 1,
            "fillcolor": zone_colors.get(z, "#888"),
            "opacity": 0.06, "line": {"width": 0},
            "layer": "below",
        })

    layout = {
        "paper_bgcolor": "#161b22", "plot_bgcolor": "#161b22",
        "font": {"color": "#8b949e", "size": 10},
        "margin": {"l": 50, "r": 16, "t": 8, "b": 24},
        "xaxis": {"gridcolor": "#21262d", "zerolinecolor": "#21262d", "type": "date"},
        "yaxis": {"gridcolor": "#21262d", "zerolinecolor": "#21262d",
                  "title": "系数", "side": "right"},
        "hovermode": "x", "showlegend": False,
        "shapes": shapes,
    }
    return json.dumps({"data": [trace], "layout": layout, "config": {"responsive": True, "displayModeBar": False}},
                       ensure_ascii=False, default=str)


def build_html(daily, intraday, cur_data, cur_ratio, backtest) -> None:
    """生成完整 HTML."""
    from .config import DOCS_DIR, HTML_PATH
    Path(DOCS_DIR).mkdir(parents=True, exist_ok=True)

    sig_key, sig_tag = get_signal(cur_ratio["ratio"])
    now = datetime.now()

    chart_json = build_chart_json(daily, intraday, backtest, cur_data, cur_ratio)
    bt_chart_json = build_bt_chart_json(backtest, cur_data["scco_close"])

    total_days = len(daily)
    transitions = backtest.get("transitions", [])
    zones = backtest.get("zone_history", [])

    template = _load_template()
    html = template % {
        "updated": now.strftime("%Y-%m-%d %H:%M UTC"),
        "total_days": total_days,
        "sig_key": sig_key,
        "sig_tag": sig_tag,
        "ratio": cur_ratio["ratio"],
        "copper": cur_data["copper"],
        "scco_close": cur_data["scco_close"],
        "p_safe": cur_ratio["p_safe"],
        "p_watch": cur_ratio["p_watch"],
        "p_hot": cur_ratio["p_hot"],
        "chart_json": chart_json,
        "bt_chart_json": bt_chart_json,
        "transitions": len(transitions),
        "zones_count": len(zones),
        "github_url": f"https://github.com/{GITHUB_REPOSITORY}",
        "pages_url": PAGES_URL,
    }
    HTML_PATH.write_text(html, encoding="utf-8")
    print(f"  HTML 生成 ({total_days} 日 + {len(intraday)} 根日内)")
