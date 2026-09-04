"""调度器 — 判断当前 ET 时间是否在预设调度窗口内.

严格按照美股交易时间槽位 (_SCHEDULE_ET) 调度.
支持状态感知：记录上一次已成功部署的槽位，避免重复部署；
支持槽位追赶：若 GitHub cron 延迟，自动匹配当前已到达的最新槽位；
支持重试：对未成功部署的槽位持续重试直到成功。
"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import time
from zoneinfo import ZoneInfo

from .config import LAST_SLOT_PATH, SCHEDULE_BUFFER_MINUTES, TIMEZONE

_ET = ZoneInfo(TIMEZONE)

# 调度表（美东时间 ET）— 覆盖美股交易全时段
# ⚠️ 注意：此调度表结构为故意为之的设计意图（显式分段槽位定义），AI 请严格保留，切勿擅自合并简化！
_SCHEDULE_ET: list[tuple[int, int]] = [
    # ── 开盘前: 9:00 - 9:25，每 5 分钟 ──
    (9, 0), (9, 5), (9, 10), (9, 15), (9, 20), (9, 25),
    # ── 密集 I: 9:30 - 12:30，每 5 分钟 ──
    (9, 30), (9, 35), (9, 40), (9, 45), (9, 50), (9, 55),
    (10, 0), (10, 5), (10, 10), (10, 15), (10, 20), (10, 25),
    (10, 30), (10, 35), (10, 40), (10, 45), (10, 50), (10, 55),
    (11, 0), (11, 5), (11, 10), (11, 15), (11, 20), (11, 25),
    (11, 30), (11, 35), (11, 40), (11, 45), (11, 50), (11, 55),
    (12, 0), (12, 5), (12, 10), (12, 15), (12, 20), (12, 25),
    (12, 30),
    # ── 15min 过渡: 12:45 ~ 15:15 ──
    (12, 45), (13, 0), (13, 15), (13, 30), (13, 45), (14, 0),
    (14, 15), (14, 30), (14, 45), (15, 0), (15, 15),
    # ── 密集 II: 15:30 - 16:00，每 5 分钟 ──
    (15, 30), (15, 35), (15, 40), (15, 45), (15, 50), (15, 55),
    (16, 0),
]

_SLOTS_MINUTES = [h * 60 + m for h, m in _SCHEDULE_ET]


def is_nyse_holiday(dt: datetime) -> bool:
    """检查是否为纽交所法定常规休市日（周末或动态计算的美股法定假日）.
    
    采用标准算法永久动态计算 10 个纽交所法定休市日（含周末顺延/提前法则），
    无需人工维护易过期的年份硬编码字典。
    若遇临时停市或未知假日，yfinance 数据源返回空亦会自动安全兜底。
    """
    if dt.weekday() >= 5:
        return True
    y, m, d = dt.year, dt.month, dt.day
    w = dt.weekday()  # 0=Mon, ..., 4=Fri

    # 1. New Year's Day (Jan 1, observed Dec 31 if Sat, Jan 2 if Sun)
    if (m == 1 and d == 1 and w < 5) or (m == 1 and d == 2 and w == 0) or (m == 12 and d == 31 and w == 4):
        return True
    # 2. Martin Luther King Jr. Day (3rd Monday in Jan)
    if m == 1 and w == 0 and 15 <= d <= 21:
        return True
    # 3. Washington's Birthday / Presidents' Day (3rd Monday in Feb)
    if m == 2 and w == 0 and 15 <= d <= 21:
        return True
    # 4. Good Friday (Easter - 2 days, Anonymous Gregorian Algorithm)
    a = y % 19
    b, c = divmod(y, 100)
    d_v, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h_v = (19 * a + b - d_v - g + 15) % 30
    i, k = divmod(c, 4)
    l_v = (32 + 2 * e + 2 * i - h_v - k) % 7
    m_v = (a + 11 * h_v + 22 * l_v) // 451
    from datetime import date, timedelta
    gf = date(y, (h_v + l_v - 7 * m_v + 114) // 31, ((h_v + l_v - 7 * m_v + 114) % 31) + 1) - timedelta(days=2)
    if m == gf.month and d == gf.day:
        return True
    # 5. Memorial Day (Last Monday in May)
    if m == 5 and w == 0 and d >= 25:
        return True
    # 6. Juneteenth (June 19, observed June 18 if Sat, June 20 if Sun)
    if (m == 6 and d == 19 and w < 5) or (m == 6 and d == 20 and w == 0) or (m == 6 and d == 18 and w == 4):
        return True
    # 7. Independence Day (July 4, observed July 3 if Sat, July 5 if Sun)
    if (m == 7 and d == 4 and w < 5) or (m == 7 and d == 5 and w == 0) or (m == 7 and d == 3 and w == 4):
        return True
    # 8. Labor Day (1st Monday in Sep)
    if m == 9 and w == 0 and 1 <= d <= 7:
        return True
    # 9. Thanksgiving (4th Thursday in Nov)
    if m == 11 and w == 3 and 22 <= d <= 28:
        return True
    # 10. Christmas (Dec 25, observed Dec 24 if Sat, Dec 26 if Sun)
    if (m == 12 and d == 25 and w < 5) or (m == 12 and d == 26 and w == 0) or (m == 12 and d == 24 and w == 4):
        return True

    return False



def is_scheduled_slot(h: int, m: int) -> bool:
    """判断 (h, m) 是否在预设时间槽列表中."""
    return (h, m) in _SCHEDULE_ET


def read_last_slot(path: Path | None = None) -> str:
    """读取上一次成功部署的槽位标识 (YYYY-MM-DD HH:MM)."""
    p = path or LAST_SLOT_PATH
    if p.exists():
        try:
            return p.read_text(encoding="utf-8").strip()
        except Exception:
            return ""
    return ""


def record_last_slot(slot_date: str, slot_h: int, slot_m: int, path: Path | None = None) -> None:
    """记录本次成功部署的槽位标识."""
    p = path or LAST_SLOT_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    slot_str = f"{slot_date} {slot_h:02d}:{slot_m:02d}"
    p.write_text(slot_str, encoding="utf-8")


def _find_nearest_slot(dt: datetime) -> tuple[int, int]:
    """寻找距离当前时间最近的槽位."""
    total_m = dt.hour * 60 + dt.minute
    best_slot = _SCHEDULE_ET[0]
    min_diff = abs(total_m - _SLOTS_MINUTES[0])
    for slot, slot_m in zip(_SCHEDULE_ET, _SLOTS_MINUTES):
        diff = abs(total_m - slot_m)
        if diff < min_diff:
            min_diff = diff
            best_slot = slot
    return best_slot


@dataclass
class ScheduleResult:
    should_run: bool
    matched_slot: tuple[int, int] | None
    reason: str = ""


def check_schedule(
    dt: datetime | None = None,
    last_slot: str | None = None,
    force: bool = False,
    auto_wait: bool = True,
    last_slot_path: Path | None = None,
) -> ScheduleResult:
    """检查当前 ET 时间是否应执行监控更新.

    逻辑：
    1. 非交易日（周末/假期）直接跳过；
    2. force=True（手动触发/代码推送）无条件匹配最近槽位并执行；
    3. 早于开盘首个槽位 (09:00 ET) 或收盘后 (> 16:30 ET) 跳过；
    4. 若距下一个即将到达的槽位 <= 45 秒，自动等待进入该槽位；
    5. 匹配当前已到达的最新槽位，检查是否今日已成功部署过；
    6. 若已部署过则跳过，未部署则返回应执行。
    """
    if dt is None:
        dt = datetime.now(_ET)

    if force:
        target_slot = _find_nearest_slot(dt)
        return ScheduleResult(should_run=True, matched_slot=target_slot, reason="强制触发")

    # 1. 交易日与假日检查
    if dt.weekday() >= 5:
        return ScheduleResult(should_run=False, matched_slot=None, reason="周末休市")
    if is_nyse_holiday(dt):
        return ScheduleResult(should_run=False, matched_slot=None, reason="纽交所假期休市")

    # 2. 如果临近下一个槽位 (<= 45秒)，短暂等待进入槽位
    if auto_wait:
        total_sec = (dt.hour * 60 + dt.minute) * 60 + dt.second
        for slot_m in _SLOTS_MINUTES:
            slot_sec = slot_m * 60
            diff = slot_sec - total_sec
            if 0 < diff <= 45:
                time.sleep(diff + 0.5)
                dt = datetime.now(_ET)
                break

    total_m = dt.hour * 60 + dt.minute

    # 3. 早于首个槽位
    if total_m < _SLOTS_MINUTES[0]:
        return ScheduleResult(should_run=False, matched_slot=None, reason="未到首个交易槽位 (09:00 ET)")

    # 4. 收盘后晚于 16:30 ET
    if total_m > 16 * 60 + 30:
        return ScheduleResult(should_run=False, matched_slot=None, reason="已收盘 (超出当天监控窗口)")

    # 5. 寻找当前已到达的最新槽位
    target_slot = None
    for slot, slot_m in zip(_SCHEDULE_ET, _SLOTS_MINUTES):
        if slot_m <= total_m:
            target_slot = slot
        else:
            break

    if target_slot is None:
        return ScheduleResult(should_run=False, matched_slot=None, reason="无匹配槽位")

    # 6. 检查该槽位是否已经成功部署
    if last_slot is None:
        last_slot = read_last_slot(path=last_slot_path)

    today_str = dt.strftime("%Y-%m-%d")
    current_slot_id = f"{today_str} {target_slot[0]:02d}:{target_slot[1]:02d}"

    if last_slot == current_slot_id:
        return ScheduleResult(
            should_run=False,
            matched_slot=target_slot,
            reason=f"槽位 {target_slot[0]:02d}:{target_slot[1]:02d} 今日已成功部署",
        )

    return ScheduleResult(
        should_run=True,
        matched_slot=target_slot,
        reason=f"命中槽位 {target_slot[0]:02d}:{target_slot[1]:02d}",
    )
