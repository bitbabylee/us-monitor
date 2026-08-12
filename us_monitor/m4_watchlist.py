# -*- coding: utf-8 -*-
"""
模块4：26 只专属观察池
  第二部分：日线动能与 CMF 资金强流入 TOP5
  第三部分：日线 5 大经典买点形态触发表
      💡 Pocket Pivot 口袋支点 | 🟢 10EMA 强动能回调 | 🚀 超跌反弹起爆点
"""
import pandas as pd
from . import config as C
from . import earnings
from .data import col
from .indicators import rsi, ema, cmf, mfi, last_metrics


def _pattern(close, high, low, open_, vol):
    """日线 5 大经典买点。返回 (标记, 形态名, 细节说明)；
    优先级：口袋支点 > 箱体突破 > 10EMA回调 > 金叉启动 > 超跌反弹"""
    e10, e21 = ema(close, 10), ema(close, 21)
    r = rsi(close)
    up_day = close.iloc[-1] > open_.iloc[-1]

    # 💡 Pocket Pivot：今日收阳，且成交量 > 近 N 日所有阴线量的最大值
    down_mask = (close < open_).iloc[-C.PP_LOOKBACK - 1:-1]
    down_vols = vol.iloc[-C.PP_LOOKBACK - 1:-1][down_mask]
    max_down_vol = down_vols.max() if len(down_vols) else 0
    if up_day and close.iloc[-1] > e10.iloc[-1] and vol.iloc[-1] > max_down_vol > 0:
        return ("💡", "【Pocket Pivot 口袋支点】",
                f"阳线量({vol.iloc[-1]/1e6:.1f}M)超越近{C.PP_LOOKBACK}日最大阴线量, 机构暗中放量吸筹")

    # 📦 20日箱体突破：收盘创近20日新高 + 放量确认（分母不含当日, 避免自稀释）
    volx = vol.iloc[-1] / vol.rolling(20).mean().shift(1).iloc[-1]
    box_high = close.iloc[-21:-1].max()
    if up_day and close.iloc[-1] > box_high and volx > C.BREAKOUT_VOLX:
        return ("📦", "【20日箱体突破】",
                f"收盘(${close.iloc[-1]:.2f})突破近20日高点(${box_high:.2f}), 放量{volx:.1f}x确认")

    # 🟢 10EMA 强动能回调：多头排列，最低价踩到 10EMA 且缩量企稳
    trend_up = e10.iloc[-1] > e21.iloc[-1] and close.iloc[-1] > e21.iloc[-1]
    touched = low.iloc[-1] <= e10.iloc[-1] * (1 + C.EMA_TOUCH_TOL)
    shrink = vol.iloc[-1] < vol.rolling(20).mean().shift(1).iloc[-1]
    if trend_up and touched and shrink and close.iloc[-1] >= e10.iloc[-1] * 0.99:
        return ("🟢", "【10 EMA 强动能回调】",
                f"踩稳 10 EMA (${e10.iloc[-1]:.2f}), 缩量企稳")

    # 🌊 EMA10/21 金叉启动：短均线今日上穿长均线, 趋势转多初启
    if e10.iloc[-2] <= e21.iloc[-2] and e10.iloc[-1] > e21.iloc[-1] and close.iloc[-1] > e21.iloc[-1]:
        return ("🌊", "【EMA10/21 金叉启动】",
                f"EMA10(${e10.iloc[-1]:.2f})上穿 EMA21(${e21.iloc[-1]:.2f}), 趋势转多初启")

    # 🚀 超跌反弹起爆点：RSI 近日击穿超跌区后今日收阳
    if r.iloc[-3:].min() < C.OVERSOLD_RSI and up_day:
        return ("🚀", "【超跌反弹起爆点】",
                f"RSI({r.iloc[-1]:.1f}) 超跌后收阳, 引发修复超跌浪")

    return ("⚪", "无显性日线买点", "在正常日线轨道内震荡")


def run(daily: pd.DataFrame) -> pd.DataFrame:
    bench = col(daily, "Close", C.BENCHMARK)
    eflags = earnings.flags(C.WATCHLIST)
    rows = []
    for tk in C.WATCHLIST:
        try:
            close = col(daily, "Close", tk)
            high, low = col(daily, "High", tk), col(daily, "Low", tk)
            open_, vol = col(daily, "Open", tk), col(daily, "Volume", tk)
            # 五序列共同对齐: 各字段NaN模式可能不同(批量下载日期并集),
            # 不对齐会让布尔掩码索引错位崩溃
            sub = pd.concat({"c": close, "h": high, "l": low,
                             "o": open_, "v": vol}, axis=1).dropna()
            close, high, low = sub["c"], sub["h"], sub["l"]
            open_, vol = sub["o"], sub["v"]
            if len(close) < 30:
                continue
        except (KeyError, IndexError):
            print(f"  ⚠️ {tk} 无数据, 跳过（退市/改代码?）")
            continue
        ret1, alpha1, volx, ex5 = last_metrics(close, vol, bench)
        c = cmf(high, low, close, vol).iloc[-1]
        m = mfi(high, low, close, vol).iloc[-1]
        # 日线综合得分 = 超额 + 放量加成 + 资金流加成（权重可调）
        score = alpha1 + 5 * (volx - 1) + 10 * c
        mark, pat, detail = _pattern(close, high, low, open_, vol)
        rows.append((tk, close.iloc[-1], ret1, alpha1, volx, c, m, score,
                     ema(close, 10).iloc[-1], ema(close, 21).iloc[-1],
                     rsi(close).iloc[-1], mark, pat, detail, eflags.get(tk, "")))

    df = pd.DataFrame(rows, columns=["代码", "收盘价", "涨跌", "超额Alpha", "量倍", "CMF",
                                     "MFI", "得分", "EMA10", "EMA21", "RSI",
                                     "标记", "形态", "细节", "财报"])
    date = bench.index[-1].strftime("%Y-%m-%d")
    n = len(df)

    top5 = df.sort_values("得分", ascending=False).head(5)
    print("=" * 96)
    print(f"【第二部分: {n} 只专属观察池 — 日线动能与 CMF 资金强流入 TOP 5】 [{date}]")
    print(f"{'代码':>5} {'收盘价':>9} {'1日超额Alpha(%)':>12} {'成交量倍数':>8} "
          f"{'CMF资金流':>8} {'MFI指数':>7} {'日线综合得分':>10}")
    for _, r in top5.iterrows():
        print(f"{r['代码']:>5} {r['收盘价']:>9.2f} {r['超额Alpha']:>14.2f} {r['量倍']:>9.2f}x "
              f"{r['CMF']:>9.2f} {r['MFI']:>8.1f} {r['得分']:>11.2f}")

    print()
    print(f"【第三部分: {n} 只专属观察池 — 日线 5 大经典买点形态触发表】")
    print(f"{'代码':>5} {'最新价':>9} {'EMA10':>8} {'EMA21':>8} {'日线RSI':>6}   "
          f"{'日线形态买点诊断':<24} 量化细节说明")
    for _, r in df.iterrows():
        efl = f"  ‼️{r['财报']}" if r["财报"] else ""
        print(f"{r['代码']:>5} {r['收盘价']:>9.2f} {r['EMA10']:>8.2f} {r['EMA21']:>8.2f} "
              f"{r['RSI']:>7.1f}   {r['标记']} {r['形态']:<22} {r['细节']}{efl}")

    hits = df[df["标记"] != "⚪"]
    print("-" * 96)
    print("【日线战术选股结论】")
    if hits.empty:
        print("👉 今日观察池内无经典形态触发")
    for _, r in hits.iterrows():
        if r["财报"]:
            print(f"👉 {r['代码']}: {r['标记']} {r['形态']} → ‼️ 信号作废降级: {r['财报']}")
        else:
            print(f"👉 {r['代码']}: {r['标记']} {r['形态']} | {r['细节']}")
    print("=" * 96)
    return df
