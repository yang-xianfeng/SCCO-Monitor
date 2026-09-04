import os
import sys
import time
from datetime import datetime
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

from scco_monitor import config
from scco_monitor.chart import build_html
from scco_monitor.core import calculate_ratio, get_signal
from scco_monitor.fetcher import (
    FetchError,
    fetch_daily_data,
    fetch_intraday_data,
    fetch_market_data,
)
from scco_monitor.notifier import push
from scco_monitor.scheduler import check_schedule, record_last_slot
from scco_monitor.storage import append_csv, read_csv, row_to_numeric

_ET = ZoneInfo(config.TIMEZONE)


def _backfill_history() -> list[dict]:
    rows = read_csv()
    if len(rows) >= config.DAYS_HISTORICAL:
        return rows
    needed = config.DAYS_HISTORICAL - len(rows)
    period = f"{needed + 10}d" if needed < 60 else "3mo"
    historical = fetch_daily_data(period=period)
    if not historical:
        return rows
    print(f"  回填 {len(historical)} 日历史数据 (period={period}) ...")
    for h in historical:
        r = calculate_ratio(h)
        append_csv(h, r)
    return read_csv()


def run_monitor(force: bool = False) -> bool:
    now = datetime.now()
    now_et = datetime.now(_ET)
    print("=" * 42)
    print("  SCCO Monitor · 相关性系数")
    print(f"  {now.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 42)

    sr = check_schedule(force=force)
    if not sr.should_run:
        print(f"  当前 ET {now_et.strftime('%H:%M')} 跳过执行: {sr.reason}")
        print("=" * 42)
        return False

    slot_info = f"ET {sr.matched_slot[0]:02d}:{sr.matched_slot[1]:02d}" if sr.matched_slot else "实时"
    print(f"  [调度] 目标槽位: {slot_info} ({sr.reason})")

    rows = _backfill_history()
    print(f"\n[1] 历史数据: {len(rows)} 日")

    # 多次重试获取行情数据 (满足至少 6-8 次重试要求)
    cur_data = None
    last_err = None
    for attempt in range(1, config.MAX_RETRIES + 1):
        try:
            cur_data = fetch_market_data()
            if cur_data is not None:
                break
            print(f"  [重试 {attempt}/{config.MAX_RETRIES}] 暂无最新行情数据，等待重试...")
        except Exception as e:
            last_err = e
            print(f"  [重试 {attempt}/{config.MAX_RETRIES}] 获取行情异常: {e}")
        if attempt < config.MAX_RETRIES:
            time.sleep(config.RETRY_DELAY)

    is_fresh = cur_data is not None
    if is_fresh:
        print(f"[2] 行情: 铜 ${cur_data['copper']}  |  SCCO ${cur_data['scco_close']}")
    else:
        if not rows:
            print("[2] 无可用的市场数据且重试耗尽")
            if last_err:
                raise FetchError(f"获取市场数据失败: {last_err}")
            print("=" * 42)
            return False
        cur_data = row_to_numeric(rows[-1])
        print(f"[2] 使用最后已知数据: 铜 ${cur_data['copper']}  |  SCCO ${cur_data['scco_close']}")

    intro = []
    if is_fresh:
        for attempt in range(1, config.MAX_RETRIES + 1):
            try:
                intro = fetch_intraday_data()
                break
            except Exception as e:
                print(f"  [重试 {attempt}/{config.MAX_RETRIES}] 获取日内K线异常: {e}")
                if attempt < config.MAX_RETRIES:
                    time.sleep(config.RETRY_DELAY)

    print(f"[3] 日内: {len(intro)} 根 15min K 线")

    ratio = calculate_ratio(cur_data)
    sig_key, sig_tag = get_signal(ratio["ratio"])
    print(f"[4] 系数: {ratio['ratio']} ({sig_tag})")

    if is_fresh:
        append_csv(cur_data, ratio)
        rows = read_csv()
    print(f"[5] CSV: {len(rows)} 行")

    build_html(rows, intro, cur_data, ratio, matched_slot=sr.matched_slot)

    # 成功生成后记录槽位并创建标志文件
    if sr.matched_slot:
        record_last_slot(
            now_et.strftime("%Y-%m-%d"),
            sr.matched_slot[0],
            sr.matched_slot[1],
            path=config.LAST_SLOT_PATH,
        )
    (config.DATA_DIR / ".generated").touch()
    print("[6] HTML 已生成并完成状态记录")

    tag = " [Offline]" if not is_fresh else ""
    report = (
        f"【SCCO Monitor】{now.strftime('%m-%d %H:%M')}{tag}\n"
        f"铜 ${cur_data['copper']}  |  SCCO ${cur_data['scco_close']}\n"
        f"系数 {ratio['ratio']}  |  {sig_tag}\n"
        f"📊 {config.PAGES_URL}"
    )
    print(f"\n{report}\n")
    push(report)

    print("=" * 42)
    print("  ✓ 完成")
    print("=" * 42)
    return True


def main() -> None:
    force = os.getenv("FORCE_RUN") == "1" or "--force" in sys.argv
    run_monitor(force=force)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)
