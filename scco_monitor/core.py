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


def _anchor_mcap(p_copper: float) -> float:
    return p_copper / ANCHOR_COPPER_BASE * ANCHOR_MCAP_FACTOR * ANCHOR_MCAP_UNIT


def calculate_ratio(data: dict) -> dict:
    """计算相关性系数及各阈值对应的 SCCO 价格.

    输入 data 须包含: copper, scco_close, shares (float / int).
    返回: {ratio, p_safe, p_watch, p_hot}
    """
    anchor = _anchor_mcap(float(data["copper"]))
    actual = float(data["scco_close"]) * float(data["shares"])
    ratio = actual / anchor

    return {
        "ratio": round(ratio, 4),
        "p_safe": round(THRESHOLD_SAFE * anchor / float(data["shares"]), 2),
        "p_watch": round(THRESHOLD_WATCH * anchor / float(data["shares"]), 2),
        "p_hot": round(THRESHOLD_HOT * anchor / float(data["shares"]), 2),
    }


def get_signal(ratio: float) -> tuple[str, str]:
    """根据相关性系数判定当前所在区间.

    返回 (key, label), key ∈ {safe, watch, hot, danger}.
    """
    if ratio <= THRESHOLD_SAFE:
        return "safe", "安全"
    if ratio <= THRESHOLD_WATCH:
        return "watch", "关注"
    if ratio < THRESHOLD_HOT:
        return "hot", "偏热"
    return "danger", "过热"
