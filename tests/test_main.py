"""SCCO Monitor · 相关性系数 — 完整测试."""

import json
from datetime import datetime
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from scco_monitor import chart as scco_chart
from scco_monitor import config
from scco_monitor.chart import build_chart_json, build_history_chart_json, build_html
from scco_monitor.core import calculate_ratio, get_signal
from scco_monitor.fetcher import FetchError, fetch_market_data
from scco_monitor.models import Signal
from scco_monitor.scheduler import (
    check_schedule,
    is_nyse_holiday,
    is_scheduled_slot,
    read_last_slot,
    record_last_slot,
)
from scco_monitor.storage import append_csv, append_intraday_csv, read_csv, read_intraday_csv
from scco_monitor.zone import scan_transitions as run_bt


@pytest.fixture
def sample_data():
    return {"date": "2026-07-03", "copper": 6.229, "scco_open": 171.0, "scco_high": 175.89,
            "scco_low": 169.14, "scco_close": 172.01, "scco_volume": 1_454_500, "shares": 773_000_000}


@pytest.fixture
def sample_ratio():
    return {"ratio": 0.9961, "p_safe": 175.93, "p_watch": 191.92, "p_hot": 208.29}


@pytest.fixture
def sample_intraday():
    return [
        {"datetime": "2026-07-03T09:30:00", "copper_ref": 6.229, "scco_open": 171.0,
         "scco_high": 171.5, "scco_low": 170.8, "scco_close": 171.2, "scco_volume": 50000},
        {"datetime": "2026-07-03T09:45:00", "copper_ref": 6.229, "scco_open": 171.2,
         "scco_high": 171.8, "scco_low": 171.0, "scco_close": 171.6, "scco_volume": 42000},
    ]


@pytest.fixture
def tmp_workspace(tmp_path):
    d, doc = tmp_path / "data", tmp_path / "docs"
    d.mkdir()
    doc.mkdir()
    with patch.object(config, "DATA_DIR", d), patch.object(config, "DOCS_DIR", doc), \
         patch.object(config, "CSV_PATH", d / "history.csv"), \
         patch.object(config, "CSV_INTRADAY_PATH", d / "intraday.csv"), \
         patch.object(config, "LAST_SLOT_PATH", d / ".last_slot"), \
         patch.object(config, "HTML_PATH", doc / "index.html"), \
         patch.object(scco_chart, "DOCS_DIR", doc), \
         patch.object(scco_chart, "HTML_PATH", doc / "index.html"):
        yield tmp_path


# ── calculate_ratio ─────────────────────────

class TestCalcRatio:
    def test_basic(self, sample_data):
        r = calculate_ratio(sample_data)
        assert "ratio" in r and 0 < r["ratio"] < 5
        assert r["p_safe"] < r["p_watch"] < r["p_hot"]

    def test_boundary_consistency(self):
        d = {"copper": 6.229, "scco_close": 172.01, "shares": 773_000_000}
        r = calculate_ratio(d)
        anchor = d["copper"] / 4.2 * 900 * 1e8
        for mult, key in [(1.08, "p_safe"), (1.18, "p_watch"), (1.28, "p_hot")]:
            assert abs(r[key] - mult * anchor / d["shares"]) < 0.01

    def test_string_input(self):
        """calculate_ratio 应能处理字符串数值 (CSV 读取场景)."""
        d = {"copper": "6.229", "scco_close": "172.01", "shares": "773000000"}
        r = calculate_ratio(d)
        assert 0 < r["ratio"] < 5

    def test_missing_shares(self):
        d = {"copper": 6.229, "scco_close": 172.01}
        with pytest.raises(KeyError):
            calculate_ratio(d)


# ── get_signal ──────────────────────────────

class TestGetSignal:
    @pytest.mark.parametrize("ratio,expected", [
        (0.5, "safe"), (1.0, "safe"), (1.08, "safe"),
        (1.081, "watch"), (1.15, "watch"), (1.18, "watch"),
        (1.181, "hot"), (1.25, "hot"), (1.279, "hot"),
        (1.28, "danger"), (2.0, "danger"),
    ])
    def test_boundaries(self, ratio, expected):
        assert get_signal(ratio)[0] == expected

    def test_returns_tuple(self):
        assert len(get_signal(1.0)) == 2


# ── CSV ─────────────────────────────────────

class TestCSV:
    def _w(self, date="2026-01-01", close=100, ratio=0.9):
        append_csv({"date": date, "copper": 5.0, "scco_open": 100, "scco_high": 101,
                     "scco_low": 99, "scco_close": close, "scco_volume": 1000, "shares": 773_000_000},
                    {"ratio": ratio, "p_safe": 100, "p_watch": 110, "p_hot": 120})

    def test_creates(self, tmp_workspace):
        self._w()
        assert config.CSV_PATH.exists()

    def test_roundtrip(self, tmp_workspace):
        self._w("2026-01-01")
        self._w("2026-01-02", close=102)
        assert len(read_csv()) == 2

    def test_upsert(self, tmp_workspace):
        self._w("2026-01-01", close=100)
        self._w("2026-01-01", close=105)
        assert read_csv()[0]["scco_close"] == "105"

    def test_empty(self, tmp_workspace):
        assert read_csv() == []

    def test_sort(self, tmp_workspace):
        for d in ["2026-01-03", "2026-01-01", "2026-01-02"]:
            self._w(d)
        assert [r["date"] for r in read_csv()] == ["2026-01-01", "2026-01-02", "2026-01-03"]


class TestIntraCSV:
    def test_write_read(self, tmp_workspace, sample_intraday):
        append_intraday_csv(sample_intraday, 0.99)
        rows = read_intraday_csv()
        assert len(rows) == 2 and float(rows[0]["ratio"]) == 0.99

    def test_empty(self, tmp_workspace):
        assert read_intraday_csv() == []


# ── 回测 ────────────────────────────────────

class TestBacktest:
    @staticmethod
    def _mk(n=50):
        import random
        random.seed(0)
        return [{"date": f"2026-{i//30+1:02d}-{(i%30)+1:02d}",
                 "scco_close": str(round(170 + random.uniform(-5, 5), 2)),
                 "ratio": str(round(random.uniform(0.8, 1.4), 4))} for i in range(n)]

    def test_short(self):
        assert run_bt([]) == {"zone_history": [], "transitions": []}

    def test_has_keys(self):
        r = run_bt(self._mk())
        assert "zone_history" in r and "transitions" in r

    def test_transitions(self):
        rows = []
        for i in range(50):
            ratio = 0.9 if i < 15 else (1.2 if i < 30 else 1.4)
            rows.append({"date": f"2026-01-{i+1:02d}",
                         "scco_close": str(150 + i * 0.5), "ratio": str(ratio)})
        r = run_bt(rows)
        assert len(r["transitions"]) >= 2


# ── HTML ────────────────────────────────────

class TestHTML:
    def test_generates(self, tmp_workspace, sample_data, sample_ratio, sample_intraday):
        build_html([], [], sample_data, sample_ratio)
        assert config.HTML_PATH.exists()
        html = config.HTML_PATH.read_text()
        assert "Plotly.react" in html

    def test_with_data(self, tmp_workspace, sample_data, sample_ratio, sample_intraday):
        row = {**sample_data, **sample_ratio}
        build_html([row], sample_intraday, sample_data, sample_ratio)
        html = config.HTML_PATH.read_text()
        assert "SCCO" in html and "Correlation" in html

    def test_chart_json(self, sample_data, sample_ratio):
        j = json.loads(build_chart_json([], sample_data, sample_ratio))
        assert "data" in j and "layout" in j and "config" in j

    def test_history_chart_json(self):
        j = json.loads(build_history_chart_json([]))
        assert j is None

    def test_history_chart_json_with_data(self, sample_data, sample_ratio):
        row = {**sample_data, **sample_ratio}
        with patch.object(config, "DAYS_HISTORICAL", 60):
            j = json.loads(build_history_chart_json([row, row]))
        assert isinstance(j, dict)


# ── 调度器 ────────────────────────────────────

class TestScheduler:
    def _et(self, h, m, dow=0):
        """创建 ET 时区的 datetime. dow: 0=Mon ... 6=Sun."""
        from datetime import timedelta
        base = datetime(2026, 7, 6) + timedelta(days=dow)  # 2026-07-06 为周一，非假日
        return base.replace(hour=h, minute=m, tzinfo=ZoneInfo("America/New_York"))

    @pytest.mark.parametrize("h,m", [
        (9, 0), (9, 5), (9, 10), (9, 15), (9, 20), (9, 25),
        (9, 30), (9, 55), (10, 0),
        (11, 30), (11, 35), (11, 45), (12, 0), (12, 30),
        (12, 45), (13, 0),
        (15, 55), (16, 0),
    ])
    def test_exact_match(self, h, m):
        assert check_schedule(self._et(h, m), last_slot="", auto_wait=False).should_run

    @pytest.mark.parametrize("h,m", [
        (8, 0), (8, 30), (17, 0), (18, 0),
    ])
    def test_no_match_outside_hours(self, h, m):
        assert not check_schedule(self._et(h, m), last_slot="", auto_wait=False).should_run

    def test_scheduled_slot_membership(self):
        assert is_scheduled_slot(9, 30)
        assert is_scheduled_slot(11, 35)
        assert is_scheduled_slot(12, 0)
        assert is_scheduled_slot(12, 30)
        assert not is_scheduled_slot(12, 35)
        assert not is_scheduled_slot(12, 40)
        assert is_scheduled_slot(12, 45)

    def test_off_slot_skip_when_deployed(self):
        """当上一个槽位已部署时，非槽位时刻正常跳过."""
        sr = check_schedule(self._et(12, 35), last_slot="2026-07-06 12:30", auto_wait=False)
        assert not sr.should_run

    def test_cron_latency_absorbs_and_matches_slot(self):
        """cron 延迟 2 分钟启动时，仍能正确匹配到当前槽位并执行."""
        sr = check_schedule(self._et(10, 2), last_slot="2026-07-06 09:55", auto_wait=False)
        assert sr.should_run
        assert sr.matched_slot == (10, 0)

    def test_slot_deduplication(self):
        """相同槽位今日已成功部署过则跳过."""
        sr = check_schedule(self._et(10, 0), last_slot="2026-07-06 10:00", auto_wait=False)
        assert not sr.should_run
        assert "已成功部署" in sr.reason

    def test_force_run(self):
        """force=True 时无论是否部署过均执行."""
        sr = check_schedule(self._et(10, 0), last_slot="2026-07-06 10:00", force=True, auto_wait=False)
        assert sr.should_run

    def test_weekend(self):
        assert not check_schedule(self._et(10, 0, dow=6), last_slot="", auto_wait=False).should_run
        assert not check_schedule(self._et(10, 0, dow=5), last_slot="", auto_wait=False).should_run

    def test_nyse_holiday(self):
        labor_day = datetime(2026, 9, 7, 10, 0, tzinfo=ZoneInfo("America/New_York"))
        assert is_nyse_holiday(labor_day)
        assert not check_schedule(labor_day, last_slot="", auto_wait=False).should_run

    def test_last_slot_persistence(self, tmp_workspace):
        slot_file = config.LAST_SLOT_PATH
        record_last_slot("2026-07-06", 10, 30, path=slot_file)
        assert read_last_slot(path=slot_file) == "2026-07-06 10:30"



# ── fetch_market_data ───────────────────────

class TestFetch:
    @patch("scco_monitor.fetcher.yf.Ticker")
    def test_ok(self, mock_t):
        mc, ms = MagicMock(), MagicMock()
        mock_t.side_effect = lambda t: mc if t == "HG=F" else ms
        idx = pd.DatetimeIndex(["2026-07-02"])
        mc.history.return_value = pd.DataFrame({"Close": [6.229]}, index=idx)
        ms.history.return_value = pd.DataFrame({"Open": [171], "High": [175], "Low": [169],
                                                  "Close": [172], "Volume": [1_000_000]}, index=idx)
        ms.info = {"sharesOutstanding": 773_000_000}
        r = fetch_market_data()
        assert r is not None
        assert r["copper"] == 6.229 and r["scco_close"] == 172.0
        assert r["date"] == "2026-07-02"

    @patch("scco_monitor.fetcher.yf.Ticker")
    def test_non_trading_day(self, mock_t):
        """非交易日返回 None (而不是抛异常)."""
        mock_t.return_value.history.return_value = pd.DataFrame()
        assert fetch_market_data() is None

    @patch("scco_monitor.fetcher.yf.Ticker")
    def test_fallback_shares(self, mock_t):
        mc, ms = MagicMock(), MagicMock()
        mock_t.side_effect = lambda t: mc if t == "HG=F" else ms
        idx = pd.DatetimeIndex(["2026-07-02"])
        mc.history.return_value = pd.DataFrame({"Close": [6.0]}, index=idx)
        ms.history.return_value = pd.DataFrame({"Open": [100], "High": [101], "Low": [99],
                                                  "Close": [100], "Volume": [1000]}, index=idx)
        ms.info = {}
        assert fetch_market_data()["shares"] == 773_000_000


# ── run_monitor 流程与重试测试 ────────────────────────

class TestRunMonitor:
    @patch("main.push")
    @patch("main.fetch_intraday_data")
    @patch("main.fetch_market_data")
    @patch("main.check_schedule")
    def test_run_monitor_success(self, mock_sched, mock_fetch, mock_intro, mock_push, tmp_workspace, sample_data):
        from main import run_monitor
        from scco_monitor.scheduler import ScheduleResult
        mock_sched.return_value = ScheduleResult(should_run=True, matched_slot=(10, 0), reason="命中槽位")
        mock_fetch.return_value = sample_data
        mock_intro.return_value = []
        result = run_monitor()
        assert result is True
        assert (tmp_workspace / "data" / ".generated").exists()
        assert (tmp_workspace / "data" / ".last_slot").exists()

    @patch("main.check_schedule")
    def test_run_monitor_skip(self, mock_sched, tmp_workspace):
        from main import run_monitor
        from scco_monitor.scheduler import ScheduleResult
        mock_sched.return_value = ScheduleResult(should_run=False, matched_slot=None, reason="周末休市")
        result = run_monitor()
        assert result is False
        assert not (tmp_workspace / "data" / ".generated").exists()

    @patch("main.time.sleep")
    @patch("main.push")
    @patch("main.fetch_intraday_data")
    @patch("main.fetch_market_data")
    @patch("main.check_schedule")
    def test_run_monitor_retry_until_success(self, mock_sched, mock_fetch, mock_intro, mock_push, mock_sleep, tmp_workspace, sample_data):
        from main import run_monitor
        from scco_monitor.scheduler import ScheduleResult
        mock_sched.return_value = ScheduleResult(should_run=True, matched_slot=(10, 30), reason="命中槽位")
        # 前两次失败，第三次成功
        mock_fetch.side_effect = [Exception("网络超时"), None, sample_data]
        mock_intro.return_value = []
        result = run_monitor()
        assert result is True
        assert mock_fetch.call_count == 3
        assert (tmp_workspace / "data" / ".generated").exists()

