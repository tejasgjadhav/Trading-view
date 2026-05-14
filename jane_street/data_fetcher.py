"""
Data Fetcher — historical and live intraday NSE data via yfinance.
"""
import warnings
warnings.filterwarnings("ignore")
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import pytz
from jane_street.config import BACKTEST_PERIOD_YEARS, IST


def _flatten(df: pd.DataFrame) -> pd.DataFrame:
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df


def _localize(df: pd.DataFrame) -> pd.DataFrame:
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC").tz_convert(IST)
    else:
        df.index = df.index.tz_convert(IST)
    return df


def fetch_historical(ticker: str, years: float = BACKTEST_PERIOD_YEARS) -> pd.DataFrame:
    """2 years of daily OHLCV."""
    end   = datetime.today()
    start = end - timedelta(days=int(years * 365))
    df = yf.download(ticker, start=start, end=end, interval="1d",
                     auto_adjust=True, progress=False)
    df = _flatten(df)
    df.dropna(inplace=True)
    if df.empty:
        raise ValueError(f"No historical data for {ticker}")
    return df


def fetch_intraday(ticker: str, interval: str = "5m", period: str = "1d") -> pd.DataFrame:
    """Today's intraday bars."""
    df = yf.download(ticker, period=period, interval=interval,
                     auto_adjust=True, progress=False)
    df = _flatten(df)
    df = _localize(df)
    df.dropna(inplace=True)
    return df


def fetch_intraday_1min(ticker: str) -> pd.DataFrame:
    """1-minute bars for today."""
    return fetch_intraday(ticker, interval="1m", period="1d")


def get_previous_day_levels(ticker: str, df_hist: pd.DataFrame = None) -> dict:
    """Returns PDH, PDL, PDC (previous day high/low/close)."""
    if df_hist is None:
        df_hist = fetch_historical(ticker, years=0.1)
    if len(df_hist) < 2:
        raise ValueError(f"Not enough history for {ticker}")
    prev = df_hist.iloc[-2]
    return {
        "pdh": float(prev["High"]),
        "pdl": float(prev["Low"]),
        "pdc": float(prev["Close"]),
    }
