# -*- coding: utf-8 -*-
"""模块19：全市场主题雷达 —— 65 个主题 ETF 的 z-score 排序 + RRG 四象限。

解决的盲区: 观察池只有 27 只美股, 池外资金流向完全看不见(如 2026-08-11
资金从AI撤向石油/白银, 日报只有 XLE 一个入口)。
口径(借鉴沈老板主题榜):
  z = 当日涨跌 / 该ETF自身 RADAR_Z_WIN 日收益标准差
      —— 低波品种的小异动比高波品种的大异动更有信息量
  象限 = RS_long(vs SPY) × RS_short: 领/改/弱/落, "改善"格是下一棒候选池
只做发现与排序, 不产生买卖信号(个股信号仍只在 WATCHLIST 内)。
"""
from __future__ import annotations

import pandas as pd
import yfinance as yf

from . import config as C
from .data import col


def _load(daily=None):
    tks = list(C.RADAR_ETFS) + [C.BENCHMARK]
    if daily is not None:
        try:
            got = {t: col(daily, "Close", t).dropna() for t in tks}
            if all(len(s) > C.RADAR_RS_LONG + 2 for s in got.values()):
                return got
        except Exception:
            pass
    df = yf.download(tks, period="8mo", interval="1d", auto_adjust=True,
                     progress=False, group_by="column")["Close"]
    return {t: df[t].dropna() for t in tks if t in df.columns}


def run(daily=None) -> dict:
    px = _load(daily)
    spy = px.get(C.BENCHMARK)
    if spy is None or len(spy) < C.RADAR_RS_LONG + 2:
        print("【全市场主题雷达】基准数据不足, 跳过")
        return {"lines": [], "rows": []}

    def ret(s, n):
        return (s.iloc[-1] / s.iloc[-n - 1] - 1) * 100 if len(s) > n else float("nan")

    b_s, b_l = ret(spy, C.RADAR_RS_SHORT), ret(spy, C.RADAR_RS_LONG)
    rows = []
    for tk, name in C.RADAR_ETFS.items():
        s = px.get(tk)
        if s is None or len(s) < C.RADAR_Z_WIN + 2 or s.index[-1] != spy.index[-1]:
            continue                      # 日期不齐的直接跳过, 防错位假读数
        chg = (s.iloc[-1] / s.iloc[-2] - 1) * 100
        sd = s.pct_change().iloc[-C.RADAR_Z_WIN:].std() * 100
        z = chg / sd if sd else 0.0
        rs_s, rs_l = ret(s, C.RADAR_RS_SHORT) - b_s, ret(s, C.RADAR_RS_LONG) - b_l
        quad = ("领" if rs_l > 0 and rs_s > 0 else "改" if rs_s > 0
                else "弱" if rs_l > 0 else "落")
        rows.append({"tk": tk, "name": name, "chg": chg, "z": z,
                     "rs_s": rs_s, "rs_l": rs_l, "quad": quad})

    rows.sort(key=lambda r: -r["z"])
    n = C.RADAR_TOP_N
    top, bot = rows[:n], rows[-n:]
    improving = sorted([r for r in rows if r["quad"] == "改"],
                       key=lambda r: -r["rs_s"])[:6]
    cnt = {q: sum(1 for r in rows if r["quad"] == q) for q in "领改弱落"}

    fmt = lambda r: f"{r['name']}({r['tk']}) z{r['z']:+.1f}/{r['chg']:+.1f}%"
    print("=" * 96)
    print(f"【全市场主题雷达 — z-score 排序】{len(rows)} 个主题ETF · 只做发现不给信号")
    print(f"  象限分布: 领{cnt['领']} 改{cnt['改']} 弱{cnt['弱']} 落{cnt['落']}"
          f"  (领=长短RS双正, 改=长弱短强=下一棒候选)")
    print("  🔺今日最异常(强): " + " · ".join(fmt(r) for r in top))
    print("  🔻今日最异常(弱): " + " · ".join(fmt(r) for r in reversed(bot)))
    if improving:
        print("  📈改善象限(下一棒候选): "
              + " · ".join(f"{r['name']}({r['tk']}) 短RS{r['rs_s']:+.0f}%"
                           for r in improving))
    print("  口径: z = 当日涨跌 ÷ 自身60日波动 (低波品种小异动=高信息量)")
    print("=" * 96)

    from . import tv
    tv.warm(list(C.RADAR_ETFS))
    # 日报只说人话结论: 钱进/钱出(纯名字) + 下一棒候选(带可点符号, 符号后留空格防链接正则失配)
    lines = ["  钱进: " + "·".join(r["name"] for r in top)
             + "   钱出: " + "·".join(r["name"] for r in reversed(bot))]
    if improving:
        lines.append("  下一棒候选(长期落后·短期转强): "
                     + "  ".join(f"{tv.symbol(r['tk'])} {r['name']}" for r in improving[:5]))
    return {"lines": lines, "rows": rows, "improving": improving}


if __name__ == "__main__":
    run()
