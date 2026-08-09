# -*- coding: utf-8 -*-
"""
模块5：观察池【今日日内量价择时执行信号】(VWAP / ORB / 15m 结构)
信号优先级（从危险到机会）：
  🔴 规避/止损(破位走弱) → 🔴 锁定利润(15m结构破位) → 🔥 强主升浪(切勿卖飞)
  → 🟡 弱突破预警(缩量突破ORB) → 🟢 突破买点(ORB强动能) → 🟡 临近前高(谨防双顶)
  → 🟢 稳健买点(温和站回VWAP) → ⚪ 观望
"""
import pandas as pd
import numpy as np
from . import config as C
from .data import col
from .indicators import vwap_intraday, ema, pct


def _one(tk, intra: pd.DataFrame, prev_high: float, dclose: pd.Series = None):
    close = col(intra, "Close", tk)
    if close.empty:
        return None
    days = sorted({t.date() for t in close.index})
    today = days[-1]
    # 跳空幅度: 今日开盘 vs 前一交易日收盘（隔夜信息的量化）
    gap = np.nan
    if dclose is not None:
        prevs = dclose[[t.date() < today for t in dclose.index]]
        if len(prevs):
            first_open = col(intra, "Open", tk)
            first_open = first_open[[t.date() == today for t in first_open.index]]
            if len(first_open):
                gap = pct(first_open.iloc[0], prevs.iloc[-1])
    bars = pd.DataFrame({f: col(intra, f, tk) for f in
                         ["Open", "High", "Low", "Close", "Volume"]})
    tbars = bars[[t.date() == today for t in bars.index]]
    if len(tbars) < 1:
        return None

    vwap = vwap_intraday(tbars)
    price, vw = tbars["Close"].iloc[-1], vwap.iloc[-1]
    dev = pct(price, vw)

    n_orb = max(1, C.ORB_MINUTES // 5)          # 5m bars
    orb_ready = len(tbars) >= n_orb             # 开盘区间是否已成型(需30分钟)
    orb_high = tbars["High"].iloc[:n_orb].max()
    orb_low = tbars["Low"].iloc[:n_orb].min()
    day_low = tbars["Low"].min()
    runup = pct(price, day_low)

    # 15m 结构：重采样出 15m K线, 8EMA + 前一根 15m 低点
    b15 = tbars.resample("15min").agg({"High": "max", "Low": "min",
                                       "Close": "last", "Volume": "sum"}).dropna()
    e8 = ema(b15["Close"], 8) if len(b15) else pd.Series([price])
    struct_broken = len(b15) >= 3 and (price < e8.iloc[-1] or
                                       price < b15["Low"].iloc[-2])
    # 15m 量能：只取"已走完"的 15m 桶（不足3根5m的最后一桶是半桶, 剔除）,
    # 基线用前几个交易日「同一时段」的 15m 量中位数 —— 早盘量天然大, 全天混比会失真
    cnt = tbars["Close"].resample("15min").count()
    full = b15[cnt.reindex(b15.index, fill_value=0) >= 3]
    prior = bars[[t.date() != today for t in bars.index]]
    hist15 = prior["Volume"].resample("15min").sum()
    hist15 = hist15[hist15 > 0]
    vol15x = np.nan
    if len(full) and len(hist15) > 10:
        slot = full.index[-1].time()
        same_slot = hist15[[t.time() == slot for t in hist15.index]]
        base = same_slot.median() if len(same_slot) >= 3 else hist15.median()
        vol15x = full["Volume"].iloc[-1] / base

    near_high = prev_high and price >= prev_high * (1 - C.NEAR_HIGH_TOL) and price <= prev_high * 1.005

    # ── 决策树 ──
    if not orb_ready:
        # 开盘前30分钟: ORB 未成型, 只报位置不给突破/破位信号（避免噪音信号）
        elapsed = len(tbars) * 5
        sig = (f"⏳ 开盘 {elapsed} 分钟（区间未成型）",
               f"{'站上' if dev >= 0 else '低于'} VWAP(${vw:.2f}) {dev:+.2f}%, "
               f"需满 {C.ORB_MINUTES} 分钟才出 ORB 择时信号")
    elif price < orb_low or dev < C.DEV_STOPLOSS:
        sig = ("🔴 规避/止损（破位走弱）",
               f"跌破开盘低点(${orb_low:.2f})或低于 VWAP {C.DEV_STOPLOSS}%")
    elif dev > C.DEV_OVERBOUGHT:
        if struct_broken:
            sig = ("🔴 锁定利润（高位 15m 结构破位）",
                   f"偏离 VWAP {dev:+.1f}% 且跌破前一 15m 低点/8EMA, 分批锁润")
        else:
            sig = ("🔥 强主升浪（切勿卖飞!）",
                   f"偏离 VWAP {dev:+.1f}% 但 15m 结构未破, 移动止损至 15m 8EMA(${e8.iloc[-1]:.2f})")
    elif dev > C.DEV_TRIM and struct_broken:
        sig = ("🔴 锁定利润（高位 15m 结构破位）",
               f"偏离 VWAP {dev:+.1f}% 且跌破前一 15m 低点/8EMA, 分批锁润")
    elif price > orb_high and price > vw:
        if not np.isnan(vol15x) and vol15x < C.VOL15_WEAK:
            sig = ("🟡 弱突破预警（缩量突破 ORB）",
                   f"突破高点但量能仅({vol15x:.1f}x), 警惕诱多假突破")
        elif near_high:
            sig = ("🟡 警告: 临近前高（谨防双顶）",
                   f"从低点已拉升 {runup:+.1f}%, 切勿在前高附近追高")
        elif not np.isnan(vol15x) and vol15x >= C.VOL15_GOLD:
            sig = ("🟢 强动能买点（放量突破 ORB）",
                   f"放量({vol15x:.1f}x)突破开盘高点(${orb_high:.2f}), 强力主升浪")
        else:
            sig = ("🟢 突破买点（ORB动能）",
                   f"突破开盘高点(${orb_high:.2f})且站稳 VWAP, 主力控盘")
    elif near_high and runup > C.RUNUP_WARN:
        sig = ("🟡 警告: 临近前高（谨防双顶）",
               f"从低点已拉升 {runup:+.1f}%, 切勿在前高附近追高")
    elif 0 <= dev <= C.DEV_GOLD and not np.isnan(vol15x) and vol15x >= C.VOL15_GOLD:
        sig = ("🟢 黄金买点（放量站回 VWAP）",
               f"放量({vol15x:.1f}x)重新踩稳 VWAP(${vw:.2f}), 主力建仓反弹")
    elif 0 <= dev <= 0.5:
        sig = ("🟢 稳健买点（温和站回 VWAP）",
               f"踩稳 VWAP(${vw:.2f}), 量能温和, 可分批低吸")
    else:
        sig = ("⚪ 观望", "VWAP 下方弱势区间, 等待站回 VWAP")

    # ── 跳空闸门: 隔夜信息推翻/威胁日线买点前提 ──
    is_buy = sig[0].startswith(("🟢", "🔥"))
    if not np.isnan(gap) and is_buy:
        if gap <= -C.GAP_VOID:
            sig = ("🟡 跳空低开, 买点降级",
                   f"低开{gap:+.1f}%, 隔夜信息推翻日线买点前提; 原信号[{sig[0]}]压制, 等企稳再评估")
        elif gap >= C.GAP_CHASE:
            sig = (sig[0], sig[1] + f"; ⚠️高开{gap:+.1f}%勿追, 回踩 VWAP 确认再进")

    return dict(代码=tk, 现价=price, VWAP=vw, 偏离=dev, 量能15=vol15x,
                跳空=gap, 信号=sig[0], 细节=sig[1], session=str(today))


def run(intra: pd.DataFrame, daily: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for tk in C.WATCHLIST:
        try:
            dh = col(daily, "High", tk)
            prev_high = dh.iloc[-6:-1].max() if len(dh) > 6 else None  # 近5日前高
            r = _one(tk, intra, prev_high, dclose=col(daily, "Close", tk))
            if r:
                rows.append(r)
        except (KeyError, IndexError):
            continue
    if not rows:
        print("⚠️ 无日内数据（休市中?）")
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    print("=" * 96)
    print(f"【第四部分: {len(df)} 只专属观察池 — 今日日内量价择时执行信号】 "
          f"[session: {df['session'].iloc[0]}]")
    print(f"{'代码':>5} {'现价':>9} {'日内VWAP':>9} {'VWAP偏离':>7} {'跳空':>6} {'15m量能':>6}   "
          f"{'日内择时信号':<28} 择时战术细节")
    for _, r in df.iterrows():
        v15 = f"{r['量能15']:.1f}x" if not np.isnan(r["量能15"]) else "N/A"
        gp = f"{r['跳空']:+.1f}%" if not np.isnan(r["跳空"]) else "N/A"
        print(f"{r['代码']:>5} {r['现价']:>9.2f} {r['VWAP']:>9.2f} {r['偏离']:>+7.2f}% "
              f"{gp:>6} {v15:>6}   {r['信号']:<30} {r['细节']}")

    buys = df[df["信号"].str.startswith(("🟢", "🔥"))]["代码"].tolist()
    sells = df[df["信号"].str.startswith("🔴")]["代码"].tolist()
    print("-" * 96)
    print("【今日战术执行指令】")
    print(f"👉 重点关注买入机会标的 : {', '.join(buys) if buys else '无'}")
    print(f"👉 重点关注止盈/止损标的 : {', '.join(sells) if sells else '无'}")
    print("=" * 96)
    return df
