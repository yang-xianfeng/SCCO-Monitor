import time
import yfinance as yf

from .config import (
    COPPER_TICKER,
    DEFAULT_SHARES,
    INTRADAY_INTERVAL,
    INTRADAY_PERIOD,
    SCCO_TICKER,
)
from .models import IntradayBar, MarketData


class FetchError(Exception):
    """数据采集失败 (网络 / yfinance 异常)."""


def _retry_with_backoff(max_retries: int = 3, base_delay: float = 2.0):
    """指数退避重试装饰器."""
    def decorator(func):
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        delay = base_delay * (2 ** attempt)
                        time.sleep(delay)
            raise last_exception
        return wrapper
    return decorator


@_retry_with_backoff(max_retries=3, base_delay=2.0)
def fetch_daily_data(period: str = "3mo") -> list[MarketData]:
    copper = yf.Ticker(COPPER_TICKER).history(period=period)
    scco = yf.Ticker(SCCO_TICKER).history(period=period)

    if copper.empty or scco.empty:
        return []

    idx = scco.index.intersection(copper.index)
    if idx.empty:
        return []

    shares = yf.Ticker(SCCO_TICKER).info.get("sharesOutstanding") or DEFAULT_SHARES
    return [
        MarketData(
            date=dt.strftime("%Y-%m-%d"),
            copper=round(float(copper.loc[dt, "Close"]), 4),
            scco_open=round(float(scco.loc[dt, "Open"]), 2),
            scco_high=round(float(scco.loc[dt, "High"]), 2),
            scco_low=round(float(scco.loc[dt, "Low"]), 2),
            scco_close=round(float(scco.loc[dt, "Close"]), 2),
            scco_volume=int(scco.loc[dt, "Volume"]),
            shares=int(shares),
        )
        for dt in idx
    ]


@_retry_with_backoff(max_retries=3, base_delay=2.0)
def fetch_intraday_data() -> list[IntradayBar]:
    scco = yf.Ticker(SCCO_TICKER).history(period=INTRADAY_PERIOD, interval=INTRADAY_INTERVAL)
    copper = yf.Ticker(COPPER_TICKER).history(period=INTRADAY_PERIOD, interval=INTRADAY_INTERVAL)

    if scco.empty:
        return []

    copper_ref = round(float(copper["Close"].iloc[-1]), 4) if not copper.empty else 0.0
    last_date = scco.index[-1].date()
    scco_today = scco[scco.index.date == last_date]

    return [
        IntradayBar(
            datetime=idx.to_pydatetime().isoformat(),
            copper_ref=copper_ref,
            scco_open=round(float(row["Open"]), 2),
            scco_high=round(float(row["High"]), 2),
            scco_low=round(float(row["Low"]), 2),
            scco_close=round(float(row["Close"]), 2),
            scco_volume=int(row["Volume"]),
        )
        for idx, row in scco_today.iterrows()
    ]


@_retry_with_backoff(max_retries=3, base_delay=2.0)
def fetch_market_data() -> MarketData | None:
    copper_hist = yf.Ticker(COPPER_TICKER).history(period="1d")
    scco_hist = yf.Ticker(SCCO_TICKER).history(period="1d")

    if copper_hist.empty or scco_hist.empty:
        return None

    shares = yf.Ticker(SCCO_TICKER).info.get("sharesOutstanding") or DEFAULT_SHARES

    return MarketData(
        date=scco_hist.index[-1].strftime("%Y-%m-%d"),
        copper=round(float(copper_hist["Close"].iloc[-1]), 4),
        scco_open=round(float(scco_hist["Open"].iloc[-1]), 2),
        scco_high=round(float(scco_hist["High"].iloc[-1]), 2),
        scco_low=round(float(scco_hist["Low"].iloc[-1]), 2),
        scco_close=round(float(scco_hist["Close"].iloc[-1]), 2),
        scco_volume=int(scco_hist["Volume"].iloc[-1]),
        shares=int(shares),
    )
