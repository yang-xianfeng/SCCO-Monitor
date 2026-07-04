"""数据采集 — Yahoo Finance 日线 & 日内 15min.

非交易日: fetch_market_data() 返回 None, fetch_intraday_data() 返回 [].
"""

from datetime import datetime

import pandas as pd
import yfinance as yf

from .config import (
    COPPER_TICKER,
    DEFAULT_SHARES,
    INTRADAY_INTERVAL,
    INTRADAY_PERIOD,
    SCCO_TICKER,
)


class FetchError(Exception):
    """数据采集失败 (网络 / yfinance 异常)."""


def fetch_daily_data(period: str = "3mo") -> list[dict]:
    """获取 SCCO + 铜期货 N 日日线 OHLCV.

    shares 只 fetch 一次 (避免循环内重复调用 yfinance API).
    """
    copper = yf.Ticker(COPPER_TICKER).history(period=period)
    scco = yf.Ticker(SCCO_TICKER).history(period=period)

    if copper.empty or scco.empty:
        return []

    idx = scco.index.intersection(copper.index)
    if idx.empty:
        return []

    shares = yf.Ticker(SCCO_TICKER).info.get("sharesOutstanding") or DEFAULT_SHARES
    return [
        {
            "date": dt.strftime("%Y-%m-%d"),
            "copper": round(float(copper.loc[dt, "Close"]), 4),
            "scco_open": round(float(scco.loc[dt, "Open"]), 2),
            "scco_high": round(float(scco.loc[dt, "High"]), 2),
            "scco_low": round(float(scco.loc[dt, "Low"]), 2),
            "scco_close": round(float(scco.loc[dt, "Close"]), 2),
            "scco_volume": int(scco.loc[dt, "Volume"]),
            "shares": int(shares),
        }
        for dt in idx
    ]


def fetch_intraday_data() -> list[dict]:
    """获取当日 SCCO 15min 日内 OHLCV + 铜价参考.

    非交易日返回 [].
    """
    scco = yf.Ticker(SCCO_TICKER).history(period=INTRADAY_PERIOD, interval=INTRADAY_INTERVAL)
    copper = yf.Ticker(COPPER_TICKER).history(period=INTRADAY_PERIOD, interval=INTRADAY_INTERVAL)

    if scco.empty:
        return []

    copper_ref = round(float(copper["Close"].iloc[-1]), 4) if not copper.empty else 0.0
    last_date = scco.index[-1].date()
    scco_today = scco[scco.index.date == last_date]

    return [
        {
            "datetime": idx.to_pydatetime().isoformat(),
            "copper_ref": copper_ref,
            "scco_open": round(float(row["Open"]), 2),
            "scco_high": round(float(row["High"]), 2),
            "scco_low": round(float(row["Low"]), 2),
            "scco_close": round(float(row["Close"]), 2),
            "scco_volume": int(row["Volume"]),
        }
        for idx, row in scco_today.iterrows()
    ]


def fetch_market_data() -> dict | None:
    """采集当日单日行情.

    返回 dict (有数据) 或 None (非交易日/空数据).
    网络错误等仍可能抛出 FetchError.
    """
    copper_hist = yf.Ticker(COPPER_TICKER).history(period="1d")
    scco_hist = yf.Ticker(SCCO_TICKER).history(period="1d")

    if copper_hist.empty or scco_hist.empty:
        return None

    shares = yf.Ticker(SCCO_TICKER).info.get("sharesOutstanding") or DEFAULT_SHARES

    return {
        "date": copper_hist.index[-1].strftime("%Y-%m-%d"),
        "copper": round(float(copper_hist["Close"].iloc[-1]), 4),
        "scco_open": round(float(scco_hist["Open"].iloc[-1]), 2),
        "scco_high": round(float(scco_hist["High"].iloc[-1]), 2),
        "scco_low": round(float(scco_hist["Low"].iloc[-1]), 2),
        "scco_close": round(float(scco_hist["Close"].iloc[-1]), 2),
        "scco_volume": int(scco_hist["Volume"].iloc[-1]),
        "shares": int(shares),
    }
