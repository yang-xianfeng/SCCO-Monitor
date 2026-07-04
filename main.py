"""SCCO Monitor · 相关性系数 — 主入口.

流程: 回填历史 → 采集 → 计算 → 存储 → 图表 → 通知
非交易日自动兜底, 使用最后已知数据生成报告.
"""

from datetime import datetime

from scco_monitor.chart import build_html
from scco_monitor.config import DAYS_HISTORICAL, PAGES_URL
from scco_monitor.core import calculate_ratio, get_signal
from scco_monitor.fetcher import fetch_daily_data, fetch_intraday_data, fetch_market_data
from scco_monitor.notifier import push
from scco_monitor.storage import append_csv, read_csv

_NUMERIC_KEYS = {"copper", "scco_open", "scco_high", "scco_low", "scco_close", "scco_volume", "shares"}


def _backfill_history() -> list[dict]:
    """回填历史数据到 CSV，只 fetch 不足的部分."""
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


def _row_to_numeric(row: dict) -> dict:
    """将 CSV 读出的字符串 dict 转为数值类型, 供 calculate_ratio / build_html 使用."""
    out = dict(row)
    for k in _NUMERIC_KEYS:
        if k in out:
            try:
                out[k] = float(out[k])
            except (ValueError, TypeError):
                pass
    if "shares" in out:
        out["shares"] = int(out["shares"])
    return out


def main() -> None:
    now = datetime.now()
    print("=" * 42)
    print("  SCCO Monitor · 相关性系数")
    print(f"  {now.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 42)

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
        cur_data = _row_to_numeric(rows[-1])
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

    build_html(rows, intro, cur_data, ratio)
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
