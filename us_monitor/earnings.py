# -*- coding: utf-8 -*-
"""
财报感知层：观察池财报日历 + 风险窗口标记。

规则（AMD 2026-08-04 盘后财报次日跳水就是教训）:
  财报前 ≤EARNINGS_PRE_DAYS 日  → ⚠️ 财报临近, 日线买点信号降级(禁追)
  财报后 ≤EARNINGS_POST_DAYS 日 → 📊 价格发现观察期, 财报前的旧形态失效
财报日期用 yfinance 拉取, 按「纽约日期」缓存一天(.cache_earnings.json)。
"""
import datetime as dt
import json
import re
from pathlib import Path

from . import config as C
from .data import NY

CACHE = Path(__file__).resolve().parent / ".cache_earnings.json"


JSON_CAL = Path(__file__).resolve().parent / "earnings_calendar.json"


def _from_json() -> dict:
    """随仓库分发的财报日历快照（由 xlsx 导出, 供 CI 环境使用）"""
    if not JSON_CAL.exists():
        return {}
    try:
        return json.loads(JSON_CAL.read_text())
    except json.JSONDecodeError:
        return {}


def _from_xlsx() -> dict:
    """用户自维护《宏观×财报事件日历》—— 比 yahoo 可靠, 作为权威加成源。
    本地有 xlsx 用 xlsx（最新）; CI 里没有则回退随仓库的 JSON 快照。"""
    if not C.EARNINGS_XLSX.exists():
        return _from_json()
    try:
        import pandas as pd
        df = pd.read_excel(C.EARNINGS_XLSX, header=1)
    except Exception:
        return {}
    year = _ny_today().year
    out = {}
    er = df[df["类型"].astype(str).str.contains("财报", na=False)]
    for _, r in er.iterrows():
        m = re.search(r"\(([A-Z]{1,6})\)", str(r["事件"]))
        dm = re.match(r"(\d{1,2})/(\d{1,2})", str(r["日期"]).strip())
        if not m or not dm:
            continue                      # "约7月底"这类模糊日期跳过
        try:
            d = dt.date(year, int(dm.group(1)), int(dm.group(2)))
        except ValueError:
            continue
        out.setdefault(m.group(1), set()).add(d.isoformat())
    return {k: sorted(v) for k, v in out.items()}


def _ny_today() -> dt.date:
    return dt.datetime.now(NY).date()


def _fetch(tickers) -> dict:
    import yfinance as yf
    out = {}
    for tk in tickers:
        try:
            df = yf.Ticker(tk).get_earnings_dates(limit=12)
            out[tk] = ([] if df is None or df.empty
                       else sorted({d.date().isoformat() for d in df.index}))
        except Exception:
            out[tk] = []          # ETF/指数无财报, 或接口抖动
    return out


def load(tickers, force=False) -> dict:
    """三层合并: yfinance(缓存一天) + 自维护xlsx日历 + config手工覆盖"""
    today = _ny_today().isoformat()
    yf_dates = None
    if CACHE.exists() and not force:
        try:
            c = json.loads(CACHE.read_text())
            if c.get("fetched") == today and set(tickers) <= set(c.get("dates", {})):
                yf_dates = c["dates"]
        except (json.JSONDecodeError, KeyError):
            pass
    if yf_dates is None:
        print("拉取观察池财报日历 ...")
        yf_dates = _fetch(tickers)
        CACHE.write_text(json.dumps({"fetched": today, "dates": yf_dates},
                                    ensure_ascii=False, indent=1))
    merged = {tk: set(v) for tk, v in yf_dates.items()}
    for src in (_from_xlsx(), C.EARNINGS_OVERRIDE):
        for tk, ds in src.items():
            merged.setdefault(tk, set()).update(ds)
    for tk, ds in getattr(C, "EARNINGS_REMOVE", {}).items():   # 人工核实过的错误日期
        merged.get(tk, set()).difference_update(ds)
    return {tk: sorted(v) for tk, v in merged.items()}


def flags(tickers) -> dict:
    """{代码: 警示文本} —— 只包含处于财报风险窗口内的标的"""
    dates = load(tickers)
    today = _ny_today()
    out = {}
    for tk in tickers:
        ds = [dt.date.fromisoformat(x) for x in dates.get(tk, [])]
        if not ds:
            continue
        future = [d for d in ds if d >= today]
        past = [d for d in ds if d < today]
        if past and (today - max(past)).days <= C.EARNINGS_POST_DAYS:
            n = (today - max(past)).days
            out[tk] = f"📊 财报后第{n}日({max(past):%m-%d}), 价格发现期, 旧形态失效"
        elif future and (min(future) - today).days <= C.EARNINGS_PRE_DAYS:
            n = (min(future) - today).days
            when = "今日(盘后?)" if n == 0 else f"{n}日后({min(future):%m-%d})"
            out[tk] = f"⚠️ {when}财报, 信号降级禁追"
        elif not future and past and (today - max(past)).days > C.EARNINGS_STALE_DAYS:
            # yahoo缺漏下次财报日, 但按季度节奏已到窗口（AMD 2026-08 教训）
            out[tk] = (f"❓ 财报日数据缺失(上次{max(past):%m-%d}距今"
                       f"{(today - max(past)).days}天), 季度节奏已到窗口, 需人工核实")
    return out


def upcoming(tickers, days=14) -> list:
    """未来 N 日财报日历: [(日期, 代码), ...] 按日期排序"""
    dates = load(tickers)
    today = _ny_today()
    cal = []
    for tk in tickers:
        for x in dates.get(tk, []):
            d = dt.date.fromisoformat(x)
            if 0 <= (d - today).days <= days:
                cal.append((d, tk))
    return sorted(cal)
