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

# 调度表（美东时间 ET）
# 覆盖美股交易全时段
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

# NYSE 市场假日 (2024-2027)
# 参考: https://www.nyse.com/markets/hours-calendars
_NYSE_HOLIDAYS = {
    # 2024
    (2024, 1, 1), (2024, 1, 15), (2024, 2, 19), (2024, 3, 29),
    (2024, 5, 27), (2024, 6, 19), (2024, 7, 4), (2024, 9, 2),
    (2024, 11, 28), (2024, 12, 25),
    # 2025
    (2025, 1, 1), (2025, 1, 20), (2025, 2, 17), (2025, 4, 18),
    (2025, 5, 26), (2025, 6, 19), (2025, 7, 4), (2025, 9, 1),
    (2025, 11, 27), (2025, 12, 25),
    # 2026
    (2026, 1, 1), (2026, 1, 19), (2026, 2, 16), (2026, 4, 3),
    (2026, 5, 25), (2026, 6, 19), (2026, 7, 3), (2026, 9, 7),
    (2026, 11, 26), (2026, 12, 25),
    # 2027
    (2027, 1, 1), (2027, 1, 18), (2027, 2, 15), (2027, 3, 26),
    (2027, 5, 31), (2027, 6, 18), (2027, 7, 5), (2027, 9, 6),
    (2027, 11, 25), (2027, 12, 24),
}


def is_nyse_holiday(dt: datetime) -> bool:
    """检查是否为纽交所非交易日（周末或节假日）."""
    if dt.weekday() >= 5:
        return True
    return (dt.year, dt.month, dt.day) in _NYSE_HOLIDAYS


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
