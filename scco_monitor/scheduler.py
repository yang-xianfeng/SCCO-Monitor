"""调度器 — 判断当前 ET 时间是否在预设调度窗口内.

时间槽位(_SCHEDULE_ET)为唯一权威调度依据，绝不修改。
check_schedule 匹配 [槽位, 槽位+BUFFER] 窗口，用迟到容忍吸收
GitHub Actions cron 的启动延迟（否则延迟 1 分钟即漏触发）。
"""

from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from .config import SCHEDULE_BUFFER_MINUTES, TIMEZONE

_ET = ZoneInfo(TIMEZONE)

# 迟到容忍缓冲(分钟)。槽位间隔最小 5 分钟，故恒 < 5，相邻槽位不重叠。
BUFFER_MINUTES = SCHEDULE_BUFFER_MINUTES

_SCHEDULE_ET: list[tuple[int, int]] = [
    (9, 0), (9, 5), (9, 10), (9, 15), (9, 20), (9, 25),
    (9, 30), (9, 35), (9, 40), (9, 45), (9, 50), (9, 55),
    (10, 0), (10, 5), (10, 10), (10, 15), (10, 20), (10, 25),
    (10, 30), (10, 35), (10, 40), (10, 45), (10, 50), (10, 55),
    (11, 0), (11, 5), (11, 10), (11, 15), (11, 20), (11, 25), (11, 30),
    (12, 45), (13, 0), (13, 15), (13, 30), (13, 45), (14, 0),
    (14, 15), (14, 30), (14, 45), (15, 0), (15, 15),
    (15, 30), (15, 35), (15, 40), (15, 45), (15, 50), (15, 55),
    (16, 0),
]

_SLOTS_MINUTES = [h * 60 + m for h, m in _SCHEDULE_ET]


@dataclass
class ScheduleResult:
    should_run: bool
    matched_slot: tuple[int, int] | None


def check_schedule(dt: datetime | None = None) -> ScheduleResult:
    """当前 ET 时间落在 [槽位, 槽位+BUFFER] 内则返回应执行.

    槽位保持精确；缓冲仅用于吸收 cron 启动延迟，避免漏触发。
    """
    if dt is None:
        dt = datetime.now(_ET)
    if dt.weekday() >= 5:
        return ScheduleResult(should_run=False, matched_slot=None)
    total = dt.hour * 60 + dt.minute

    for slot_h, slot_m, slot_total in zip(
        [h for h, _ in _SCHEDULE_ET],
        [m for _, m in _SCHEDULE_ET],
        _SLOTS_MINUTES,
    ):
        if slot_total <= total <= slot_total + BUFFER_MINUTES:
            return ScheduleResult(should_run=True, matched_slot=(slot_h, slot_m))

    return ScheduleResult(should_run=False, matched_slot=None)
