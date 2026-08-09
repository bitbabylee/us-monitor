# -*- coding: utf-8 -*-
"""
一键运行全部模块：
    python3 -m us_monitor.run_all              # 全部（含日内）
    python3 -m us_monitor.run_all --no-intraday  # 只跑日线（收盘后复盘用）

最后的【板块共振 Cross-Check】会把个股买点信号和所在板块/主题的资金方向对齐，
只有获得板块确认的信号才进入「今日聚焦清单」——这就是自动缩减标的的逻辑。
"""
import sys
import warnings
warnings.filterwarnings("ignore", category=FutureWarning)

import pandas as pd
from . import config as C
from . import earnings
from .data import fetch_daily, fetch_intraday
from . import (m1_macro, m2_sectors, m3_themes, m4_watchlist, m5_intraday,
               m7_gao, m8_alerts, m9_premarket, m10_camslim)


def compute_crosscheck(sec_df, theme_df, wl_df):
    """板块共振过滤：日线形态 + (板块Alpha>0 或 主题Alpha>0) 才保留。
    返回 (keep, drop)，元素为 (代码, 形态, 上下文说明)。"""
    sec_alpha = dict(zip(sec_df["代码"], sec_df["超额Alpha"]))
    ticker_theme = {}
    for theme, members in C.THEMES.items():
        for tk in members:
            ticker_theme.setdefault(tk, theme)
    theme_alpha = dict(zip(theme_df["主题"], theme_df["超额Alpha"]))

    keep, drop = [], []
    for _, r in wl_df[wl_df["标记"] != "⚪"].iterrows():
        tk = r["代码"]
        etf = C.TICKER_SECTOR.get(tk, "XLK")
        sa = sec_alpha.get(etf, 0.0)
        th = ticker_theme.get(tk)
        ta = theme_alpha.get(th) if th else None
        eflag = r["财报"] if "财报" in r.index else ""
        confirmed = (sa > 0 or (ta is not None and ta > 0)) and not eflag
        ctx = f"板块{etf} α={sa:+.2f}%" + (f" | 主题「{th}」α={ta:+.2f}%" if ta is not None else "")
        if eflag:
            ctx = f"{eflag} | {ctx}"          # 财报窗口一票否决, 优先展示原因
        (keep if confirmed else drop).append((tk, r["形态"], ctx))
    return keep, drop


def cross_check(sec_df, theme_df, wl_df, intra_df):
    keep, drop = compute_crosscheck(sec_df, theme_df, wl_df)
    print("=" * 96)
    print("【板块共振 Cross-Check — 自动缩减聚焦清单】")
    if not keep and not drop:
        print("👉 今日无日线形态信号, 无需过滤")
        print("=" * 96)
        return
    for tk, pat, ctx in keep:
        print(f"✅ 保留 {tk:>5} {pat} — 板块资金确认（{ctx}）")
    for tk, pat, ctx in drop:
        reason = "财报风险窗口" if "财报" in ctx else "板块资金背离"
        print(f"⛔ 降级 {tk:>5} {pat} — {reason}, 仅观察不追（{ctx}）")
    if intra_df is not None and not intra_df.empty and keep:
        sig = dict(zip(intra_df["代码"], intra_df["信号"]))
        print("-" * 96)
        print("👉 聚焦清单 × 日内信号:")
        for tk, _, _ in keep:
            print(f"   {tk:>5}: {sig.get(tk, '（无日内数据）')}")
    print("=" * 96)


def main():
    with_intraday = "--no-intraday" not in sys.argv

    print("正在批量拉取日线数据 ...")
    daily = fetch_daily(C.all_daily_tickers())

    m1_macro.run(daily)
    print()
    m10_camslim.run(daily)
    print()
    gao = m7_gao.run(daily)
    print()
    m8_alerts.run(daily, gao)
    print()
    m9_premarket.run(daily)
    print()
    sec_df = m2_sectors.run(daily)
    print()
    theme_df = m3_themes.run(daily)
    print()
    wl_df = m4_watchlist.run(daily)
    print()

    # 财报雷达: 未来两周观察池财报日历
    cal = earnings.upcoming(C.WATCHLIST, days=14)
    print("=" * 96)
    print("【财报雷达 — 观察池未来14日财报日历】")
    if cal:
        for d, tk in cal:
            print(f"📅 {d:%m-%d} ({['周一','周二','周三','周四','周五','周六','周日'][d.weekday()]})  {tk}")
    else:
        print("👉 未来14日观察池无财报")
    print("=" * 96)
    print()

    intra_df = None
    if with_intraday:
        print("正在拉取观察池 5 分钟级数据 ...")
        intra = fetch_intraday(C.WATCHLIST)
        intra_df = m5_intraday.run(intra, daily)
        print()

    cross_check(sec_df, theme_df, wl_df, intra_df)


if __name__ == "__main__":
    main()
