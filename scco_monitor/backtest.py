"""回测 — 相关性系数区间转换记录.

记录每日系数所在区间, 标记区间切换的时间点与价格.
"""

from .core import get_signal


def run(rows: list[dict]) -> dict:
    """扫描历史数据, 记录系数区间及切换事件.

    返回: {
      "zone_history": [(date, zone, ratio, price), ...],   // 每日区间
      "transitions": [(date, old_zone, new_zone, ratio, price), ...],  // 切换点
    }
    """
    if len(rows) < 2:
        return {"zone_history": [], "transitions": []}

    zones = []
    transitions = []
    prev_zone = None

    for row in rows:
        date = row["date"]
        ratio = float(row["ratio"])
        price = float(row.get("scco_close", 0))
        z = get_signal(ratio)[0]

        zones.append((date, z, ratio, price))

        if prev_zone is not None and z != prev_zone:
            transitions.append((date, prev_zone, z, ratio, price))
        prev_zone = z

    return {"zone_history": zones, "transitions": transitions}
