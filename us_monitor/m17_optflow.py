# -*- coding: utf-8 -*-
"""模块17：期权异动 —— WATCHLIST 期权链快照 + vol/OI 开仓过滤 + T+1 OI确认。

设计(对齐 2026-08-11 讨论):
  · 快餐流量账号(RunningoftheBulltards类)靠猜成交方向, 我们不猜——
    只做两件可验证的事: ①vol/OI>阈值 = 疑似新开仓(新钱)
    ②次日 OI 增量核对 = 确认开仓(别人不做的那一步, 慢一天假信号少一半)
  · 方向只按 call/put 权利金相对占比粗分(C/P/≈), 不声称知道买卖方
  · 收盘后快照有效; 盘前跑时当日 volume≈0, 自动只做昨日候选确认
状态: .optflow_state.json (CI 需 git add -f 持久化, 已加入 workflow)
时段注意: OPRA 的 OI 每日晨间(~6am ET)更新; 美股深夜跑时 yfinance 常
  bid/ask=0 且 OI=0 → 候选自动为空(无害), 权利金退回 lastPrice 口径。
  两条 cron 恰好分工: 16:30ET=量快照(live), 次日 8:30ET=OI 确认。
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import yfinance as yf

from . import config as C

STATE = Path(__file__).parent / ".optflow_state.json"
N_EXP = 2            # 扫最近两个到期日
MIN_VOL = 300        # 候选合约最小当日量
VOI = 1.5            # vol/OI ≥此 → 疑似新开仓
MIN_PREM = 2e6       # 单票单边权利金达标线($)
CONFIRM_R = 0.5      # 次日OI增量 ≥ 昨日量×此比例 → 确认开仓
TOP_N = 5


def _scan(tk):
    """返回 (call_prem, put_prem, 候选list, oi查询表)。任何异常抛给上层跳过。"""
    t = yf.Ticker(tk)
    call_p = put_p = 0.0
    cands, oi_map = [], {}
    for exp in (t.options or [])[:N_EXP]:
        ch = t.option_chain(exp)
        for side, df in (("C", ch.calls), ("P", ch.puts)):
            df = df.fillna(0)
            # 陈旧 lastPrice 会把 illiquid 链的权利金吹爆 → 有双边报价用中点
            mid = ((df["bid"] + df["ask"]) / 2).where((df["bid"] > 0) & (df["ask"] > 0),
                                                      df["lastPrice"])
            prem = float((df["volume"] * mid).sum()) * 100
            if side == "C":
                call_p += prem
            else:
                put_p += prem
            for _, r in df.iterrows():
                key = f"{exp}|{side}|{r['strike']:g}"
                oi_map[key] = int(r["openInterest"])
                # OI≥50: 排除新挂合约的 vol/OI 假天文数
                if (r["volume"] >= MIN_VOL and r["openInterest"] >= 50
                        and r["volume"] >= VOI * r["openInterest"]):
                    cands.append({"k": key, "vol": int(r["volume"]),
                                  "oi": int(r["openInterest"])})
    return call_p, put_p, cands, oi_map


def run() -> dict:
    today = dt.date.today().isoformat()
    try:
        prev = json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        prev = {}

    rows, all_cands, oi_all, failed = [], {}, {}, []
    for tk in C.WATCHLIST:
        try:
            cp, pp, cands, oi_map = _scan(tk)
        except Exception:
            failed.append(tk)
            continue
        oi_all[tk] = oi_map
        if cands:
            all_cands[tk] = cands
        tot = cp + pp
        if max(cp, pp) >= MIN_PREM and tot > 0:
            dirn = "C" if cp >= 2 * pp else ("P" if pp >= 2 * cp else "≈")
            best_voi = max((c["vol"] / max(c["oi"], 1) for c in cands), default=0)
            rows.append((tk, dirn, max(cp, pp), best_voi))

    live = bool(rows)          # 盘前跑时权利金≈0 → 只做确认
    rows.sort(key=lambda x: -x[2])

    # T+1 确认: 用今日 OI 核对上一次的候选
    confirms = []
    if prev.get("date") and prev.get("date") != today:
        for tk, cands in prev.get("cands", {}).items():
            cur = oi_all.get(tk, {})
            for c in cands:
                if c["k"] not in cur:
                    continue
                delta = cur[c["k"]] - c["oi"]
                ok = delta >= CONFIRM_R * c["vol"]
                exp, side, strike = c["k"].split("|")
                confirms.append((tk, side, strike, exp[5:], ok, delta))

    lines = []
    if live:
        items = [f"{tk}{d}${p/1e6:.0f}M" + (f"(v/oi{min(v, 99):.1f})" if v >= VOI else "")
                 for tk, d, p, v in rows[:TOP_N]]
        lines.append("  今日: " + " ".join(items))
    else:
        lines.append("  今日: 无快照(盘前/量未达标)")
    if confirms:
        cf = [f"{tk}{s}{k}({e}){'✅开仓' if ok else '✗未增'}"
              for tk, s, k, e, ok, _ in confirms[:4]]
        lines.append("  T+1核对: " + " ".join(cf))
    if failed:
        lines.append(f"  (拉取失败 {len(failed)} 只: {' '.join(failed[:4])})")

    print("=" * 96)
    print("【期权异动 — vol/OI 开仓过滤·T+1 OI 确认·不猜买卖方向】")
    for ln in lines:
        print(ln)
    print("=" * 96)

    if live:               # 只有拿到有效快照才覆盖候选, 盘前跑不清空
        STATE.write_text(json.dumps({"date": today, "cands": all_cands},
                                    ensure_ascii=False), encoding="utf-8")
    return {"lines": lines, "live": live}


if __name__ == "__main__":
    run()
