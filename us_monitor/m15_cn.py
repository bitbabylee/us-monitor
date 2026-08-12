# -*- coding: utf-8 -*-
"""模块15：A股重演监控 —— 反转 vs 反弹五条件判定 + 四棒轮动表。

框架来源: 2026-08 策略会"H2 按 PCB→光→液冷→存储 重演"的可检验化:
  ① 龙头能否创新高      ② 量能结构(涨放量/跌缩量)
  ③ 扩散质量(龙头带队?) ④ 指数验证(上证 3946-3980/缺口3983-3996)
  ⑤ 海外锚(价格代理: TSM 20日动量 + SMH/QQQ 相对强弱)
⑤的台光电/台积电"月营收"与 CSP 指引无法日频自动化 → 价格代理+人工月检。
判定: 反转条件满足 ≥4 → 反转倾向; ≤1 → 反弹定性; 其余 → 中性观察。
数据: yfinance 直连(.SS/.SZ), 不走 IB(A股合约不在 IB 覆盖内)。
A股 15:00 收盘, 15:05(北京)前运行时丢弃当日未完成K线。
"""
from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf

from . import config as C

SH = ZoneInfo("Asia/Shanghai")
_NM = C.CN_NAMES.get


def _fetch() -> pd.DataFrame:
    tickers = sorted({t for m in C.CN_BATONS.values() for t in m}
                     | set(C.CN_LEADERS) | {C.CN_BENCH, C.CN_INDEX} | set(C.CN_ANCHORS))
    df = yf.download(tickers, period="8mo", interval="1d",
                     auto_adjust=True, progress=False, group_by="column", threads=True)
    now = dt.datetime.now(SH)
    if len(df) and df.index[-1].date() == now.date() and now.time() < dt.time(15, 5):
        df = df.iloc[:-1]                     # 当日A股K线未走完
    return df


def _close(df, tk):
    s = df["Close"][tk].dropna()
    return s if len(s) >= 30 else None


def _ret(s, n):
    return (s.iloc[-1] / s.iloc[-n - 1] - 1) * 100 if len(s) > n else float("nan")


def _c1_leader_high(df):
    """① 龙头 vs 前高(不含最近 CN_HIGH_SKIP 日的 CN_HIGH_WIN 日最高收盘)。"""
    items, n_break = [], 0
    for tk in C.CN_LEADERS:
        s = _close(df, tk)
        if s is None:
            items.append(f"{_NM(tk, tk)}无数据")
            continue
        ref = s.iloc[-(C.CN_HIGH_WIN + C.CN_HIGH_SKIP):-C.CN_HIGH_SKIP].max()
        dist = (s.iloc[-1] / ref - 1) * 100
        n_break += dist >= 0
        items.append(f"{_NM(tk, tk)}{dist:+.0f}%")
    ok = n_break >= 2
    return ok, f"距前高 {' '.join(items)}" + (" 突破" if ok else "")


def _c2_volume(df):
    """② 近 CN_VOLRATIO_N 日 涨日均量/跌日均量（龙头均值）。"""
    ratios = []
    for tk in C.CN_LEADERS:
        s = _close(df, tk)
        v = df["Volume"][tk].dropna() if s is not None else None
        if s is None or v is None or not len(v):
            continue
        chg = s.diff().iloc[-C.CN_VOLRATIO_N:]
        vv = v.reindex(chg.index)
        up, dn = vv[chg > 0], vv[chg < 0]
        if len(up) and len(dn) and dn.mean() > 0:
            ratios.append(up.mean() / dn.mean())
    if not ratios:
        return None, "量能数据不足"
    r = sum(ratios) / len(ratios)
    return r >= C.CN_VOLRATIO_OK, f"涨/跌量比 {r:.2f}x ({C.CN_VOLRATIO_N}日)"


def _c3_diffusion(df):
    """③ 龙头 5 日收益 vs 全棒池中位数 → 谁在带队。"""
    lead = [_ret(_close(df, t), C.CN_RS_N) for t in C.CN_LEADERS if _close(df, t) is not None]
    pool = [_ret(_close(df, t), C.CN_RS_N)
            for m in C.CN_BATONS.values() for t in m if _close(df, t) is not None]
    if not lead or not pool:
        return None, "扩散数据不足"
    lm = sum(lead) / len(lead)
    pm = sorted(pool)[len(pool) // 2]
    ok = lm >= pm
    return ok, f"龙头5日{lm:+.1f}% vs 池中位{pm:+.1f}% {'龙头带队' if ok else '补涨带队'}"


def _c4_index(df):
    """④ 上证 vs 滞涨区/缺口。价格口径, 放量确认需人工看分时。"""
    s = _close(df, C.CN_INDEX)
    if s is None:
        return None, "上证数据缺失"
    px = s.iloc[-1]
    lo, hi = C.CN_SH_BOX
    g_lo, g_hi = C.CN_SH_GAP
    if px > g_hi:
        return True, f"上证{px:.0f} 已回补缺口{g_lo:.0f}-{g_hi:.0f}"
    if px > hi:
        return True, f"上证{px:.0f} 站上{hi:.0f} 攻缺口{g_lo:.0f}"
    if px >= lo:
        return False, f"上证{px:.0f} 滞涨区{lo:.0f}-{hi:.0f}内"
    return False, f"上证{px:.0f} 区间{lo:.0f}下方"


def _c5_anchor(df):
    """⑤ 海外锚价格代理: TSM 20日动量>0 且 SMH/QQQ 比值>其20日均。"""
    tsm, smh, qqq = (_close(df, t) for t in ("TSM", "SMH", "QQQ"))
    if tsm is None or smh is None or qqq is None:
        return None, "海外锚数据缺失"
    mom = _ret(tsm, 20)
    ratio = (smh / qqq).dropna()
    rs_up = ratio.iloc[-1] > ratio.rolling(20).mean().iloc[-1]
    ok = mom > 0 and rs_up
    return ok, f"TSM20日{mom:+.1f}% SMH/QQQ{'↑' if rs_up else '↓'}20日均 (月营收人工)"


def _batons(df):
    """四棒+探测器: 等权超额 + RRG式象限(RS_60水平 × RS_5动量) + 5日加速度。
    象限: 领=双正 改=长负短正 弱=长正短负 落=双负 (借鉴沈老板 Leadership 四象限)"""
    bench = _close(df, C.CN_BENCH)

    def alpha(members, n, off=0):
        rets = []
        for t in members:
            s = _close(df, t)
            if s is None or len(s) <= n + off + 1:
                continue
            s2 = s.iloc[:-off] if off else s
            b2 = bench.iloc[:-off] if off else bench
            rets.append(_ret(s2, n) - _ret(b2, n))
        return sum(rets) / len(rets) if rets else float("nan")

    out = []
    for name, members in C.CN_BATONS.items():
        a5 = alpha(members, C.CN_RS_N)
        a60 = alpha(members, 60)
        accel = a5 - alpha(members, C.CN_RS_N, off=C.CN_RS_N)
        quad = ("领" if a60 > 0 and a5 > 0 else
                "改" if a5 > 0 else
                "弱" if a60 > 0 else "落")
        out.append((name, a5, quad, accel))
    return out


def run(df=None) -> dict:
    if df is None:
        df = _fetch()
    checks = [("①龙头前高",) + _c1_leader_high(df),
              ("②量能结构",) + _c2_volume(df),
              ("③扩散质量",) + _c3_diffusion(df),
              ("④指数验证",) + _c4_index(df),
              ("⑤海外锚",) + _c5_anchor(df)]
    score = sum(1 for _, ok, _ in checks if ok)
    valid = sum(1 for _, ok, _ in checks if ok is not None)
    verdict = ("反转倾向" if score >= 4 else
               "反弹定性" if score <= 1 else "中性观察")
    batons = _batons(df)
    lead = max((b for b in batons if b[1] == b[1]), key=lambda x: x[1], default=None)
    fmt_b = lambda b: f"{b[0]}{b[1]:+.1f}%{b[2]}{'↑' if b[3] > 0 else '↓'}"

    date = _close(df, C.CN_INDEX)
    date = date.index[-1].strftime("%m-%d") if date is not None else "?"
    print("=" * 96)
    print(f"【A股重演监控 — 反转/反弹五条件】数据截至 {date}")
    for name, ok, detail in checks:
        mark = "？" if ok is None else ("✅" if bool(ok) else "✗")
        print(f"  {mark} {name}  {detail}")
    print(f"  → 判定: {verdict}（反转条件 {score}/{valid}）")
    print("  四棒5日超额(象限/加速): " + "  ".join(fmt_b(b) for b in batons))
    if lead:
        note = "⚠️探测器领跑=新逻辑苗头" if lead[0] == "探测" else f"当前棒:{lead[0]}"
        print(f"  {note} · 重演序: PCB→光→液冷→存储")
    print("=" * 96)
    return {"date": date, "checks": checks, "score": score, "valid": valid,
            "verdict": verdict, "batons": batons}


if __name__ == "__main__":
    run()
