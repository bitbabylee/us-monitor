# -*- coding: utf-8 -*-
"""
模块9：盘前/盘后雷达 —— 把延长时段(4:00-9:30 盘前 / 16:00-20:00 盘后)纳入视野。

解决的问题：日线和日内模块都只看正常时段, 而财报反应发生在盘后/盘前
(AMD 8/4 盘后财报跳水就是例子)。本模块在开盘前就把异动摆到台面上。
"""
import datetime as dt

import numpy as np
import pandas as pd

from . import config as C
from . import earnings
from .data import col, fetch_extended, NY


def run(daily: pd.DataFrame) -> pd.DataFrame:
    ext = fetch_extended(C.WATCHLIST)
    eflags = earnings.flags(C.WATCHLIST)
    rows = []
    for tk in C.WATCHLIST:
        try:
            base_s = col(daily, "Close", tk)
            base = base_s.iloc[-1]                     # 最近完结日收盘
            base_day = base_s.index[-1].date()
            c = col(ext, "Close", tk)
            v = col(ext, "Volume", tk)
        except (KeyError, IndexError):
            continue
        if c.empty:
            continue
        # 正常时段收盘之后的所有 bars = 延长时段（盘后+隔夜盘前）
        cutoff = pd.Timestamp(base_day, tz=NY) + pd.Timedelta(hours=16)
        after = c[c.index > cutoff]
        if after.empty:
            continue
        last_t = after.index[-1]
        px = after.iloc[-1]
        chg = (px / base - 1) * 100
        vol = v[v.index > cutoff].sum()
        session = "盘前" if last_t.time() >= dt.time(4, 0) and last_t.time() < dt.time(9, 30) \
            and last_t.date() > base_day else "盘后"
        rows.append((tk, base, px, chg, vol, session,
                     last_t.strftime("%m-%d %H:%M"), eflags.get(tk, "")))

    if not rows:
        print("盘前雷达: 暂无延长时段数据（盘前 4:00 ET 后再跑）")
        return pd.DataFrame()

    df = pd.DataFrame(rows, columns=["代码", "昨收", "延长价", "涨跌", "量",
                                     "时段", "最后成交", "财报"])
    df = df.reindex(df["涨跌"].abs().sort_values(ascending=False).index)

    ny = dt.datetime.now(NY).strftime("%m-%d %H:%M")
    print("=" * 96)
    print(f"【盘前/盘后雷达 — 延长时段异动】 (纽约时间 {ny})")
    print(f"{'代码':>5} {'昨收':>9} {'延长价':>9} {'延长涨跌':>7} {'时段':>4} "
          f"{'最后成交':>12}  异动/财报标记")
    for _, r in df.iterrows():
        mark = ""
        if abs(r["涨跌"]) >= C.EXT_MOVE_ALERT:
            mark = "🚨 " if r["涨跌"] < 0 else "🔥 "
        efl = f" ‼️{r['财报']}" if r["财报"] else ""
        print(f"{r['代码']:>5} {r['昨收']:>9.2f} {r['延长价']:>9.2f} {r['涨跌']:>+7.2f}% "
              f"{r['时段']:>4} {r['最后成交']:>12}  {mark}{efl}")
    movers = df[df["涨跌"].abs() >= C.EXT_MOVE_ALERT]
    print("-" * 96)
    if movers.empty:
        print("👉 延长时段无显著异动(±2%)")
    else:
        for _, r in movers.iterrows():
            print(f"👉 {r['代码']} {r['时段']}{r['涨跌']:+.1f}%"
                  f"{' — ' + r['财报'] if r['财报'] else ''} — 开盘前重设该标的的日线信号预期")
    print("=" * 96)
    return df
