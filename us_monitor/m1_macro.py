# -*- coding: utf-8 -*-
"""模块1：美股每日量化诊断简报（SPX 偏离度 / RSI / VIX / MTUM÷MAGS 因子轮动）"""
import pandas as pd
from . import config as C
from .data import col
from .indicators import rsi, pct


def run(daily: pd.DataFrame) -> dict:
    spx = col(daily, "Close", "^GSPC")
    vix = col(daily, "Close", "^VIX").iloc[-1]
    mtum_s = col(daily, "Close", "MTUM")
    mags_s = col(daily, "Close", "MAGS")

    spx_curr = spx.iloc[-1]
    dev50 = pct(spx_curr, spx.rolling(50).mean().iloc[-1])
    r = rsi(spx).iloc[-1]
    # 因子轮动：MTUM/MAGS 是价格比值, 绝对水平无意义（原版固定阈值1.25恒真）,
    # 改用比值相对自身 20 日均线的趋势方向判断
    ratio = (mtum_s / mags_s).dropna()
    rs, rs_ma = ratio.iloc[-1], ratio.rolling(20).mean().iloc[-1]
    to_mtum = rs > rs_ma

    print("=" * 50)
    print(f"       美股每日量化诊断简报 [{spx.index[-1].strftime('%Y-%m-%d')}]")
    print("=" * 50)
    print(f"1. 标普500点位: {spx_curr:.2f} (50日均线偏离度: {dev50:+.2f}%)")
    print(f"2. 14日 RSI 动能: {r:.2f} ({'⚠️偏热/背离预警' if r > C.RSI_HOT else '中性健康'})")
    print(f"3. VIX 恐慌指数: {vix:.2f} ({'🚨去杠杆/避险升温' if vix > C.VIX_ALERT else '情绪平稳'})")
    print(f"4. 因子轮动 (MTUM/MAGS): {rs:.4f} (20日均线 {rs_ma:.4f}, "
          f"{'站上' if to_mtum else '跌破'})")
    print(f"   └─ 结论: {'🔥 资金偏向广义动量股 (MTUM)' if to_mtum else '💻 资金偏向七巨头抱团 (MAGS)'}")

    # 5. 日性质因子行: 因子ETF对SPY的当日超额(pct), 判别当天下跌/上涨的"性质"
    spy = col(daily, "Close", C.BENCHMARK).dropna()
    spy_d = (spy.iloc[-1] / spy.iloc[-2] - 1) * 100
    fac = {}
    for tk, nm in C.FACTOR_ETFS.items():
        try:
            s = col(daily, "Close", tk).dropna()
            if s.index[-1] != spy.index[-1]:
                continue                      # 数据滞后一天则跳过, 防日期错位假读数
            fac[nm] = (s.iloc[-1] / s.iloc[-2] - 1) * 100 - spy_d
        except Exception:
            pass
    mo, hb = fac.get("动量", 0), fac.get("高贝", 0)
    lv, va = fac.get("低波", 0), fac.get("价值", 0)
    nature = ("去杠杆/轮动日" if mo < -0.4 and hb < -0.3 else
              "避险日" if lv > 0.3 and hb < -0.3 else
              "风偏进攻日" if hb > 0.4 and mo > 0.2 else
              "价值轮动日" if va > 0.4 and mo < 0 else "中性日")
    if fac:
        print("5. 日性质: " + " ".join(f"{n}{v:+.1f}" for n, v in fac.items())
              + f" → {nature}")
    print("=" * 50)

    return {"spx": spx_curr, "dev50": dev50, "rsi": r, "vix": vix,
            "mtum_mags": rs, "mtum_mags_ma": rs_ma,
            "regime": "MTUM" if to_mtum else "MAGS",
            "factors": fac, "day_nature": nature}
