"""数据采集 — Yahoo Finance 日线 & 日内 15min."""

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
    """数据采集失败."""


def fetch_daily_data(period: str = "3mo") -> list[dict]:
    """获取 SCCO + 铜期货 N 日日线 OHLCV."""
    copper = yf.Ticker(COPPER_TICKER).history(period=period)
    scco = yf.Ticker(SCCO_TICKER).history(period=period)

    if copper.empty or scco.empty:
        print("WARN: 日线数据不完整")
        return []

    idx = scco.index.intersection(copper.index)
    if idx.empty:
        return []

    shares = yf.Ticker(SCCO_TICKER).info.get("sharesOutstanding") or DEFAULT_SHARES
    rows = []
    for dt in idx:
        rows.append({
            "date": dt.strftime("%Y-%m-%d"),
            "copper": round(float(copper.loc[dt, "Close"]), 4),
            "scco_open": round(float(scco.loc[dt, "Open"]), 2),
            "scco_high": round(float(scco.loc[dt, "High"]), 2),
            "scco_low": round(float(scco.loc[dt, "Low"]), 2),
            "scco_close": round(float(scco.loc[dt, "Close"]), 2),
            "scco_volume": int(scco.loc[dt, "Volume"]),
            "shares": int(shares),
        })
    return rows


def fetch_intraday_data() -> list[dict]:
    """获取当日 SCCO 15min 日内 OHLCV."""
    scco = yf.Ticker(SCCO_TICKER).history(period=INTRADAY_PERIOD, interval=INTRADAY_INTERVAL)
    copper = yf.Ticker(COPPER_TICKER).history(period=INTRADAY_PERIOD, interval=INTRADAY_INTERVAL)

    if scco.empty:
        print("WARN: 日内数据为空")
        return []

    copper_ref = round(float(copper["Close"].iloc[-1]), 4) if not copper.empty else 0.0
    today = pd.Timestamp(datetime.now().strftime("%Y-%m-%d"), tz=scco.index.tz)
    scco_today = scco[scco.index.date == today.date()]

    rows = []
    for idx, row in scco_today.iterrows():
        rows.append({
            "datetime": idx.to_pydatetime().isoformat(),
            "copper_ref": copper_ref,
            "scco_open": round(float(row["Open"]), 2),
            "scco_high": round(float(row["High"]), 2),
            "scco_low": round(float(row["Low"]), 2),
            "scco_close": round(float(row["Close"]), 2),
            "scco_volume": int(row["Volume"]),
        })
    return rows


def fetch_market_data() -> dict:
    """采集当日单日行情."""
    copper = yf.Ticker(COPPER_TICKER)
    scco = yf.Ticker(SCCO_TICKER)

    copper_hist = copper.history(period="1d")
    scco_hist = scco.history(period="1d")

    if copper_hist.empty or scco_hist.empty:
        raise FetchError("yfinance 返回空数据，可能非交易日或网络异常")

    shares = scco.info.get("sharesOutstanding") or DEFAULT_SHARES

    return {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "copper": round(float(copper_hist["Close"].iloc[-1]), 4),
        "scco_open": round(float(scco_hist["Open"].iloc[-1]), 2),
        "scco_high": round(float(scco_hist["High"].iloc[-1]), 2),
        "scco_low": round(float(scco_hist["Low"].iloc[-1]), 2),
        "scco_close": round(float(scco_hist["Close"].iloc[-1]), 2),
        "scco_volume": int(scco_hist["Volume"].iloc[-1]),
        "shares": int(shares),
    }
