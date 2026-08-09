# -*- coding: utf-8 -*-
"""
模块10：CAMSLIM 大盘健康度分析器（欧奈尔/IBD 派发日体系）

核心思想：大盘顶部不是一天砸出来的, 是机构在高位连续"派发"（放量下跌）堆出来的。
数派发日 → 定仓位。这是自上而下的"该不该重仓"，与 m4/m5 的"买什么"互补。

三类日：
  🔴 派发日 Distribution: 收跌≥0.2% 且 量>前日 —— 机构在卖
  🟢 吸筹日 Accumulation:  收涨≥0.7% 且 量>前日 —— 机构在买
  🟡 滞涨日 Stall:         收涨但涨幅微弱 + 放量 + 收在当日下半区 —— 高位换手, 隐性派发

派发日的两种消除方式：
  ① 自然过期：滚出 25 个交易日窗口
  ② 上涨作废：创窗口新高(hard_remove) 或 较该日收盘涨超5%(soft, IBD标准)
"""
import numpy as np
import pandas as pd

from . import config as C
from .data import col


def _classify(c, o, h, l, v):
    """逐日打标: 返回 DataFrame[日期, 涨跌%, 放量, 类型]"""
    chg = c.pct_change() * 100
    vol_up = v > v.shift()
    rng = (h - l).replace(0, np.nan)
    close_pos = (c - l) / rng          # 收盘在当日区间的位置 0~1
    rows = []
    for i in range(1, len(c)):
        t = ""
        if chg.iloc[i] <= -C.CAM_DIST_PCT and vol_up.iloc[i]:
            t = "dist"
        elif chg.iloc[i] >= C.CAM_ACC_PCT and vol_up.iloc[i]:
            t = "acc"
        elif (0 < chg.iloc[i] < C.CAM_STALL_PCT and vol_up.iloc[i]
              and close_pos.iloc[i] < 0.5):
            t = "stall"
        rows.append((c.index[i], c.iloc[i], chg.iloc[i], bool(vol_up.iloc[i]), t))
    return pd.DataFrame(rows, columns=["date", "close", "chg", "vol_up", "type"])


def _alive_at(df: pd.DataFrame, end: int):
    """截至 df 第 end 行(不含)时, 仍然存活的派发/滞涨日。
    hard_remove: 一旦其后指数创出【CAM_HIGH_WIN 窗口】新高, 之前的派发日被永久清除。
    注意参照窗口必须比计数窗口长 —— 否则 25 日内的次级高点会被误判为新高。"""
    win = df.iloc[max(0, end - C.CAM_WINDOW):end]
    if win.empty:
        return [], []
    price = win["close"].iloc[-1]
    cutoff = None
    if C.CAM_INVALIDATION == "hard_remove":
        ref = df.iloc[max(0, end - C.CAM_HIGH_WIN):end]      # 长参照窗口
        for k in range(len(win) - 1, -1, -1):
            dt = win["date"].iloc[k]
            prior = ref[ref["date"] <= dt]["close"]
            if len(prior) and win["close"].iloc[k] >= prior.max() - 1e-9:
                cutoff = dt                                   # 真·新高 → 压力清零点
                break
    alive, stalls = [], []
    for _, r in win.iterrows():
        if cutoff is not None and r["date"] <= cutoff:
            continue                                  # 新高之前的压力已释放
        rally = (price / r["close"] - 1) * 100
        if r["type"] == "dist" and rally < C.CAM_RALLY_PCT:
            alive.append((r["date"], r["chg"], rally))
        elif r["type"] == "stall":
            stalls.append(r)
    return alive, stalls


def _count_at(df: pd.DataFrame, pos: int):
    """历史上第 pos 天(负索引)当时的存活派发日数 —— 用来还原压力曲线"""
    a, s = _alive_at(df, len(df) + pos + 1)
    return len(a) + len(s) * 0.5


def run(daily: pd.DataFrame) -> dict:
    idx = C.CAM_INDEX
    c = col(daily, "Close", idx)
    o, h, l = col(daily, "Open", idx), col(daily, "High", idx), col(daily, "Low", idx)
    v = col(daily, "Volume", idx)
    df = _classify(c, o, h, l, v)

    win = df.tail(C.CAM_WINDOW)                     # 25 交易日计数窗口
    price = c.iloc[-1]
    high = c.iloc[-C.CAM_HIGH_WIN:].max()           # 回撤基准 = 长窗口高点
    new_high = price >= high * (1 - 1e-9)

    # 压力曲线: 还原最近 N 日每天的派发日数（轨迹比单日数值更重要）
    traj = [(df["date"].iloc[i], _count_at(df, i)) for i in range(-C.CAM_WINDOW, 0)]

    # 派发日清点与作废（新高之前的压力永久释放, 不复活）
    raw = win[win["type"] == "dist"]
    acc_n = len(win[win["type"] == "acc"])
    alive, stall_list = _alive_at(df, len(df))
    alive_dates = {d for d, _, _ in alive}
    killed = []
    for _, r in raw.iterrows():
        if r["date"] in alive_dates:
            continue
        rally = (price / r["close"] - 1) * 100
        why = (f"较该日收盘涨 {rally:.1f}% ≥{C.CAM_RALLY_PCT}%" if rally >= C.CAM_RALLY_PCT
               else "其后指数创窗口新高, 派发压力已释放")
        killed.append((r["date"], rally, why))
    stalls = pd.DataFrame(stall_list) if stall_list else win.iloc[0:0]
    dist_n = len(alive) + len(stall_list) * 0.5

    # 状态判定与建议仓位
    # 状态阈值由原版实证: dist≥5 → CONFIRMED CORRECTION, ==4 → CAUTION, ≤3 → UPTREND
    ma50 = c.rolling(50).mean().iloc[-1]
    above50 = price > ma50
    if dist_n >= C.CAM_CORRECTION_LINE:
        status = "CONFIRMED CORRECTION"
    elif dist_n >= C.CAM_CAUTION:
        status = "CAUTION"
    elif above50:
        status = "CONFIRMED UPTREND"
    else:
        status = "RALLY ATTEMPT"

    # 仓位 = clamp((BASE - 派发日) × STEP, FLOOR, CAP) —— 由原版6个时点反推
    ladder_pct = min(C.CAM_EXPO_CAP,
                     max(C.CAM_EXPO_FLOOR,
                         (C.CAM_EXPO_BASE - dist_n) * C.CAM_EXPO_STEP))
    ladder = f"{ladder_pct:.0f}%"

    # ── 仓位爬坡：卖压刚从高位降下来时不一次给满，每站稳一天加一档 ──
    counts = [n for _, n in traj]
    peak_recent = max(counts[-C.CAM_RAMP_LOOKBACK:]) if counts else 0
    days_improved = 0
    for n in reversed(counts):                       # 连续站在当前(改善后)水平的天数
        if n <= dist_n:
            days_improved += 1
        else:
            break
    # 爬坡只用于「被动衰减」——派发日自然过期、卖压慢慢变小, 需要时间验证。
    # 若改善来自「指数创新高」(决定性利多), 压力是被真金白银打掉的, 直接给足仓位。
    # 判据看的是"压力清零是否由近期新高造成", 而非"今天是否恰好新高"。
    hw = c.iloc[-C.CAM_HIGH_WIN:]
    runmax = hw.cummax()
    nh_pos = [i for i in range(len(hw)) if hw.iloc[i] >= runmax.iloc[i] - 1e-9]
    days_since_nh = len(hw) - 1 - nh_pos[-1] if nh_pos else 999
    decayed = peak_recent >= C.CAM_HIGH_PRESSURE and dist_n < peak_recent
    ramping = (C.CAM_USE_RAMP and decayed
               and days_since_nh > C.CAM_RAMP_LOOKBACK
               and days_improved <= len(C.CAM_RAMP_STEPS))
    if ramping:
        cap = C.CAM_RAMP_STEPS[max(0, days_improved - 1)]
        cap = min(cap, ladder_pct)                   # 爬坡只压低不抬高
        exposure = f"{cap:.0f}%"
        ramp_note = (f"卖压刚从 {peak_recent:g} 降到 {dist_n:g}（连续第 {days_improved} 天）"
                     f"→ 爬坡上限 {cap:.0f}%，原版公式给 {ladder}，站稳再加")
    elif decayed and days_since_nh <= C.CAM_RAMP_LOOKBACK:
        exposure = ladder
        ramp_note = (f"卖压由 {peak_recent:g} 归 {dist_n:g}，且 {days_since_nh} 日前指数创"
                     f"{C.CAM_HIGH_WIN}日新高——决定性利多, 不走爬坡, 直接给足 {ladder}")
    else:
        exposure, ramp_note = ladder, ""

    drawdown = (price / high - 1) * 100
    week = (price / c.iloc[-5] - 1) * 100      # 5个交易日前(对齐原版口径)

    # 卖压轨迹解读（用户核心经验：持续高位=机构一直在卖, 反弹容易被卖出）
    hi_days = sum(1 for n in counts[-C.CAM_RAMP_LOOKBACK:] if n >= C.CAM_HIGH_PRESSURE)
    if dist_n >= C.CAM_HIGH_PRESSURE:
        pressure_read = ("🔴 卖压持续高位 —— 机构一直在卖, 市场卖方主导。反弹容易被卖出, "
                         "做多难度大: 只做最强势个股, 止损带窄, 突破/高位追涨都要谨慎")
    elif ramping:
        pressure_read = (f"🟡 卖压刚缓解（近{C.CAM_RAMP_LOOKBACK}日峰值 {peak_recent:g}）—— "
                         f"在卖的机构少了, 但只是第 {days_improved} 天。分批加仓不一次满仓, "
                         f"再站稳几天才升级为牛")
    elif hi_days:
        pressure_read = f"🟡 近{C.CAM_RAMP_LOOKBACK}日有 {hi_days} 天处于卖压高位, 余悸未消, 保持警觉"
    elif dist_n >= C.CAM_CAUTION:
        pressure_read = "🟡 卖压中等 —— 有机构在减仓, 新开仓位控制规模、止损收紧"
    else:
        pressure_read = "🟢 卖压清淡 —— 机构未在系统性卖出, 强势股突破的成功率较高"
    # 方向强度: 窗口内吸筹日占(吸筹+派发)比重
    tot = acc_n + len(raw)
    dir_pct = 100 * acc_n / tot if tot else 50
    direction = ("BULLISH" if dir_pct >= 65 else "NEUTRAL" if dir_pct >= 48 else
                 "UNCERTAIN" if dir_pct >= 40 else "BEARISH")

    events = []
    if len(killed):
        events.append(f"{len(killed)} 个派发日被上涨作废（{killed[0][2]}）")
    if len(stalls):
        events.append(f"窗口内 {len(stalls)} 个滞涨日（高位换手, 隐性派发）")
    cross = c.rolling(50).mean()
    for i in range(-C.CAM_WINDOW, 0):
        if (c.iloc[i] > cross.iloc[i]) != (c.iloc[i - 1] > cross.iloc[i - 1]):
            events.append(f"{'站上' if c.iloc[i] > cross.iloc[i] else '跌破'} 50日均线 "
                          f"于 {c.index[i]:%m-%d}")
            break

    d = c.index[-1].strftime("%Y-%m-%d")
    print("=" * 72)
    print(f"CAMSLIM 大盘健康度分析器 | {idx} | {d} | 窗口 {C.CAM_WINDOW} 交易日")
    print("=" * 72)
    print(f"状态: {status}   |   派发日: {dist_n:g} (对 {acc_n} 吸筹日)   |   "
          f"建议仓位: {exposure}   |   方向: {direction} {dir_pct:.0f}%")
    print(f"现价 {price:.2f}   窗口高 {high:.2f}   回撤 {drawdown:+.2f}%   "
          f"周涨幅 {week:+.2f}%   MA50 {ma50:.2f}({'上方' if above50 else '下方'})")
    if ramp_note:
        print(f"⚠️ 仓位爬坡: {ramp_note}")
    print()
    # 压力曲线（轨迹比单日数值重要：持续高位=机构一直在卖, 反弹易被卖出）
    spark = "".join("▁▂▃▄▅▆▇█"[min(int(n), 7)] for _, n in traj)
    print(f"【卖压轨迹 近{C.CAM_WINDOW}日】{spark}  ({traj[0][1]:g} → {traj[-1][1]:g})")
    print(f"  解读: {pressure_read}")
    print()
    print(f"【存活派发日 {len(alive)} 个】" if alive else "【无存活派发日】")
    for dt, chg, rally in alive:
        print(f"  🔴 {dt:%m-%d}  {chg:+.2f}%   现价较其 {rally:+.1f}%")
    if killed:
        print(f"【已作废 {len(killed)} 个】")
        for dt, rally, why in killed:
            print(f"  ⚪ {dt:%m-%d}  现价较其 {rally:+.1f}%  — {why}")
    if len(stalls):
        print(f"【滞涨日 {len(stalls)} 个】" + ", ".join(f"{r['date']:%m-%d}"
                                                     for _, r in stalls.iterrows()))
    print()
    print(f"【仓位公式】min({C.CAM_EXPO_CAP}, max({C.CAM_EXPO_FLOOR}, "
          f"({C.CAM_EXPO_BASE} − 派发日) × {C.CAM_EXPO_STEP}))  —— 由原版6个时点反推")
    print("【关键事件】" + ("; ".join(events) if events else "无"))
    print("=" * 72)

    return {"status": status, "direction": direction, "dir_pct": dir_pct,
            "dist_n": dist_n, "acc_n": acc_n, "exposure": exposure,
            "ladder": ladder, "ramping": ramping, "ramp_note": ramp_note,
            "days_improved": days_improved, "peak_recent": peak_recent,
            "pressure_read": pressure_read, "traj": traj,
            "price": price, "high": high, "drawdown": drawdown, "week": week,
            "ma50": ma50, "above50": above50, "alive": alive, "killed": killed,
            "stalls": len(stalls), "events": events, "date": d,
            "series": df.tail(C.CAM_WINDOW * 2)}
