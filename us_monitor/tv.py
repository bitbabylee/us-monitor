# -*- coding: utf-8 -*-
"""
TradingView 符号解析 —— 把裸 ticker 变成「交易所:代码」并生成可点链接。

yfinance 的 exchange 字段是内部代号(NMS/NYQ/PCX...), 要映射成 TradingView 的
交易所前缀。解析结果缓存到 .tv_symbols.json, 不必每次联网。
"""
import json
import re
from pathlib import Path

CACHE = Path(__file__).resolve().parent / ".tv_symbols.json"

# yfinance exchange code → TradingView 前缀
EXCH = {
    "NMS": "NASDAQ", "NGM": "NASDAQ", "NCM": "NASDAQ", "NAS": "NASDAQ",
    "NYQ": "NYSE", "NYS": "NYSE",
    "PCX": "AMEX", "ASE": "AMEX", "ARCA": "AMEX", "BTS": "AMEX", "BATS": "AMEX",
    "CBO": "CBOE", "CBOE": "CBOE",
}
# 指数/特殊标的手工映射（yfinance 的 ^ 代码 TradingView 不认）
SPECIAL = {
    "^GSPC": "SP:SPX", "^VIX": "CBOE:VIX", "^TNX": "TVC:TNX",
    "^IXIC": "NASDAQ:IXIC", "^DJI": "DJ:DJI",
    "JPY=X": "FX_IDC:USDJPY",
}


def _load() -> dict:
    if CACHE.exists():
        try:
            return json.loads(CACHE.read_text())
        except json.JSONDecodeError:
            pass
    return {}


def _save(d: dict):
    CACHE.write_text(json.dumps(d, ensure_ascii=False, indent=1, sort_keys=True))


def resolve_many(tickers, refresh=False) -> dict:
    """批量解析。未知的走 yfinance 查一次并落盘缓存。"""
    cache = _load()
    todo = [t for t in dict.fromkeys(tickers)
            if t not in SPECIAL and (refresh or t not in cache)]
    if todo:
        try:
            import yfinance as yf
            for t in todo:
                try:
                    ex = (yf.Ticker(t).info or {}).get("exchange", "")
                    cache[t] = f"{EXCH.get(ex, 'NASDAQ')}:{t}"
                except Exception:
                    cache[t] = f"NASDAQ:{t}"      # 兜底: TradingView 多能自动跳转
            _save(cache)
        except ImportError:
            pass
    out = {}
    for t in dict.fromkeys(tickers):
        out[t] = SPECIAL.get(t) or cache.get(t) or f"NASDAQ:{t}"
    return out


_MAP: dict = {}


def warm(tickers):
    """在渲染前预热一次, 避免逐个联网"""
    global _MAP
    _MAP.update(resolve_many(tickers))
    return _MAP


def symbol(tk: str) -> str:
    """返回 'NASDAQ:AAPL' 形式"""
    if tk in _MAP:
        return _MAP[tk]
    if tk in SPECIAL:
        return SPECIAL[tk]
    return _load().get(tk, f"NASDAQ:{tk}")


def url(tk: str) -> str:
    """图表页(不是 overview 页) —— 登录状态下打开用户自己的图表布局"""
    return "https://www.tradingview.com/chart/?symbol=" + symbol(tk).replace(":", "%3A")


def link(tk: str, bold=True, show_exchange=True) -> str:
    """生成 HTML 链接。show_exchange=False 时只显示代码但仍可点。"""
    sym = symbol(tk)
    ex, _, code = sym.partition(":")
    inner = (f'<span style="color:var(--muted);font-size:11px">{ex}:</span>{code}'
             if show_exchange else code)
    if bold:
        inner = f"<b>{inner}</b>"
    return (f'<a href="{url(tk)}" target="_blank" rel="noopener" '
            f'style="color:inherit;text-decoration:none;border-bottom:1px dotted var(--muted)" '
            f'title="{sym} · 在 TradingView 打开">{inner}</a>')


def linkify_text(s: str, tickers) -> str:
    """把一段纯文本里出现的 ticker 变成链接（用于领头羊/清单这类字符串）"""
    for tk in sorted(set(tickers), key=len, reverse=True):
        s = re.sub(rf"\b{re.escape(tk)}\b", link(tk, bold=False, show_exchange=False), s)
    return s
