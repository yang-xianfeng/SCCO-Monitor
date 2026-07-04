"""SCCO Monitor · 相关性系数 — 完整测试."""

import json
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from scco_monitor import config
from scco_monitor.backtest import run as run_bt
from scco_monitor.chart import build_chart_json, build_html
from scco_monitor.core import calculate_ratio, get_signal
from scco_monitor.fetcher import FetchError, fetch_market_data
from scco_monitor.storage import append_csv, append_intraday_csv, read_csv, read_intraday_csv


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
    d.mkdir(); doc.mkdir()
    with patch.object(config, "DATA_DIR", d), patch.object(config, "DOCS_DIR", doc), \
         patch.object(config, "CSV_PATH", d / "history.csv"), \
         patch.object(config, "CSV_INTRADAY_PATH", d / "intraday.csv"), \
         patch.object(config, "HTML_PATH", doc / "index.html"):
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
    def _mk(self, n=50):
        import random; random.seed(0)
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

    def test_history_chart_json(self, tmp_workspace, sample_data, sample_ratio):
        from scco_monitor.chart import build_history_chart_json
        j = json.loads(build_history_chart_json([]))
        assert j is None or j == "null"


# ── fetch_market_data ───────────────────────

class TestFetch:
    @patch("scco_monitor.fetcher.yf.Ticker")
    def test_ok(self, mock_t):
        mc, ms = MagicMock(), MagicMock()
        mock_t.side_effect = lambda t: mc if t == "HG=F" else ms
        mc.history.return_value = pd.DataFrame({"Close": [6.229]})
        ms.history.return_value = pd.DataFrame({"Open": [171], "High": [175], "Low": [169],
                                                  "Close": [172], "Volume": [1_000_000]})
        ms.info = {"sharesOutstanding": 773_000_000}
        r = fetch_market_data()
        assert r["copper"] == 6.229 and r["scco_close"] == 172.0

    @patch("scco_monitor.fetcher.yf.Ticker")
    def test_empty(self, mock_t):
        mock_t.return_value.history.return_value = pd.DataFrame()
        with pytest.raises(FetchError):
            fetch_market_data()

    @patch("scco_monitor.fetcher.yf.Ticker")
    def test_fallback_shares(self, mock_t):
        mc, ms = MagicMock(), MagicMock()
        mock_t.side_effect = lambda t: mc if t == "HG=F" else ms
        mc.history.return_value = pd.DataFrame({"Close": [6.0]})
        ms.history.return_value = pd.DataFrame({"Open": [100], "High": [101], "Low": [99],
                                                  "Close": [100], "Volume": [1000]})
        ms.info = {}
        assert fetch_market_data()["shares"] == 773_000_000
