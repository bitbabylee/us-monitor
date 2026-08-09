# -*- coding: utf-8 -*-
"""
模块14：信号日志 + 历史回放 —— 回答「这套系统到底准不准」。

两件事:
  ① 日志: 每天把发出的信号存档, T+1/T+5/T+10 自动回填实际表现（持续积累真实样本）
  ② 回放: 把形态检测函数在历史数据上重跑一遍, 立刻拿到每类信号的历史胜率
     （形态函数是纯函数, 切片到第 T 天重放即可; 只用 ≤T 的数据, 无未来函数）

诚实原则: 样本量小的信号明确标注「样本不足」, 不给看起来很准的假象。
回放测的是「信号发出后 N 日的裸收益」, 不含止损/仓位/滑点 —— 是信号质量的下限参考,
不是策略收益。

    python3 -m us_monitor.m14_journal              # 回放 + 统计
    python3 -m us_monitor.m14_journal --record     # 只记录今日信号
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from . import config as C
from .data import col

JOURNAL = Path(__file__).resolve().parent / ".signal_journal.json"
REPLAY = Path(__file__).resolve().parent / ".signal_replay.json"


# ── ① 日志：记录当日信号 + 回填表现 ──────────────────

def _load(p: Path, default):
    if p.exists():
        try:
            return json.loads(p.read_text())
        except json.JSONDecodeError:
            pass
    return default


def record(daily: pd.DataFrame, wl_df: pd.DataFrame, keep, drop) -> dict:
    """把当日日线形态信号写进日志（同日同票同形态只记一次）"""
    j = _load(JOURNAL, {"entries": []})
    seen = {(e["date"], e["ticker"], e["signal"]) for e in j["entries"]}
    date = col(daily, "Close", C.BENCHMARK).index[-1].strftime("%Y-%m-%d")
    kept = {tk for tk, _, _ in keep}

    n = 0
    for _, r in wl_df[wl_df["标记"] != "⚪"].iterrows():
        key = (date, r["代码"], r["形态"])
        if key in seen:
            continue
        j["entries"].append({
            "date": date, "ticker": r["代码"], "signal": r["形态"],
            "mark": r["标记"], "price": float(r["收盘价"]),
            "passed_crosscheck": r["代码"] in kept,
            "earnings_flag": bool(r.get("财报")),
            "rsi": float(r["RSI"]), "volx": float(r["量倍"]),
            "ret": {},                       # 待回填
        })
        n += 1
    j["updated"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    JOURNAL.write_text(json.dumps(j, ensure_ascii=False, indent=1))
    return {"added": n, "total": len(j["entries"])}


def backfill(daily: pd.DataFrame) -> int:
    """给历史条目回填 T+1/T+5/T+10 收益"""
    j = _load(JOURNAL, {"entries": []})
    filled = 0
    for e in j["entries"]:
        try:
            c = col(daily, "Close", e["ticker"])
        except (KeyError, IndexError):
            continue
        idx = c.index.strftime("%Y-%m-%d")
        pos = list(idx).index(e["date"]) if e["date"] in list(idx) else -1
        if pos < 0:
            continue
        for h in C.JRN_HORIZONS:
            k = f"T+{h}"
            if k in e["ret"] or pos + h >= len(c):
                continue
            e["ret"][k] = round((c.iloc[pos + h] / c.iloc[pos] - 1) * 100, 2)
            filled += 1
    JOURNAL.write_text(json.dumps(j, ensure_ascii=False, indent=1))
    return filled


# ── ② 历史回放：立刻拿到胜率 ─────────────────────────

def replay(daily: pd.DataFrame, lookback: int = None) -> dict:
    """把 _pattern() 在历史每一天重跑, 统计各类信号的前瞻收益。
    切片保证只用 ≤T 的数据 —— 无未来函数。"""
    from .m4_watchlist import _pattern
    lookback = lookback or C.JRN_REPLAY_DAYS
    hits = []
    for tk in C.WATCHLIST:
        try:
            c, h, l = (col(daily, "Close", tk), col(daily, "High", tk),
                       col(daily, "Low", tk))
            o, v = col(daily, "Open", tk), col(daily, "Volume", tk)
        except (KeyError, IndexError):
            continue
        n = len(c)
        if n < 80:
            continue
        start = max(60, n - lookback)
        for t in range(start, n):
            mark, pat, _ = _pattern(c.iloc[:t + 1], h.iloc[:t + 1], l.iloc[:t + 1],
                                    o.iloc[:t + 1], v.iloc[:t + 1])
            if mark == "⚪":
                continue
            rec = {"date": c.index[t].strftime("%Y-%m-%d"), "ticker": tk,
                   "signal": pat, "mark": mark}
            for hz in C.JRN_HORIZONS:
                if t + hz < n:
                    rec[f"T+{hz}"] = (c.iloc[t + hz] / c.iloc[t] - 1) * 100
            hits.append(rec)

    df = pd.DataFrame(hits)
    out = {"n_signals": len(df), "lookback": lookback,
            "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "by_signal": [], "baseline": {}}
    if df.empty:
        REPLAY.write_text(json.dumps(out, ensure_ascii=False, indent=1))
        return out

    # 基准: 同期观察池「任意一天买入」的平均表现, 用来对照信号有没有超额
    base = []
    for tk in C.WATCHLIST:
        try:
            c = col(daily, "Close", tk)
        except (KeyError, IndexError):
            continue
        n = len(c)
        start = max(60, n - lookback)
        for t in range(start, n):
            row = {}
            for hz in C.JRN_HORIZONS:
                if t + hz < n:
                    row[f"T+{hz}"] = (c.iloc[t + hz] / c.iloc[t] - 1) * 100
            if row:
                base.append(row)
    bdf = pd.DataFrame(base)
    for hz in C.JRN_HORIZONS:
        k = f"T+{hz}"
        if k in bdf:
            out["baseline"][k] = {"avg": round(bdf[k].mean(), 2),
                                  "win": round((bdf[k] > 0).mean() * 100, 1),
                                  "n": int(bdf[k].notna().sum())}

    for sig, g in df.groupby("signal"):
        row = {"signal": sig, "mark": g["mark"].iloc[0], "n": len(g)}
        for hz in C.JRN_HORIZONS:
            k = f"T+{hz}"
            if k in g and g[k].notna().any():
                s = g[k].dropna()
                row[k] = {"avg": round(s.mean(), 2),
                          "med": round(s.median(), 2),
                          "win": round((s > 0).mean() * 100, 1),
                          "n": len(s),
                          "edge": round(s.mean() - out["baseline"].get(k, {}).get("avg", 0), 2)}
        row["enough"] = len(g) >= C.JRN_MIN_SAMPLE
        out["by_signal"].append(row)
    out["by_signal"].sort(key=lambda r: -(r.get(f"T+{C.JRN_HORIZONS[-1]}", {}).get("edge", -99)))
    REPLAY.write_text(json.dumps(out, ensure_ascii=False, indent=1))
    return out


def load_replay() -> dict:
    return _load(REPLAY, {"by_signal": [], "n_signals": 0})


def run(daily=None) -> dict:
    if daily is None:
        from .data import fetch_daily
        print("拉取日线 ...")
        daily = fetch_daily(C.all_daily_tickers(), days=C.JRN_REPLAY_DAYS + 200)
    r = replay(daily)
    hz_last = f"T+{C.JRN_HORIZONS[-1]}"
    print("=" * 104)
    print(f"【信号历史回放】近 {r['lookback']} 交易日 · 观察池 {len(C.WATCHLIST)} 只 · "
          f"共触发 {r['n_signals']} 次")
    print("口径: 信号当日收盘买入, N 日后收盘的裸收益。不含止损/仓位/滑点, 是信号质量的下限参考。")
    b = r.get("baseline", {})
    if b:
        print("基准（同期任意一天买入）: " + " · ".join(
            f"{k} 均值 {v['avg']:+.2f}% 胜率 {v['win']:.0f}%" for k, v in b.items()))
    print("-" * 104)
    print(f"{'形态':<26}{'样本':>5}", end="")
    for hz in C.JRN_HORIZONS:
        print(f"{'T+'+str(hz)+' 均值/胜率/超额':>22}", end="")
    print()
    for row in r["by_signal"]:
        flag = "" if row["enough"] else "  ⚠️样本不足"
        print(f"{row['mark']} {row['signal'][:22]:<24}{row['n']:>5}", end="")
        for hz in C.JRN_HORIZONS:
            d = row.get(f"T+{hz}")
            cell = (f"{d['avg']:+.2f}% / {d['win']:.0f}% / {d['edge']:+.2f}%"
                    if d else "—")
            print(f"{cell:>22}", end="")
        print(flag)
    print("-" * 104)
    print(f"⚠️ 样本 < {C.JRN_MIN_SAMPLE} 的结论不可信。「超额」= 该信号均值 − 同期随机买入均值,")
    print("   超额为负说明这个形态还不如随便买 —— 那就该调阈值或弃用。")
    print("=" * 104)
    return r


if __name__ == "__main__":
    if "--record" in sys.argv:
        print("record 需由 run_all/m6 调用（要用到当日 wl_df）")
    else:
        run()
