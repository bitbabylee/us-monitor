# -*- coding: utf-8 -*-
"""
数据层：IB (Interactive Brokers) 优先，yfinance 自动兜底。

- TWS / IB Gateway 开着（API 端口 7496/7497/4001/4002 任一）→ 走 IB 真实行情
- 没开 / 某标的无权限 → 自动降级 yfinance，打印提示，流程不中断
- 对外接口不变：fetch_daily / fetch_intraday 返回 (字段, 代码) MultiIndex DataFrame
"""
import datetime as dt
import time
from zoneinfo import ZoneInfo

import pandas as pd

from . import config as C

NY = ZoneInfo("America/New_York")


def _drop_partial(df: pd.DataFrame) -> pd.DataFrame:
    """美股收盘(16:00 ET)前, 日线最后一根是当天未完结K线 —— 切掉,
    保证「前一日涨跌/超额/量倍」永远基于已完结交易日, 不被盘中半根K污染。"""
    if df.empty:
        return df
    ny = dt.datetime.now(NY)
    last = df.index[-1]
    last_date = last.date() if hasattr(last, "date") else last
    if last_date == ny.date() and (ny.hour, ny.minute) < (16, 5):
        return df.iloc[:-1]
    return df

# ── yfinance 兜底 ────────────────────────────────────────────

def _yf_daily(tickers, days=260):
    import yfinance as yf
    end = dt.datetime.now()
    return yf.download(sorted(set(tickers)),
                       start=(end - dt.timedelta(days=days)).strftime("%Y-%m-%d"),
                       progress=False, auto_adjust=True, group_by="column")


def _yf_intraday(tickers, interval="5m", period="5d"):
    import yfinance as yf
    return yf.download(sorted(set(tickers)), interval=interval, period=period,
                       progress=False, auto_adjust=True, group_by="column",
                       prepost=False)

# ── IB 后端 ──────────────────────────────────────────────────

_IB = None          # 复用同一个连接


def _ib_connect():
    """尝试连上本机 TWS / Gateway，失败返回 None"""
    global _IB
    if _IB is not None:
        return _IB if _IB.isConnected() else None
    try:
        from ib_insync import IB
    except ImportError:
        return None
    import logging
    logging.getLogger("ib_insync").setLevel(logging.CRITICAL)  # 静音端口探测报错
    for port in C.IB_PORTS:
        ib = IB()
        try:
            ib.connect("127.0.0.1", port, clientId=C.IB_CLIENT_ID,
                       readonly=True, timeout=4)
            _IB = ib
            print(f"✅ 已连接 IB (端口 {port}, {'实盘' if port in (7496, 4001) else '模拟'})")
            return ib
        except Exception:
            ib.disconnect()
    return None


def _ib_contract(ticker):
    from ib_insync import Stock, Index
    mapping = {"^GSPC": ("SPX", "CBOE"), "^VIX": ("VIX", "CBOE"),
               "^TNX": ("TNX", "CBOE")}
    if ticker in mapping:
        sym, exch = mapping[ticker]
        return Index(sym, exch, "USD")
    return Stock(ticker, "SMART", "USD", primaryExchange="")


def _ib_history(ib, tickers, duration, bar_size, what_daily):
    """串行拉取（尊重 IB pacing），返回 {ticker: df}，失败的不在结果里"""
    out, failed = {}, []
    for tk in sorted(set(tickers)):
        contract = _ib_contract(tk)
        what = "TRADES" if contract.secType != "IND" else "TRADES"
        if bar_size == "1 day" and contract.secType == "STK":
            what = what_daily                      # 日线用复权价
        try:
            bars = ib.reqHistoricalData(
                contract, endDateTime="", durationStr=duration,
                barSizeSetting=bar_size, whatToShow=what,
                useRTH=True, formatDate=1)
            if not bars:
                failed.append(tk)
                continue
            from ib_insync import util
            df = util.df(bars).set_index("date")
            df.index = pd.to_datetime(df.index)
            df = df.rename(columns={"open": "Open", "high": "High", "low": "Low",
                                    "close": "Close", "volume": "Volume"})
            out[tk] = df[["Open", "High", "Low", "Close", "Volume"]]
        except Exception:
            failed.append(tk)
        time.sleep(C.IB_PACING_SLEEP)              # pacing 限速保护
    return out, failed


def _merge(per_ticker: dict) -> pd.DataFrame:
    """{ticker: OHLCV df} → yfinance 风格 (字段, 代码) MultiIndex"""
    frames = {}
    for tk, df in per_ticker.items():
        for f in df.columns:
            frames[(f, tk)] = df[f]
    out = pd.DataFrame(frames)
    out.columns = pd.MultiIndex.from_tuples(out.columns)
    return out.sort_index()

# ── 对外接口 ─────────────────────────────────────────────────

def fetch_daily(tickers, days: int = 260) -> pd.DataFrame:
    ib = _ib_connect() if C.DATA_SOURCE == "ib" else None
    if ib is None:
        if C.DATA_SOURCE == "ib":
            print("⚠️ TWS/IB Gateway 未运行, 本次降级用 yfinance（开 TWS 并启用 API 后自动切回）")
        return _drop_partial(_yf_daily(tickers, days))
    got, failed = _ib_history(ib, tickers, f"{max(days, 365)} D", "1 day",
                              "ADJUSTED_LAST")
    if failed:
        print(f"⚠️ IB 无以下标的历史权限, 用 yfinance 补齐: {', '.join(failed)}")
        yf_df = _yf_daily(failed, days)
        for tk in failed:
            try:
                got[tk] = pd.DataFrame({f: yf_df[f][tk] for f in
                                        ["Open", "High", "Low", "Close", "Volume"]}).dropna()
            except KeyError:
                pass
    return _drop_partial(_merge(got))


def fetch_extended(tickers, interval: str = "5m", period: str = "2d") -> pd.DataFrame:
    """含盘前/盘后延长时段的分钟数据(保留纽约时区), 盘前雷达用。
    IB 路径 useRTH=False 也可, 但为简单统一走 yfinance prepost。"""
    import yfinance as yf
    return yf.download(sorted(set(tickers)), interval=interval, period=period,
                       progress=False, auto_adjust=True, group_by="column",
                       prepost=True)


def fetch_intraday(tickers, interval: str = "5m", period: str = "5d") -> pd.DataFrame:
    ib = _ib_connect() if C.DATA_SOURCE == "ib" else None
    if ib is None:
        return _yf_intraday(tickers, interval, period)
    got, failed = _ib_history(ib, tickers, "5 D", "5 mins", "TRADES")
    if failed:
        print(f"⚠️ IB 日内数据缺: {', '.join(failed)}, 用 yfinance 补齐")
        yf_df = _yf_intraday(failed, interval, period)
        for tk in failed:
            try:
                got[tk] = pd.DataFrame({f: yf_df[f][tk] for f in
                                        ["Open", "High", "Low", "Close", "Volume"]}).dropna()
            except KeyError:
                pass
    df = _merge(got)
    # IB 返回的时间带交易所时区, 去掉 tz 使 resample 与 yf 路径一致
    if getattr(df.index, "tz", None) is not None:
        df.index = df.index.tz_localize(None)
    return df


def col(df: pd.DataFrame, field: str, ticker: str) -> pd.Series:
    """从批量结果里取某只标的的某个字段并去 NaN"""
    s = df[field][ticker] if isinstance(df.columns, pd.MultiIndex) else df[field]
    return s.dropna()
