"""核心计算: 相关性系数 + 信号区间.

相关性系数 = SCCO 实际市值 / 锚定市值
锚定市值 = (铜价 / 4.2) * 900 亿
"""

from .config import (
    ANCHOR_COPPER_BASE,
    ANCHOR_MCAP_FACTOR,
    ANCHOR_MCAP_UNIT,
    THRESHOLD_HOT,
    THRESHOLD_SAFE,
    THRESHOLD_WATCH,
)


def calculate_ratio(data: dict) -> dict:
    """计算相关性系数及各阈值对应的 SCCO 价格.

    返回: {ratio, p_safe, p_watch, p_hot}
    """
    p_copper = data["copper"]
    p_scco = data["scco_close"]
    shares = data["shares"]

    anchor_mcap = p_copper / ANCHOR_COPPER_BASE * ANCHOR_MCAP_FACTOR * ANCHOR_MCAP_UNIT
    actual_mcap = p_scco * shares

    ratio = actual_mcap / anchor_mcap

    return {
        "ratio": round(ratio, 4),
        "p_safe": round(THRESHOLD_SAFE * anchor_mcap / shares, 2),
        "p_watch": round(THRESHOLD_WATCH * anchor_mcap / shares, 2),
        "p_hot": round(THRESHOLD_HOT * anchor_mcap / shares, 2),
    }


def get_signal(ratio: float) -> tuple[str, str]:
    """根据相关性系数判定当前所在区间.

    返回: (key, label)
      key ∈ {safe, watch, hot, danger}
    """
    if ratio <= THRESHOLD_SAFE:
        return "safe", "安全"
    if ratio <= THRESHOLD_WATCH:
        return "watch", "关注"
    if ratio < THRESHOLD_HOT:
        return "hot", "偏热"
    return "danger", "过热"
