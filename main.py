import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

from scco_monitor.chart import build_html
from scco_monitor.config import DAYS_HISTORICAL, PAGES_URL, TIMEZONE
from scco_monitor.core import calculate_ratio, get_signal
from scco_monitor.fetcher import fetch_daily_data, fetch_intraday_data, fetch_market_data
from scco_monitor.notifier import push
from scco_monitor.scheduler import check_schedule, _SCHEDULE_ET
from scco_monitor.storage import append_csv, read_csv, row_to_numeric

_ET = ZoneInfo(TIMEZONE)
MAX_WAIT_SECONDS = 10 * 60


def _seconds_until_next_slot(dt: datetime) -> int | None:
    """计算距离下一个调度槽位的秒数，超出最大等待返回 None."""
    if dt.weekday() >= 5:
        return None
    total = dt.hour * 60 + dt.minute
    for slot_h, slot_m in _SCHEDULE_ET:
        slot_total = slot_h * 60 + slot_m
        if slot_total > total:
            wait_minutes = slot_total - total
            if wait_minutes * 60 <= MAX_WAIT_SECONDS:
                return wait_minutes * 60
            return None
    return None


def _backfill_history() -> list[dict]:
    rows = read_csv()
    if len(rows) >= DAYS_HISTORICAL:
        return rows
    needed = DAYS_HISTORICAL - len(rows)
    period = f"{needed + 10}d" if needed < 60 else "3mo"
    historical = fetch_daily_data(period=period)
    if not historical:
        return rows
    print(f"  回填 {len(historical)} 日历史数据 (period={period}) ...")
    for h in historical:
        r = calculate_ratio(h)
        append_csv(h, r)
    return read_csv()


def main() -> None:
    now = datetime.now()
    now_et = datetime.now(_ET)
    print("=" * 42)
    print("  SCCO Monitor · 相关性系数")
    print(f"  {now.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 42)

    sr = check_schedule()
    if not sr.should_run:
        wait_seconds = _seconds_until_next_slot(now_et)
        if wait_seconds is None:
            print(f"  当前 ET {now_et.strftime('%H:%M')} 不在调度窗口内，且无后续槽位（周末或收盘后），跳过")
            print("=" * 42)
            return
        print(f"  当前 ET {now_et.strftime('%H:%M')} 不在调度窗口内，等待 {wait_seconds // 60} 分 {wait_seconds % 60} 秒至下一槽位...")
        time.sleep(wait_seconds)
        sr = check_schedule()
        if not sr.should_run:
            print(f"  等待后仍不在调度窗口内，跳过")
            print("=" * 42)
            return

    rows = _backfill_history()
    print(f"\n[1] 历史数据: {len(rows)} 日")

    cur_data = fetch_market_data()
    is_fresh = cur_data is not None

    if is_fresh:
        print(f"[2] 行情: 铜 ${cur_data['copper']}  |  SCCO ${cur_data['scco_close']}")
    else:
        if not rows:
            print("[2] 无可用的市场数据 (首次运行且非交易日)")
            print("=" * 42)
            return
        cur_data = row_to_numeric(rows[-1])
        print(f"[2] 非交易日, 使用最后已知数据: 铜 ${cur_data['copper']}  |  SCCO ${cur_data['scco_close']}")

    intro = fetch_intraday_data() if is_fresh else []
    print(f"[3] 日内: {len(intro)} 根 15min K 线")

    ratio = calculate_ratio(cur_data)
    sig_key, sig_tag = get_signal(ratio["ratio"])
    print(f"[4] 系数: {ratio['ratio']} ({sig_tag})")

    if is_fresh:
        append_csv(cur_data, ratio)
        rows = read_csv()
    print(f"[5] CSV: {len(rows)} 行")

    build_html(rows, intro, cur_data, ratio, matched_slot=sr.matched_slot)
    Path("data/.generated").touch()
    print("[6] HTML 已生成")

    tag = " [Offline]" if not is_fresh else ""
    report = (
        f"【SCCO Monitor】{now.strftime('%m-%d %H:%M')}{tag}\n"
        f"铜 ${cur_data['copper']}  |  SCCO ${cur_data['scco_close']}\n"
        f"系数 {ratio['ratio']}  |  {sig_tag}\n"
        f"📊 {PAGES_URL}"
    )
    print(f"\n{report}\n")
    push(report)

    print("=" * 42)
    print("  ✓ 完成")
    print("=" * 42)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"ERROR: {e}")
        exit(1)
