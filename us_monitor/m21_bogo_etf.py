# -*- coding: utf-8 -*-
"""Map Bogo rows to representative theme ETFs and their latest trend snapshot."""

from __future__ import annotations

import json
from pathlib import Path


DIRECT_STOCK_ETFS = {
    # Concentrated US quantum funds first; broad QTUM remains the liquid anchor.
    "RGTI": ("QTUP", "CQTM", "QTUM"),
    "IONQ": ("QTUP", "CQTM", "QTUM"),
    "QBTS": ("QTUP", "CQTM", "QTUM"),
    "QUBT": ("QTUP", "CQTM", "QTUM"),
}

# Ordered from specific to broad. These are research proxies, not claims that an
# ETF is a pure-play basket or that every mapped stock is a current holding.
THEME_ETF_RULES = (
    (("量子",), ("QTUP", "CQTM", "QTUM"), "直接主题"),
    (("铀", "核电", "核能"), ("URA", "NLR"), "直接主题"),
    (("白银",), ("SIL", "SLV"), "直接主题"),
    (("铜矿", "铜业", "铜·", "铜/", "铜金属"), ("COPX", "XME"), "直接主题"),
    (("黄金", "贵金属"), ("GDX", "GLD"), "主题代理"),
    (("铝", "金属矿业"), ("XME", "PICK"), "主题代理"),
    (("稀土",), ("REMX",), "直接主题"),
    (("锂矿", "锂资源", "锂电", "电解液", "六氟磷酸锂"), ("LIT",), "直接主题"),
    (("电动车", "智能汽车", "机器人出租车"), ("DRIV", "LIT"), "主题代理"),
    (("网络安全",), ("HACK", "CIBR"), "直接主题"),
    (("软件", "SaaS"), ("IGV", "WCLD"), "直接主题"),
    (("云计算", "云·", "云/"), ("SKYY", "IGV"), "主题代理"),
    (("半导体", "晶圆", "ASIC", "AI核心"), ("SMH", "AIQ"), "主题代理"),
    (("光器件", "光模块", "光通信", "CPO"), ("AIQ", "SMH"), "近似代理"),
    (("机器人", "自动驾驶"), ("BOTZ", "ARKQ"), "主题代理"),
    (("油气", "原油", "油服"), ("IEO", "XLE"), "主题代理"),
    (("天然气",), ("UNG", "XLE"), "主题代理"),
    (("航空", "军工"), ("JETS", "ITA"), "主题代理"),
    (("银行",), ("XLF", "KBE"), "主题代理"),
    (("券商", "金融科技"), ("FINX", "XLF"), "主题代理"),
    (("零售",), ("XRT",), "主题代理"),
    (("生物科技",), ("XBI",), "直接主题"),
    (("制药", "医疗"), ("PPH", "XLV"), "主题代理"),
)


def load_snapshot(paths: list[Path] | None = None) -> dict:
    """Load the freshly generated ETF snapshot, then fall back to docs."""
    if paths is None:
        from .m6_dashboard import OUT_DIR

        repo = Path(__file__).resolve().parents[1]
        paths = [OUT_DIR / "etf_trends.json", repo / "docs" / "etf_trends.json"]
    for path in paths:
        try:
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, TypeError, json.JSONDecodeError):
            continue
        if isinstance(payload.get("rows"), list):
            return payload
    return {"dataDate": None, "rows": []}


def map_etfs(code: str, theme: str, available: set[str] | None = None) -> list[tuple[str, str]]:
    """Return representative ETF tickers plus mapping quality."""
    code = str(code or "").strip().upper()
    theme = str(theme or "")
    available = available or set()
    if code in available:
        return [(code, "标的本身")]
    if code in DIRECT_STOCK_ETFS:
        return [(ticker, "直接主题") for ticker in DIRECT_STOCK_ETFS[code]]
    for keywords, tickers, relation in THEME_ETF_RULES:
        if any(keyword in theme for keyword in keywords):
            return [(ticker, relation) for ticker in tickers]
    return []


def contexts(row: dict, snapshot: dict) -> list[dict]:
    """Attach latest 5/21/63-day ETF performance to one Bogo row."""
    by_ticker = {
        str(item.get("tk", "")).upper(): item
        for item in snapshot.get("rows", [])
        if item.get("tk")
    }
    mapped = map_etfs(row.get("代码", ""), row.get("主题", ""), set(by_ticker))
    result = []
    for ticker, relation in mapped:
        item = by_ticker.get(ticker)
        if item:
            result.append({**item, "relation": relation})
    return result


def pct(value) -> str:
    if value is None:
        return "—"
    value = float(value)
    return f"{value:+.1f}%"


def summary(items: list[dict]) -> str:
    if not items:
        return "主题ETF：未映射或暂无行情"
    parts = []
    for item in items:
        state = " / ".join(x for x in (item.get("trend"), item.get("position")) if x)
        parts.append(
            f'{item["tk"]}（{item.get("relation", "主题代理")}） '
            f'5日 {pct(item.get("r5"))} · 21日 {pct(item.get("r21"))} · '
            f'63日 {pct(item.get("r63"))}' + (f" · {state}" if state else "")
        )
    return "主题ETF：" + "；".join(parts)
