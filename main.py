"""SCCO Monitor · 相关性系数 — 主入口.

流程: 采集 → 计算 → 存储 → 回测 → 图表 → 通知
"""

from datetime import datetime

from scco_monitor.backtest import run
from scco_monitor.chart import build_html
from scco_monitor.config import PAGES_URL
from scco_monitor.core import calculate_ratio, get_signal
from scco_monitor.fetcher import FetchError, fetch_intraday_data, fetch_market_data
from scco_monitor.notifier import push
from scco_monitor.storage import append_csv, read_csv


def main():
    now = datetime.now()
    print("=" * 42)
    print("  SCCO Monitor · 相关性系数")
    print(f"  {now.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 42)

    data = fetch_market_data()
    print(f"\n[1] 行情: 铜 ${data['copper']}  |  SCCO ${data['scco_close']}")

    intro = fetch_intraday_data()
    print(f"[2] 日内: {len(intro)} 根 15min K 线")

    ratio = calculate_ratio(data)
    sig_key, sig_tag = get_signal(ratio["ratio"])
    print(f"[3] 系数: {ratio['ratio']} ({sig_tag})")

    append_csv(data, ratio)
    rows = read_csv()
    print(f"[4] CSV: {len(rows)} 行")

    bt = run(rows)
    n_tx = len(bt.get("transitions", []))
    print(f"[5] 回测: {n_tx} 次区间切换")

    build_html(rows, intro, data, ratio, bt)
    print(f"[6] HTML 已生成")

    report = (
        f"【SCCO Monitor】{now.strftime('%m-%d %H:%M')}\n"
        f"铜 ${data['copper']}  |  SCCO ${data['scco_close']}\n"
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
    except FetchError as e:
        print(f"ERROR: {e}")
        exit(1)
