# -*- coding: utf-8 -*-
"""模块2：美股板块【前一日交易异动与日度微观动能榜】"""
import pandas as pd
from . import config as C
from .data import col
from .indicators import last_metrics


def run(daily: pd.DataFrame) -> pd.DataFrame:
    bench = col(daily, "Close", C.BENCHMARK)
    rows = []
    for tk, name in C.SECTORS.items():
        close, vol = col(daily, "Close", tk), col(daily, "Volume", tk)
        if len(close) < 25:
            continue
        ret1, alpha1, volx, ex5 = last_metrics(close, vol, bench)
        # 日度微观得分：|超额| 越大、量倍越高越显眼（自定义，可调权重）
        score = abs(alpha1) * (0.5 + 0.5 * volx) + abs(ex5) * 0.3
        if alpha1 < C.SECTOR_DUMP_ALPHA and volx > C.SECTOR_DUMP_VOL:
            diag = "🚨 前一日【放量砸盘】"
        elif alpha1 > C.SECTOR_HOT_ALPHA:
            diag = "🔥 前一日显著跑赢大盘"
        else:
            diag = "平稳"
        rows.append((tk, name, ret1, alpha1, volx, ex5, score, diag))

    df = pd.DataFrame(rows, columns=["代码", "板块名称", "前一日涨跌", "超额Alpha",
                                     "量倍", "5日超额", "得分", "诊断"])
    df = df.sort_values("超额Alpha", ascending=False).reset_index(drop=True)

    date = bench.index[-1].strftime("%Y-%m-%d")
    print("=" * 96)
    print(f"        美股板块【前一日交易异动与日度微观动能榜】 [{date}]")
    print("=" * 96)
    print(f"{'代码':>5} {'板块名称':>22} {'前一日涨跌(%)':>10} {'1日超额Alpha(%)':>12} "
          f"{'成交量倍数':>8} {'5日超额(%)':>9} {'日度微观得分':>9}  诊断")
    for _, r in df.iterrows():
        print(f"{r['代码']:>5} {r['板块名称']:>24} {r['前一日涨跌']:>12.2f} {r['超额Alpha']:>14.2f} "
              f"{r['量倍']:>10.2f}x {r['5日超额']:>10.2f} {r['得分']:>11.2f}  {r['诊断']}")

    best = df.iloc[0]
    hot_vol = df.sort_values("量倍", ascending=False).iloc[0]
    print("-" * 96)
    print("【前一日资金异动核心结论】")
    print(f"👉 前一日相对大盘最强板块 : {best['板块名称']}（单日跑赢大盘 {best['超额Alpha']:.2f}%）")
    print(f"👉 前一日资金换手最剧烈板块: {hot_vol['板块名称']}（成交量达到平时 {hot_vol['量倍']:.2f}x）")
    print("=" * 96)
    return df
