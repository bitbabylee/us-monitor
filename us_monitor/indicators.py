# -*- coding: utf-8 -*-
"""公共指标库：RSI / EMA / VWAP / CMF / MFI / 超额Alpha / 量倍"""
import pandas as pd
import numpy as np


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0).rolling(n).mean()
    loss = -delta.where(delta < 0, 0.0).rolling(n).mean()
    return 100 - 100 / (1 + gain / loss)


def ema(close: pd.Series, n: int) -> pd.Series:
    return close.ewm(span=n, adjust=False).mean()


def cmf(h, l, c, v, n: int = 20) -> pd.Series:
    """Chaikin Money Flow：>0 资金净流入，<0 净流出"""
    rng = (h - l).replace(0, np.nan)
    mfv = ((c - l) - (h - c)) / rng * v
    return mfv.rolling(n).sum() / v.rolling(n).sum()


def mfi(h, l, c, v, n: int = 14) -> pd.Series:
    """Money Flow Index：带量的 RSI"""
    tp = (h + l + c) / 3
    mf = tp * v
    pos = mf.where(tp > tp.shift(), 0.0).rolling(n).sum()
    neg = mf.where(tp < tp.shift(), 0.0).rolling(n).sum()
    return 100 - 100 / (1 + pos / neg)


def vwap_intraday(df: pd.DataFrame) -> pd.Series:
    """对单个交易日的分钟级 bars 累计 VWAP（typical price 加权）"""
    tp = (df["High"] + df["Low"] + df["Close"]) / 3
    return (tp * df["Volume"]).cumsum() / df["Volume"].cumsum().replace(0, np.nan)


def pct(a, b) -> float:
    """a 相对 b 的百分比变化"""
    return (a / b - 1) * 100


def last_metrics(close: pd.Series, vol: pd.Series, bench_close: pd.Series):
    """
    通用「前一日微观异动」三件套：
      ret1   最近一根日K涨跌%
      alpha1 减去基准后的 1 日超额%
      volx   成交量 / 20日均量
      ex5    5 日累计超额%
    """
    ret1 = pct(close.iloc[-1], close.iloc[-2])
    b1 = pct(bench_close.iloc[-1], bench_close.iloc[-2])
    alpha1 = ret1 - b1
    volx = vol.iloc[-1] / vol.rolling(20).mean().iloc[-1]
    ret5 = pct(close.iloc[-1], close.iloc[-6])
    b5 = pct(bench_close.iloc[-1], bench_close.iloc[-6])
    ex5 = ret5 - b5
    return ret1, alpha1, volx, ex5
