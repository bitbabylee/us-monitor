# -*- coding: utf-8 -*-
"""
模块7：高老师【📐 双指数阶段日报】(QQQ=大盘, SMH=进攻先锋)

两道关卡, 必选题一票否决:
  第一关「恐慌释放」4题: 跌势止住了吗?  通过=必选✓ 且 ≥3/4
  第二关「资金共识」5题: 买家回来了吗?  进C1=两道必选✓ 且 ≥3/5
阶段: P0 恐慌未释放 → P1 恐慌已释放 → C1 资金共识(可分批试仓)
外加宏观确认层(Brendon五信号自动化): ATR14分位 / 10Y美债 / HYG,LQD信用 / CTA(人工)
"""
import numpy as np
import pandas as pd

from . import config as C
from .data import col
from .indicators import pct


def _atr_pctl(high, low, close, n=14, window=252):
    pc = close.shift()
    tr = pd.concat([high - low, (high - pc).abs(), (low - pc).abs()], axis=1).max(axis=1)
    atr = tr.rolling(n).mean().dropna()
    tail = atr.iloc[-window:]
    return (tail <= atr.iloc[-1]).mean() * 100


def _no_new_low_2d(low, lookback):
    """连续两日不创新低: 昨/今最低价均高于此前的阶段低点"""
    return (low.iloc[-1] > low.iloc[-lookback:-1].min()
            and low.iloc[-2] > low.iloc[-lookback:-2].min())


def _vol_reversal(close, open_, vol, win, volx):
    """近win日内存在放量反转日: 收阳且量>volx×20日均量"""
    avg = vol.rolling(20).mean().shift(1)
    for i in range(-win, 0):
        if close.iloc[i] > open_.iloc[i] and vol.iloc[i] > volx * avg.iloc[i]:
            return True
    return False


def _breakout20_vol(close, vol, volx):
    """近3日内收盘上穿20日线且放量"""
    ma20 = close.rolling(20).mean()
    avg = vol.rolling(20).mean().shift(1)
    for i in range(-3, 0):
        if (close.iloc[i] > ma20.iloc[i] and close.iloc[i - 1] <= ma20.iloc[i - 1]
                and vol.iloc[i] > volx * avg.iloc[i]):
            return True
    return False


def run(daily: pd.DataFrame) -> dict:
    q_c, q_o = col(daily, "Close", "QQQ"), col(daily, "Open", "QQQ")
    q_h, q_l, q_v = col(daily, "High", "QQQ"), col(daily, "Low", "QQQ"), col(daily, "Volume", "QQQ")
    s_c, s_o = col(daily, "Close", "SMH"), col(daily, "Open", "SMH")
    s_l, s_v = col(daily, "Low", "SMH"), col(daily, "Volume", "SMH")

    ratio = (s_c / q_c).dropna()
    r_ma20 = ratio.rolling(20).mean()
    lb = C.GAO_LOW_LOOKBACK

    # ── 第一关: 恐慌释放 (4题, #1必选) ──
    panic = [
        ("QQQ与SMH连续两日不创新低(必选)",
         _no_new_low_2d(q_l, lb) and _no_new_low_2d(s_l, lb), True),
        ("至少一指数放量反转",
         _vol_reversal(q_c, q_o, q_v, C.GAO_REVERSAL_WIN, C.GAO_REVERSAL_VOLX)
         or _vol_reversal(s_c, s_o, s_v, C.GAO_REVERSAL_WIN, C.GAO_REVERSAL_VOLX), False),
        ("双指数收复5日线",
         q_c.iloc[-1] > q_c.rolling(5).mean().iloc[-1]
         and s_c.iloc[-1] > s_c.rolling(5).mean().iloc[-1], False),
        ("SMH/QQQ相对强弱连续两日回升",
         ratio.iloc[-1] > ratio.iloc[-2] > ratio.iloc[-3], False),
    ]
    # ── 第二关: 资金共识 (5题, #1#4必选) ──
    consensus = [
        ("QQQ站上20日线(必选)",
         q_c.iloc[-1] > q_c.rolling(20).mean().iloc[-1], True),
        ("SMH站上20日线",
         s_c.iloc[-1] > s_c.rolling(20).mean().iloc[-1], False),
        ("双指数五日收益率均为正",
         pct(q_c.iloc[-1], q_c.iloc[-6]) > 0 and pct(s_c.iloc[-1], s_c.iloc[-6]) > 0, False),
        ("ratio站上20日均值且三日斜率向上(必选)",
         ratio.iloc[-1] > r_ma20.iloc[-1] and ratio.iloc[-1] > ratio.iloc[-3], True),
        ("近三日突破20日线伴随放量",
         _breakout20_vol(q_c, q_v, C.GAO_BREAKOUT_VOLX)
         or _breakout20_vol(s_c, s_v, C.GAO_BREAKOUT_VOLX), False),
    ]
    p_score = sum(ok for _, ok, _ in panic)
    c_score = sum(ok for _, ok, _ in consensus)
    p_must = all(ok for _, ok, must in panic if must)
    c_must = all(ok for _, ok, must in consensus if must)
    panic_pass = p_must and p_score >= 3
    c1 = panic_pass and c_must and c_score >= 3

    phase = ("C1 资金共识" if c1 else "P1 恐慌已释放" if panic_pass else "P0 恐慌未释放")

    # 人话版
    if c1:
        human = "先锋与大盘双确认, 可按纪律分批试仓; 跌破失效位无条件退出。"
    elif panic_pass:
        miss = "与".join(n.replace("(必选)", "") for n, ok, _ in consensus if not ok)
        human = (f"跌势基本止住{', QQQ 已站上 20 日线' if consensus[0][1] else ''};"
                 f"还差{miss}确认(共识 {c_score}/5, 进C1需3/5+必选)。不买, 等。")
    else:
        miss = "与".join(n.replace("(必选)", "") for n, ok, _ in panic if not ok)
        human = f"恐慌未完全释放({p_score}/4), 还差{miss}。空仓/防守, 不接飞刀。"

    # 核心值与失效位（=本轮最低收盘价, 对齐原版口径）
    stop_q, stop_s = q_c.iloc[-lb:].min(), s_c.iloc[-lb:].min()

    # ── 宏观确认层 ──
    atr_p = _atr_pctl(q_h, q_l, q_c)
    atr_ok = atr_p < C.GAO_ATR_PCTL_PASS
    try:
        raw = col(daily, "Close", "^TNX").iloc[-1]
        tnx = raw / 10 if raw > 20 else raw     # ^TNX 历史上是收益率×10, 现为直接收益率
        tnx_ok = tnx <= C.GAO_TNX_PASS
    except (KeyError, IndexError):
        tnx, tnx_ok = np.nan, False
    hyg = (col(daily, "Close", "HYG") / col(daily, "Close", "LQD")).dropna()
    hyg_chg = hyg.iloc[-1] / hyg.iloc[-6] - 1
    hyg_ok = hyg_chg > C.GAO_HYG_TOL
    # 日元套息风控: USD/JPY 跌破支撑 = 借日元的杠杆被迫平仓, 无差别抛售风险资产
    try:
        jpy_s = col(daily, "Close", "JPY=X")
        jpy = jpy_s.iloc[-1]
        jpy_5d = (jpy / jpy_s.iloc[-6] - 1) * 100
        jpy_ok = jpy > C.JPY_WATCH          # 高于观察带 = 套息环境暂稳
    except (KeyError, IndexError):
        jpy, jpy_5d, jpy_ok = np.nan, np.nan, False

    d = q_c.index[-1].strftime("%Y-%m-%d")

    def mk(ok):
        return "✅" if ok else "✗"

    print("=" * 64)
    print(f"信号预警|📐 双指数阶段日报 | 数据截至 {d}")
    print(f"阶段判定:{phase}")
    print(f"恐慌释放 {p_score}/4 | 资金共识 {c_score}/5")
    print(f"▎人话版:{human}")
    print("▎读法:第一关'跌势止住了吗'(4题,必选题一票否决)→ 第二关'买家回来了吗'(5题)。"
          "QQQ=大盘,SMH=进攻先锋,真反弹必须先锋带头。")
    print()
    print("【恐慌释放】")
    for name, ok, _ in panic:
        print(f"{mk(ok)} {name}")
    print("【资金共识】")
    for name, ok, _ in consensus:
        print(f"{mk(ok)} {name}")
    print()
    print(f"核心值:QQQ {q_c.iloc[-1]:.2f}(5日{q_c.rolling(5).mean().iloc[-1]:.2f}"
          f"/10日{q_c.rolling(10).mean().iloc[-1]:.2f}/20日{q_c.rolling(20).mean().iloc[-1]:.2f})")
    print(f"       SMH {s_c.iloc[-1]:.2f}(5日{s_c.rolling(5).mean().iloc[-1]:.2f}"
          f"/10日{s_c.rolling(10).mean().iloc[-1]:.2f}/20日{s_c.rolling(20).mean().iloc[-1]:.2f})")
    print(f"       SMH/QQQ={ratio.iloc[-1]:.4f}(20日均{r_ma20.iloc[-1]:.4f})")
    print(f"失效位:QQQ<{stop_q:.2f} 或 SMH<{stop_s:.2f}")
    op = ("分批试仓, 破失效位无条件退出" if c1 else
          "等待资金共识(站上20日线+ratio翻多), 仍不追高" if panic_pass else
          "防守为主, 等恐慌释放四条件")
    print(f"操作含义:{op}")
    print()
    tnx_txt = "N/A" if np.isnan(tnx) else f"{tnx:.2f}%"
    jpy_txt = "N/A" if np.isnan(jpy) else f"{jpy:.2f}"
    jpy_state = ("N/A" if np.isnan(jpy) else
                 f"🚨已跌破{C.JPY_SUPPORT}支撑, 套息平仓螺旋风险" if jpy < C.JPY_SUPPORT else
                 f"⚠️逼近{C.JPY_SUPPORT}支撑, 警戒" if jpy < C.JPY_WATCH else
                 f"支撑{C.JPY_SUPPORT}上方 {jpy - C.JPY_SUPPORT:+.2f}")
    # 每项: (信号号, 名称, 当前值, 阈值条件, 差距, 通过?, 含义)
    macro = [
        ("#4", "ATR14 一年分位", f"{atr_p:.0f}%", f"< {C.GAO_ATR_PCTL_PASS}%",
         f"高 {atr_p - C.GAO_ATR_PCTL_PASS:.0f} 个百分点" if not atr_ok
         else f"低 {C.GAO_ATR_PCTL_PASS - atr_p:.0f} 个百分点", atr_ok,
         "波动收敛=恐慌定价消退"),
        ("#5a", "10Y 美债收益率", tnx_txt, f"≤ {C.GAO_TNX_PASS}%",
         "N/A" if np.isnan(tnx) else
         (f"高 {tnx - C.GAO_TNX_PASS:.2f} 个百分点" if not tnx_ok
          else f"低 {C.GAO_TNX_PASS - tnx:.2f} 个百分点"), tnx_ok,
         "利率压制解除(博主确认位#2)"),
        ("#5b", "HYG/LQD 信用利差", f"{hyg.iloc[-1]:.4f}", f"5日变化 > {C.GAO_HYG_TOL*100:+.1f}%",
         f"实际 {hyg_chg*100:+.2f}%", hyg_ok, "垃圾债未被抛售=无系统性风险"),
        ("加", "USD/JPY 套息开关", jpy_txt, f"> {C.JPY_WATCH:.0f}（破 {C.JPY_SUPPORT} 告警）",
         "N/A" if np.isnan(jpy) else f"5日 {jpy_5d:+.1f}%; {jpy_state}", jpy_ok,
         "日元升值→套息平仓→全球去杠杆"),
    ]
    passed = sum(1 for m in macro if m[5])
    print(f"【宏观确认层(Brendon五信号自动化) — 通过 {passed}/{len(macro)} 项】")
    print(f"{'':2}{'信号':<5}{'指标':<18}{'当前值':>9}  {'通过条件':<22}{'判定':<5} 差距/说明")
    for sid, name, cur, cond, gap, ok, why in macro:
        print(f"{mk(ok)} {sid:<5}{name:<18}{cur:>9}  {cond:<22}{'满足' if ok else '不满足':<5} {gap}")
        print(f"{'':7}└─ 含义: {why}")
    from . import cta as _cta
    cta_r = _cta.estimate(daily)
    _cta.render_console(cta_r)
    print(f"→ 环境判定: {'✅ 宏观环境支持加仓' if passed >= 3 else '⚠️ 宏观仍有压制, 谨慎' if passed >= 2 else '🚨 宏观环境不利, 防守'}")
    print("=" * 64)

    return {"phase": phase, "panic": panic, "consensus": consensus,
            "p_score": p_score, "c_score": c_score, "human": human,
            "qqq": q_c.iloc[-1], "smh": s_c.iloc[-1],
            "ratio": ratio.iloc[-1], "ratio_ma20": r_ma20.iloc[-1],
            "stop_q": stop_q, "stop_s": stop_s,
            "atr_pctl": atr_p, "atr_ok": atr_ok,
            "tnx": tnx, "tnx_ok": tnx_ok,
            "hyg": hyg.iloc[-1], "hyg_ok": hyg_ok,
            "jpy": jpy, "jpy_5d": jpy_5d, "jpy_ok": jpy_ok, "jpy_state": jpy_state,
            "macro": macro, "macro_passed": passed, "cta": cta_r, "date": d}
