# -*- coding: utf-8 -*-
"""
模块11：筛选器 —— 复刻 TradingView 那套日内选股流水线, 跑在自定义股票池上。

三个扫描器:
  ① RVOL 扫描      相对量排序找异动 —— 今天谁真的有资金介入
  ② Compression    ADR% 收窄 + 基本面增长 —— 波动压缩=大幅波动的前夜
  ③ Gappers        跳空幅度 + 量能 —— 隔夜信息推动的标的

与系统其余部分的区别: m4/m5 是对固定观察池做深度分析(广度小深度大),
本模块是对大池子做快速扫描(广度大深度小), 扫出来的候选再喂给 cross-check/财报否决。

    python3 -m us_monitor.m11_screener              # 全部三个扫描
    python3 -m us_monitor.m11_screener --rvol       # 只跑 RVOL
    python3 -m us_monitor.m11_screener --universe sp  # 换池子
"""
import sys
import warnings

import numpy as np
import pandas as pd

from . import config as C
from . import earnings
from .data import fetch_daily, fetch_extended, col, NY

warnings.filterwarnings("ignore")


def _adr_pct(high, low, n):
    """ADR% = 近n日 (最高/最低-1) 的均值 —— 日均波幅, 衡量这只票平时多能折腾"""
    return ((high / low - 1) * 100).rolling(n).mean()


def build_metrics(daily: pd.DataFrame, universe) -> pd.DataFrame:
    """给池子里每只票算一行指标"""
    bench = col(daily, "Close", C.BENCHMARK)
    rows = []
    for tk in universe:
        try:
            c, v = col(daily, "Close", tk), col(daily, "Volume", tk)
            h, l, o = col(daily, "High", tk), col(daily, "Low", tk), col(daily, "Open", tk)
            if len(c) < C.SCR_ADR_LONG + 2:
                continue
        except (KeyError, IndexError):
            continue
        avg_v = v.rolling(C.SCR_VOL_WIN).mean().shift(1).iloc[-1]
        if not avg_v or np.isnan(avg_v):
            continue
        adr_s, adr_l = _adr_pct(h, l, C.SCR_ADR_SHORT), _adr_pct(h, l, C.SCR_ADR_LONG)
        rows.append(dict(
            代码=tk, 收盘=c.iloc[-1],
            涨跌=(c.iloc[-1] / c.iloc[-2] - 1) * 100,
            开盘后=(c.iloc[-1] / o.iloc[-1] - 1) * 100,
            RVOL=v.iloc[-1] / avg_v,
            均量=avg_v,
            ADR短=adr_s.iloc[-1], ADR长=adr_l.iloc[-1],
            压缩比=adr_s.iloc[-1] / adr_l.iloc[-1] if adr_l.iloc[-1] else np.nan,
            距20日高=(c.iloc[-1] / c.iloc[-21:].max() - 1) * 100,
            YTD=(c.iloc[-1] / c.iloc[0] - 1) * 100,
        ))
    return pd.DataFrame(rows)


def scan_rvol(m: pd.DataFrame, top=15) -> pd.DataFrame:
    """① RVOL 扫描: 相对量异动排序"""
    d = m[m["RVOL"] >= C.SCR_RVOL_MIN].sort_values("RVOL", ascending=False).head(top)
    print("=" * 100)
    print(f"【① RVOL 扫描 — 相对量 ≥{C.SCR_RVOL_MIN} 的异动标的】"
          f"  RVOL=今日量÷{C.SCR_VOL_WIN}日均量, 越高=资金介入越明显")
    if d.empty:
        print("👉 无标的达到门槛")
    else:
        print(f"{'代码':>6} {'收盘':>9} {'涨跌':>8} {'RVOL':>7} {'ADR%':>7} {'距20日高':>8}")
        for _, r in d.iterrows():
            print(f"{r['代码']:>6} {r['收盘']:>9.2f} {r['涨跌']:>+7.2f}% {r['RVOL']:>6.2f}x "
                  f"{r['ADR长']:>6.2f}% {r['距20日高']:>+7.2f}%")
    print("=" * 100)
    return d


def scan_compression(m: pd.DataFrame, top=15) -> pd.DataFrame:
    """② Compression: 近期波幅明显小于长期 = 蓄势待发"""
    d = m[(m["压缩比"] <= C.SCR_COMPRESS_RATIO) & (m["ADR长"] >= C.SCR_ADR_MIN)]
    d = d.sort_values("压缩比").head(top)
    print("=" * 100)
    print(f"【② Compression 扫描 — 波动压缩 ≤{C.SCR_COMPRESS_RATIO}】"
          f"  {C.SCR_ADR_SHORT}日ADR ÷ {C.SCR_ADR_LONG}日ADR, 越小=压得越紧, 突破越猛")
    if d.empty:
        print("👉 无标的达到门槛")
    else:
        print(f"{'代码':>6} {'收盘':>9} {'压缩比':>7} {'短ADR':>7} {'长ADR':>7} "
              f"{'RVOL':>6} {'距20日高':>8} {'YTD':>8}")
        for _, r in d.iterrows():
            print(f"{r['代码']:>6} {r['收盘']:>9.2f} {r['压缩比']:>6.2f} {r['ADR短']:>6.2f}% "
                  f"{r['ADR长']:>6.2f}% {r['RVOL']:>5.2f}x {r['距20日高']:>+7.2f}% {r['YTD']:>+7.1f}%")
        print("-" * 100)
        print("👉 读法: 压缩比越低=波动被压得越紧。配合「距20日高」看——贴近前高(>-3%)的压缩")
        print("   是最强形态(高位横盘不跌=惜售); 远离前高的压缩多是无人问津, 突破方向不确定。")
    print("=" * 100)
    return d


def scan_gappers(daily: pd.DataFrame, universe, top=15) -> pd.DataFrame:
    """③ Gappers: 延长时段跳空 + 量能"""
    ext = fetch_extended(universe)
    eflags = earnings.flags(universe)
    rows = []
    for tk in universe:
        try:
            base_s = col(daily, "Close", tk)
            base, base_day = base_s.iloc[-1], base_s.index[-1].date()
            c, v = col(ext, "Close", tk), col(ext, "Volume", tk)
        except (KeyError, IndexError):
            continue
        cutoff = pd.Timestamp(base_day, tz=NY) + pd.Timedelta(hours=16)
        after, vol_after = c[c.index > cutoff], v[v.index > cutoff]
        if after.empty:
            continue
        gap = (after.iloc[-1] / base - 1) * 100
        if abs(gap) < C.SCR_GAP_MIN:
            continue
        rows.append(dict(代码=tk, 昨收=base, 现价=after.iloc[-1], 跳空=gap,
                         延长量=vol_after.sum(), 财报=eflags.get(tk, "")))
    d = pd.DataFrame(rows)
    print("=" * 100)
    print(f"【③ Gappers 扫描 — 延长时段跳空 ≥{C.SCR_GAP_MIN}%】 盘前/盘后异动, 开盘前重设预期")
    if d.empty:
        print("👉 无标的达到门槛（或当前无延长时段数据）")
    else:
        d = d.reindex(d["跳空"].abs().sort_values(ascending=False).index).head(top)
        print(f"{'代码':>6} {'昨收':>9} {'现价':>9} {'跳空':>8} {'延长量':>10}  财报标记")
        for _, r in d.iterrows():
            mark = "🚨" if r["跳空"] <= -C.EXT_MOVE_ALERT else "🔥" if r["跳空"] >= C.EXT_MOVE_ALERT else "  "
            print(f"{r['代码']:>6} {r['昨收']:>9.2f} {r['现价']:>9.2f} {r['跳空']:>+7.2f}% "
                  f"{r['延长量']/1e3:>9.0f}K  {mark}{r['财报']}")
    print("=" * 100)
    return d


def get_universe(name="all"):
    """池子: all=观察池+主题+板块 / watch=只观察池 / theme=只主题"""
    if name == "watch":
        return list(dict.fromkeys(C.WATCHLIST))
    if name == "theme":
        return list(dict.fromkeys(t for m in C.THEMES.values() for t in m))
    return list(dict.fromkeys(
        C.WATCHLIST + [t for m in C.THEMES.values() for t in m] + list(C.SECTORS)))


def run(daily=None, universe_name="all", which=("rvol", "compress", "gap")) -> dict:
    uni = get_universe(universe_name)
    if daily is None:
        print(f"拉取 {len(uni)} 只标的日线 ...")
        daily = fetch_daily(uni + [C.BENCHMARK])
    m = build_metrics(daily, uni)
    out = {}
    if "rvol" in which:
        out["rvol"] = scan_rvol(m)
    if "compress" in which:
        out["compress"] = scan_compression(m)
    if "gap" in which:
        out["gap"] = scan_gappers(daily, uni)
    out["metrics"] = m
    return out


if __name__ == "__main__":
    args = sys.argv[1:]
    which = [w for w in ("rvol", "compress", "gap")
             if f"--{w}" in args] or ("rvol", "compress", "gap")
    uni = "all"
    if "--universe" in args:
        uni = args[args.index("--universe") + 1]
    run(universe_name=uni, which=which)
