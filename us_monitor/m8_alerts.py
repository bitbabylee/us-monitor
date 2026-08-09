# -*- coding: utf-8 -*-
"""
模块8：信号预警卡 —— 复刻 hello231101/signal-system 的四类卡, 治理三类毛病:
  1. 计算类数值(20日线/0.618位/10Y/ratio) → 每日重算, 不再用帖子里的死值
  2. 事件类锚位(博主确认位680等) → 保留但带 锚定日期+失效条件
  3. 触发管理 → 一次性水位穿越只🔔一次, 之后归档显示; 阶段类只在状态变化时🔔
状态存 .alerts_state.json。返回卡片列表供仪表盘渲染。
"""
import datetime as dt
import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import config as C
from .data import col

STATE = Path(__file__).resolve().parent / ".alerts_state.json"


def _load_state() -> dict:
    if STATE.exists():
        try:
            return json.loads(STATE.read_text())
        except json.JSONDecodeError:
            pass
    return {}


def _save_state(s: dict):
    STATE.write_text(json.dumps(s, ensure_ascii=False, indent=1))


def _card(emoji, head, logic, action, nxt, source, bell):
    return {"emoji": emoji, "head": head, "logic": logic, "action": action,
            "next": nxt, "source": source, "bell": bell}


def run(daily: pd.DataFrame, gao: dict) -> list:
    q = col(daily, "Close", "QQQ")
    s = col(daily, "Close", "SMH")
    spy = col(daily, "Close", C.BENCHMARK)
    price = q.iloc[-1]
    state = _load_state()
    today = q.index[-1].strftime("%Y-%m-%d")
    cards = []

    # ── 卡1: 0.618 阶段模板（锚每日重算, 带失效条件, 状态变化才🔔）──
    peak = q.iloc[-C.FIB_PEAK_WIN:].max()
    peak_d = q.iloc[-C.FIB_PEAK_WIN:].idxmax().strftime("%m-%d")
    low = q.iloc[-C.FIB_LOW_WIN:].min()
    low_d = q.iloc[-C.FIB_LOW_WIN:].idxmin().strftime("%m-%d")
    f618 = low + 0.618 * (peak - low)
    f786 = low + 0.786 * (peak - low)
    if price >= peak:
        stage, head, act = "newhigh", (f"QQQ {price:.2f} 创阶段新高(>{peak:.2f}): "
                                       f"2015创业板'第二腿'模板作废"), "模板作废, 回归趋势跟随, 按日线/日内纪律持仓"
    elif price >= f786:
        stage = "above786"
        head = f"QQQ {price:.2f} 已穿越 0.786 位({f786:.2f}): 第二腿假设降级"
        act = "减仓指令撤销; 转为'回踩0.786不破则确认V反'逻辑"
    elif price >= f618:
        stage = "zone"
        head = (f"QQQ {price:.2f} 处于 0.618~0.786 减仓区({f618:.2f}~{f786:.2f}): "
                f"模板减仓观察带")
        act = (f"按模板可减波段仓不追高; ⚠️失效条件: 站上0.786位({f786:.2f})或"
               f"前高({peak:.2f})即撤销第二腿假设")
    else:
        stage = "below618"
        head = f"QQQ {price:.2f} 未及 0.618 位({f618:.2f}): 弱反弹区间"
        act = "模板观察中, 反弹到0.618区再执行减仓纪律"
    bell = state.get("fib_stage") != stage
    state["fib_stage"] = stage
    cards.append(_card(
        "⚠️" if stage == "zone" else "ℹ️", head,
        f"2015创业板模板:暴跌反弹通常至0.618滞涨走第二腿; 锚每日重算: 峰{peak:.2f}({peak_d})/低{low:.2f}({low_d})",
        act,
        "观察随后3日: 滞涨→等第二腿分批买; 穿0.786→假设作废",
        "hello231101/signal-system/rules.md §1阶段C (锚位已改每日重算)", bell))

    # ── 卡2: Brendon#1 20日线（死值702→每日重算）──
    ma20 = q.rolling(20).mean().iloc[-1]
    above = price > ma20
    ma20_bell = state.get("ma20_above") != above     # 只在上穿/跌破切换时🔔
    state["ma20_above"] = bool(above)
    cards.append(_card(
        "✅" if above else "✗",
        f"QQQ {price:.2f} {'站上' if above else '跌破'} 20日均线 {ma20:.2f}"
        f"（每日重算, 7/30校准值702已废弃）: Brendon信号#1 {'+1' if above else '不加分'}",
        "站稳20日均线=短期趋势由跌转涨, 底部确认计分卡五项之一",
        "计分卡见下方汇总; ≥3/5 → 阶段升级可试探仓(≤10%)",
        "连续站稳天数和ratio一起看, 不单独行动",
        "hello231101/signal-system/journal/2026-07-30.md 卡片#4", ma20_bell))

    # ── 卡3: 事件类锚位（触发即归档, 带失效条件; 附10Y自动核对）──
    raw = col(daily, "Close", "^TNX").iloc[-1]
    tnx = raw / 10 if raw > 20 else raw
    spy_newhigh = spy.iloc[-1] >= spy.iloc[-60:].max()
    for ev in C.ALERT_EVENT_LEVELS:
        px = col(daily, "Close", ev["ticker"]).iloc[-1]
        fired = state.get("fired", {}).get(ev["id"])
        crossed = px >= ev["level"]
        if crossed and not fired:
            state.setdefault("fired", {})[ev["id"]] = today
            bell, status = True, f"🔔 首次触发, 已归档"
        elif crossed and fired:
            bell = False
            status = f"已归档({fired}触发), 现价高出 {(px/ev['level']-1)*100:+.1f}%, 不再重复预警"
        else:
            if fired:                      # 跌回水位下方 → 重新武装
                state["fired"].pop(ev["id"], None)
            bell, status = False, "未触发"
        expired = " | ⚠️事件锚已过期: " + ev["invalid"] if spy_newhigh else ""
        cards.append(_card(
            "📌", f"{ev['ticker']} {px:.2f} vs {ev['desc']} {ev['level']:.0f}"
                  f"（锚定{ev['anchor']}）: {status}{expired}",
            "帖子给出的事件位是史料不重算; 但触发一次即归档, 不每日复读",
            f"确认位#2自动核对: 10Y={tnx:.2f}% {'✅≤4.5 利率压制解除' if tnx <= C.GAO_TNX_PASS else '✗>4.5 未解除'}",
            "两道确认都过才升级判断; 事件锚随失效条件自动过期",
            ev["source"], bell))

    # ── 卡4: SMH连续跑赢计数器（自动维护天数）──
    q_ret = q.pct_change().iloc[-C.SMH_STREAK_N - 2:]
    s_ret = s.pct_change().iloc[-C.SMH_STREAK_N - 2:]
    streak = 0
    for i in range(1, min(len(q_ret), len(s_ret))):
        if s_ret.iloc[-i] > q_ret.iloc[-i]:
            streak += 1
        else:
            break
    ok2 = streak >= C.SMH_STREAK_N
    cards.append(_card(
        "✅" if ok2 else "⏳",
        f"SMH跑赢QQQ 连续 {streak}/{C.SMH_STREAK_N} 日"
        f"（今日 SMH{s_ret.iloc[-1]*100:+.2f}% vs QQQ{q_ret.iloc[-1]*100:+.2f}%）: "
        f"Brendon信号#2 {'正式成立' if ok2 else '未成立(雏形)'}",
        "半导体连续跑赢=资金回进攻主线, 单日只算雏形, 计数器每日自动维护",
        "成立后并入计分卡; 中断一日即清零",
        f"还需 {max(0, C.SMH_STREAK_N - streak)} 日",
        "hello231101/signal-system/journal/2026-07-30.md 卡片#4信号2", ok2))

    # ── Brendon 五信号计分卡汇总（与 m7 宏观层合并）──
    items = [
        ("#1 QQQ站稳20日线", above),
        (f"#2 SMH连续{C.SMH_STREAK_N}日跑赢", ok2),
        ("#3 CTA仓位回升(人工)", None),
        (f"#4 ATR14分位<{C.GAO_ATR_PCTL_PASS} (现{gao['atr_pctl']:.0f}%)", gao["atr_ok"]),
        (f"#5 10Y≤4.5(现{tnx:.2f}%) 且信用利差稳", gao["tnx_ok"] and gao["hyg_ok"]),
    ]
    score = sum(1 for _, ok in items if ok)
    _save_state(state)

    # ── 控制台输出（沿用原卡片格式）──
    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    print("=" * 64)
    print(f"信号预警卡 | 数值层每日重算 | {today} 收盘值")
    for c in cards:
        print(f"\n{c['emoji']} {'🔔' if c['bell'] else ''}{c['head']}")
        print(f"▎逻辑:{c['logic']}")
        print(f"▎动作:{c['action']}")
        print(f"▎下一步:{c['next']}")
        print(f"▎出处:{c['source']}")
    print(f"\n【Brendon 底部确认计分卡: {score}/5 (≥3 确认见底)】")
    for name, ok in items:
        print(f"{'✅' if ok else '❓' if ok is None else '✗'} {name}")
    print(f"▎时间:{now} 北京(数值=最近完结交易日收盘, 每日自动重算)")
    print("=" * 64)

    return cards + [{"emoji": "🧮", "head": f"Brendon 计分卡 {score}/5 (≥3 确认见底)",
                     "logic": " · ".join(f"{'✅' if ok else '❓' if ok is None else '✗'}{n}"
                                         for n, ok in items),
                     "action": "", "next": "", "source": "", "bell": score >= 3}]
