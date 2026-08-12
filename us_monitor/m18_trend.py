# -*- coding: utf-8 -*-
"""模块18：走势中频 —— Weinstein 阶段 + 摆动结构 + 波段回撤（周~月尺度）。

填补体系空档: 日频(形态/日内/期权)与阶段级(CAMSLIM/高老师)之间的
"这只票的趋势处于什么结构位置"。中频展示原则: 日报只报【变化】
(Stage迁移/结构翻转)与池子广度, 全表在控制台看。
判定口径:
  Stage: MA150(≈30周)位置+20日斜率+MA50关系 → S1筑底/S2上升/S3筑顶/S4下降
  结构: ±5日分形摆动点, 近两组高低点 → HH/HL 或 LH/LL
  回撤: 现价在最近一段低→高波段中的回吐比例
状态: .trend_state.json 记录上次 Stage 以探测迁移(CI 需 git add -f)。
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import yfinance as yf

from . import config as C
from .data import col

STATE = Path(__file__).parent / ".trend_state.json"
SWING_W = 5          # 分形窗口: ±5 日极值为摆动点
FLAT = 0.5           # MA150 20日斜率 ±此% 内视为走平
US_EXTRA = ["SPY", "QQQ", "SMH"]


def _stage(c: pd.Series):
    if len(c) < 170:
        return "S?", 0.0
    ma50 = c.rolling(50).mean().iloc[-1]
    ma150 = c.rolling(150).mean()
    slope = (ma150.iloc[-1] / ma150.iloc[-21] - 1) * 100
    px = c.iloc[-1]
    if slope > FLAT and px > ma150.iloc[-1] and ma50 > ma150.iloc[-1]:
        return "S2↑", slope
    if slope < -FLAT and px < ma150.iloc[-1] and ma50 < ma150.iloc[-1]:
        return "S4↓", slope
    return ("S3⌒" if px >= ma150.iloc[-1] else "S1⌐"), slope


def _swings(c: pd.Series):
    """返回 (摆动高点列表, 摆动低点列表)，各取最近2个。"""
    hi, lo = [], []
    v = c.values
    for i in range(SWING_W, len(v) - SWING_W):
        seg = v[i - SWING_W:i + SWING_W + 1]
        if v[i] == seg.max():
            hi.append((i, v[i]))
        if v[i] == seg.min():
            lo.append((i, v[i]))
    return hi[-2:], lo[-2:]


def _structure(c: pd.Series):
    hi, lo = _swings(c.iloc[-130:])
    if len(hi) < 2 or len(lo) < 2:
        return "—", None, None
    hh = hi[1][1] > hi[0][1]
    hl = lo[1][1] > lo[0][1]
    struct = "HH/HL" if hh and hl else ("LH/LL" if not hh and not hl else "转折中")
    return struct, hi[-1][1], lo[-1][1]


def _retrace(px, swing_hi, swing_lo):
    if not swing_hi or not swing_lo or swing_hi <= swing_lo:
        return None
    return max(0.0, (swing_hi - px) / (swing_hi - swing_lo) * 100)


def _analyze(name, c, tk=None):
    stage, slope = _stage(c)
    struct, sh, sl = _structure(c)
    r = _retrace(c.iloc[-1], sh, sl)
    warn = "⚠️结构受损" if (r is not None and r > 62 and stage.startswith("S2")) else ""
    # 红绿灯: 把4个技术字段压成1个动作档位
    if stage.startswith("S2") and (r is None or r <= 38) and struct != "LH/LL":
        light, why = "🟢", "趋势健康·浅回撤"
    elif stage.startswith("S2") and not warn:
        light = "🟡"
        why = ("高点仍在走低·结构未转多" if struct == "LH/LL" and (r is None or r <= 38)
               else f"回撤{r:.0f}%偏深" if r is not None else "结构待明")
    elif stage.startswith("S2"):
        light, why = "🔴", f"名义上升但已回吐{r:.0f}%"
    elif stage.startswith("S1"):
        light, why = "🟡", "筑底中·未确认"
    else:
        light, why = "🔴", ("筑顶·MA150转平/向下" if stage.startswith("S3") else "下降趋势")
    from . import tv
    return {"name": name, "sym": tv.symbol(tk or name), "stage": stage,
            "slope": slope, "struct": struct,
            "retrace": r, "warn": warn, "light": light, "why": why}


def run(daily=None) -> dict:
    rows = []
    # 美股池: 复用主数据(有则), 否则自取
    us = list(dict.fromkeys(C.WATCHLIST + US_EXTRA))
    if daily is not None:
        for tk in us:
            try:
                c = col(daily, "Close", tk).dropna()
                if len(c) >= 170:
                    rows.append(_analyze(tk, c))
            except Exception:
                pass
    else:
        df = yf.download(us, period="14mo", interval="1d", auto_adjust=True,
                         progress=False, group_by="column")
        for tk in us:
            try:
                c = df["Close"][tk].dropna()
                if len(c) >= 170:
                    rows.append(_analyze(tk, c))
            except Exception:
                pass
    # A股池
    cn = sorted(C.CN_NAMES)
    dfc = yf.download(cn, period="14mo", interval="1d", auto_adjust=True,
                      progress=False, group_by="column")
    for tk in cn:
        try:
            c = dfc["Close"][tk].dropna()
            if len(c) >= 170:
                rows.append(_analyze(C.CN_NAMES.get(tk, tk), c, tk))
        except Exception:
            pass

    # Stage 迁移探测
    try:
        prev = json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        prev = {}
    cur = {r["name"]: r["stage"] for r in rows}
    moves = [f"{n} {prev[n]}→{s}" for n, s in cur.items()
             if n in prev and prev[n] != s]
    STATE.write_text(json.dumps(cur, ensure_ascii=False), encoding="utf-8")

    n = len(rows) or 1
    breadth = {k: sum(1 for r in rows if r["stage"].startswith(k))
               for k in ("S1", "S2", "S3", "S4")}
    pct2 = breadth["S2"] * 100 // n

    buckets = {k: [r for r in rows if r["light"] == k] for k in ("🟢", "🟡", "🔴")}
    key = lambda r: (r["retrace"] if r["retrace"] is not None else 99)

    print("=" * 96)
    print("【走势中频 — 三档红绿灯】(周~月尺度; 🟢可买区 🟡等待 🔴回避)")
    print(f"  大环境: 上升趋势占比 {pct2}%  (S2上升{breadth['S2']} S1筑底{breadth['S1']} "
          f"S3筑顶{breadth['S3']} S4下降{breadth['S4']})")
    if moves:
        print("  📣 本期变化: " + " · ".join(moves))
    for k, title in (("🟢", "可买区 — 趋势健康、回撤浅，日线信号可执行"),
                     ("🟡", "等待区 — 趋势在但位置不好/未确认，只观察"),
                     ("🔴", "回避区 — 趋势失效或名存实亡，日线信号一律降级")):
        b = sorted(buckets[k], key=key)
        print(f"  {k} {title}  ({len(b)})")
        for r in b:
            tag = f"{r['sym']}" + (f"({r['name']})" if r["sym"].split(":")[-1] != r["name"] else "")
            print(f"     {tag:<20} {r['why']}")
    print("  口径: S2/S1/S3/S4=Weinstein阶段(MA150) · 回撤=最近一段涨浪回吐比例")
    print("=" * 96)

    nm = lambda k: " ".join(
        r["sym"] + (f"({r['name']})" if r["sym"].split(":")[-1] != r["name"] else "")
        for r in sorted(buckets[k], key=key))
    lines = [f"  上升趋势占比 {pct2}%" + (f" · 📣{' · '.join(moves[:3])}" if moves else ""),
             f"  🟢可买区({len(buckets['🟢'])}): " + (nm("🟢") or "无"),
             f"  🔴回避区({len(buckets['🔴'])}): " + (nm("🔴") or "无")]
    return {"lines": lines, "rows": rows, "moves": moves, "buckets": buckets}


if __name__ == "__main__":
    run()
