# -*- coding: utf-8 -*-
"""模块3：自定义主题股票池【前一日微观异动与动能榜】"""
import pandas as pd
from . import config as C
from .data import col
from .indicators import last_metrics


def run(daily: pd.DataFrame) -> pd.DataFrame:
    bench = col(daily, "Close", C.BENCHMARK)
    rows = []
    for theme, members in C.THEMES.items():
        stats = []
        for tk in members:
            try:
                close, vol = col(daily, "Close", tk), col(daily, "Volume", tk)
                if len(close) < 25:
                    continue
                ret1, alpha1, volx, _ = last_metrics(close, vol, bench)
                stats.append((tk, ret1, alpha1, volx))
            except (KeyError, IndexError):
                continue
        if not stats:
            continue
        s = pd.DataFrame(stats, columns=["tk", "ret1", "alpha1", "volx"])
        leader = s.loc[s["ret1"].idxmax()]
        avg_a = s["alpha1"].mean()
        if avg_a > C.THEME_HOT_ALPHA:
            diag = "🔥 强势领涨"
        elif avg_a < C.THEME_WEAK_ALPHA:
            diag = "🧊 弱势领跌"
        else:
            diag = "平稳"
        rows.append((theme, s["ret1"].mean(), avg_a, s["volx"].mean(),
                     f"{leader['tk']} ({leader['ret1']:+.1f}%)", diag))

    df = pd.DataFrame(rows, columns=["主题", "均涨跌", "超额Alpha", "平均量倍", "领头羊", "诊断"])
    df = df.sort_values("超额Alpha", ascending=False).reset_index(drop=True)

    date = bench.index[-1].strftime("%Y-%m-%d")
    print("=" * 96)
    print(f"       自定义主题股票池【前一日微观异动与动能榜】 [{date}]")
    print("=" * 96)
    print(f"{'自定义组合主题':>28} {'前一日均涨跌(%)':>10} {'1日超额Alpha(%)':>10} "
          f"{'组合平均量倍':>8} {'组合内最强领头羊':>16}   异动诊断")
    for _, r in df.iterrows():
        print(f"{r['主题']:>30} {r['均涨跌']:>12.2f} {r['超额Alpha']:>14.2f} "
              f"{r['平均量倍']:>10.2f}x {r['领头羊']:>18}   {r['诊断']}")
    best = df.iloc[0]
    print("-" * 96)
    print(f"昨晚表现最强的主题板块 : 【{best['主题']}】")
    print(f"└─ 单日超额 Alpha: {best['超额Alpha']:.2f}%, 平均量倍: {best['平均量倍']:.2f}x, "
          f"最强龙头: {best['领头羊']}")
    print("=" * 96)
    return df
