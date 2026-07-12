"""调度器 — 判断当前 ET 时间是否在预设调度窗口内."""

from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from .config import TIMEZONE

_ET = ZoneInfo(TIMEZONE)

BUFFER_MINUTES = 3

# 穷举调度表（ET 时间）
# (hour, minute) 列表，全部在 9:00-16:00 ET 范围内
_SCHEDULE_ET: list[tuple[int, int]] = [
    # ── 开盘前: 9:00 - 9:25，每 5 分钟 ──
    (9, 0), (9, 5), (9, 10), (9, 15), (9, 20), (9, 25),
    # ── 密集 I: 9:30 - 12:30，每 5 分钟 ──
    (9, 30), (9, 35), (9, 40), (9, 45), (9, 50), (9, 55),
    (10, 0), (10, 5), (10, 10), (10, 15), (10, 20), (10, 25),
    (10, 30), (10, 35), (10, 40), (10, 45), (10, 50), (10, 55),
    (11, 0), (11, 5), (11, 10), (11, 15), (11, 20), (11, 25), 
    (11, 30), (11, 35), (11, 40), (11, 45), (11, 50), (11, 55), 
    (12, 0), (12, 05), (12, 10), (12, 15), (12, 20), (12, 25),
    (12, 30),
    # ── 15min 过渡: 12:45 ~ 15:15 ──
    (12, 45), (13, 0), (13, 15), (13, 30), (13, 45), (14, 0), 
    (14, 15), (14, 30), (14, 45),(15, 0), (15, 15),
    # ── 密集 II: 15:30 - 16:00，每 5 分钟 ──
    (15, 30), (15, 35), (15, 40), (15, 45), (15, 50), (15, 55),
    (16, 0),
]

# 预计算为分钟数，加速检查
_SLOTS_MINUTES = [h * 60 + m for h, m in _SCHEDULE_ET]

# NYSE 市场假日（2024-2026）
# 参考: https://www.nyse.com/markets/hours-calendars
_NYSE_HOLIDAYS = {
    # 2024
    (1, 1),   # New Year's Day (Monday)
    (1, 15),  # MLK Jr. Day
    (2, 19),  # Presidents' Day
    (3, 29),  # Good Friday
    (5, 27),  # Memorial Day
    (6, 19),  # Juneteenth
    (7, 4),   # Independence Day
    (9, 2),   # Labor Day
    (11, 28), # Thanksgiving
    (12, 25), # Christmas
    # 2025
    (1, 1),   # New Year's Day (Wednesday)
    (1, 20),  # MLK Jr. Day
    (2, 17),  # Presidents' Day
    (4, 18),  # Good Friday
    (5, 26),  # Memorial Day
    (6, 19),  # Juneteenth
    (7, 4),   # Independence Day
    (9, 1),   # Labor Day
    (11, 27), # Thanksgiving
    (12, 25), # Christmas
    # 2026
    (1, 1),   # New Year's Day (Thursday)
    (1, 19),  # MLK Jr. Day
    (2, 16),  # Presidents' Day
    (4, 3),   # Good Friday
    (5, 25),  # Memorial Day
    (6, 19),  # Juneteenth
    (7, 4),   # Independence Day (Saturday -> market closed Friday 7/3)
    (9, 7),   # Labor Day
    (11, 26), # Thanksgiving
    (12, 25), # Christmas
}

def _is_nyse_holiday(dt: datetime) -> bool:
    """检查是否为 NYSE 非交易日（假日或周末）."""
    # 周末直接返回 True
    if dt.weekday() >= 5:  # Sat=5, Sun=6
        return True
    
    # 检查假日列表
    if (dt.month, dt.day) in _NYSE_HOLIDAYS:
        return True
    
    return False


@dataclass
class ScheduleResult:
    """调度检查结果."""
    should_run: bool
    matched_slot: tuple[int, int] | None
    offset_min: int

    @property
    def buffer_label(self) -> str:
        if self.matched_slot is None or self.offset_min >= 0:
            return ""
        h, m = self.matched_slot
        return f"（较目标 {h:02d}:{m:02d} 提前 {-self.offset_min} 分钟）"


def check_schedule(dt: datetime | None = None) -> ScheduleResult:
    """检查 *dt*（默认当前时间，ET）是否在任一调度窗口 [slot-BUFFER, slot+1min] 内.

    仅在美国交易日 Mon-Fri（非假日）匹配调度窗口；非交易日直接返回不应执行.
    自动处理 EDT/EST 时区转换（ZoneInfo）.
    """
    if dt is None:
        dt = datetime.now(_ET)
    
    # 检查是否为 NYSE 非交易日
    if _is_nyse_holiday(dt):
        return ScheduleResult(should_run=False, matched_slot=None, offset_min=0)
    
    total = dt.hour * 60 + dt.minute

    for slot_h, slot_m, slot_total in zip(
        [h for h, _ in _SCHEDULE_ET],
        [m for _, m in _SCHEDULE_ET],
        _SLOTS_MINUTES,
    ):
        if slot_total - BUFFER_MINUTES <= total <= slot_total + 1:
            return ScheduleResult(
                should_run=True,
                matched_slot=(slot_h, slot_m),
                offset_min=total - slot_total,
            )

    return ScheduleResult(should_run=False, matched_slot=None, offset_min=0)
