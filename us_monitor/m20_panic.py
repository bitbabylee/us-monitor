# -*- coding: utf-8 -*-
"""模块20：恐慌买入计划 —— 补"只会买强势、不会在底部出手"的结构缺口。

由来(2026-08-13): 7/29 SPX 7316 那天, CAMSLIM 派发压力 7、高老师 P0,
系统正确地说了"别买"; 但等 X/PP 亮灯已是 7437-7736(晚 2-6%)。
问题不在信号迟到(那是它该做的), 而在于**没有为抄底预留过弹药、
没有预写过分批规则** —— 恐慌当天临时决策 = 必然不出手。
本模块在冷静时把规则写死, 恐慌时只负责报"第几档到了"。

三档触发(各用预留现金的 1/3, 独立计数, 触发即归档不重复):
  ①恐慌档 卖压高位(派发≥PANIC_DIST) 且 距60日高 ≤ -PANIC_DD%
  ②释放档 高老师恐慌释放成立(P1及以上, 必选题过)
  ③确认档 资金共识(C1及以上) 或 派发清零且站上MA50
纪律: 只用预留现金, 不动既有仓位; 框架底没有止损位, 所以单档上限固定。
平时静默, 只在①触发或已有档位在途时才进日报。
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from . import config as C
from .data import col

STATE = Path(__file__).parent / ".panic_state.json"


def _load() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return {"fired": {}}


def run(daily, cam, gao, m1) -> dict:
    st = _load()
    fired = st.get("fired", {})
    today = dt.date.today().isoformat()

    spx = col(daily, "Close", "^GSPC").dropna()
    px = float(spx.iloc[-1])
    hi60 = float(spx.iloc[-60:].max())
    dd = (px / hi60 - 1) * 100                     # 距60日高回撤%
    ma50 = float(spx.rolling(50).mean().iloc[-1])
    dist = float(cam.get("dist_n", 0))
    peak = float(cam.get("peak_recent", dist))     # 近10日卖压峰值
    phase = str(gao.get("phase", ""))
    p_ok = gao.get("p_score", 0) >= 3 and gao.get("panic", [(None, True)])[0][1] \
        if isinstance(gao.get("panic"), list) else phase.startswith(("P1", "C"))

    t1 = dist >= C.PANIC_DIST and dd <= -C.PANIC_DD
    t2 = phase.startswith(("P1", "C"))
    t3 = phase.startswith("C") or (dist <= 2 and px > ma50)

    # 只有在"这一轮恐慌里"才允许逐档推进: 以①的触发为一轮的开始
    round_open = bool(fired.get("t1")) or t1
    checks = [("①恐慌档", t1, f"派发{dist:g}(峰{peak:g}) 距60日高{dd:+.1f}%"
                             f" · 门槛 派发≥{C.PANIC_DIST} 且 回撤≤-{C.PANIC_DD}%"),
              ("②释放档", round_open and t2, f"阶段{phase.split()[0]}"),
              ("③确认档", round_open and t3,
               f"阶段{phase.split()[0]} · 派发{dist:g} · {'站上' if px > ma50 else '未站上'}MA50")]

    newly = []
    for key, (name, ok, _) in zip(("t1", "t2", "t3"), checks):
        if ok and not fired.get(key):
            fired[key] = today
            newly.append(name)
    # 一轮结束: 卖压清零且阶段到C1以上, 三档都用过 → 归档重置, 等下一轮恐慌
    if fired.get("t3") and dist == 0 and phase.startswith("C"):
        st.setdefault("history", []).append(dict(fired))
        fired = {}
    st["fired"] = fired
    STATE.write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")

    active = bool(fired) or t1
    lines = []
    if active:
        for key, (name, ok, detail) in zip(("t1", "t2", "t3"), checks):
            mark = f"✅已触发{fired[key][5:]}" if fired.get(key) else ("🔔今日达标" if ok else "○待触发")
            lines.append(f"  {name} {mark} — {detail}")
        lines.append("  买什么: 指数(QQQ/SPY)不是个股——指数不归零/不需基本面判断/"
                     "不被单票爆雷打脸, \"机会几乎不会错\"只在指数上成立")
        lines.append("  纪律: 每档只动预留现金1/3 · 框架底无止损位 · 单档触发一次不重复")
    else:
        lines.append(f"  未进入恐慌区(派发{dist:g} 回撤{dd:+.1f}%) · 门槛 "
                     f"派发≥{C.PANIC_DIST} 且 回撤≤-{C.PANIC_DD}%")

    print("=" * 96)
    print("【恐慌买入计划】冷静时写死·恐慌时照做(与常规信号链独立)")
    for ln in lines:
        print(ln)
    print("=" * 96)
    return {"lines": lines, "active": active, "newly": newly, "fired": fired}
