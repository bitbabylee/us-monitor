# -*- coding: utf-8 -*-
"""模块16：A股资金面周频天气 —— 量化指增超额 + 私募仓位 + 风格温度计。

前两个数没有免费API(排排网/朝阳永续周稿), 人工周更(30秒):
    python3 -m us_monitor.m16_weekly --cang 83.7 --zzchao "+0.4" \
        --date 2026-07-10 --note "近4年新高"
风格温度计全自动: 中证1000-沪深300 五日差, 正=小票扩散环境(量化/题材友好),
负=缩圈防守(抱团权重)。三者都不给买卖信号, 只定"环境"。
数据过期 >CN_WEEKLY_STALE 天 → 标⚠️提醒更新。
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import yfinance as yf

from . import config as C

STATE = Path(__file__).parent / ".cn_weekly.json"
STALE_DAYS = 12
CANG_HIGH, CANG_LOW = 83.0, 75.0     # 仓位高位/有子弹的经验分界
CSI1000 = "512100.SS"          # 中证1000ETF(指数000852在yf仅1行, 用ETF代理)
BENCH_ETF = "510300.SS"        # 沪深300ETF(与分子同为ETF口径, 免指数/基金偏差)


def _load() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _style_gauge():
    """中证1000 vs 沪深300 五日差(pct)。失败返回 None。"""
    try:
        df = yf.download([CSI1000, BENCH_ETF], period="2mo", interval="1d",
                         auto_adjust=True, progress=False, group_by="column")
        r = {}
        for tk in (CSI1000, BENCH_ETF):
            s = df["Close"][tk].dropna()
            r[tk] = (s.iloc[-1] / s.iloc[-6] - 1) * 100
        return r[CSI1000] - r[BENCH_ETF]
    except Exception:
        return None


def run(style=None) -> dict:
    st = _load()
    today = dt.date.today()
    lines = []

    def age(datestr):
        try:
            d = dt.date.fromisoformat(datestr)
            n = (today - d).days
            return f"{datestr[5:]}" + (f"⚠️{n}天前" if n > STALE_DAYS else "")
        except Exception:
            return "日期?"

    z = st.get("zzchao")
    lines.append(f"  指增超额: {z}% ({age(st.get('zzchao_date', ''))})" if z is not None
                 else "  指增超额: 未更新(26H1收窄,500/1000弱)")
    cg = st.get("cang")
    if cg is not None:
        env = ("高位·加仓空间有限" if cg >= CANG_HIGH else
               "有子弹" if cg <= CANG_LOW else "中性")
        note = st.get("note", "")
        lines.append(f"  私募仓位: {cg}% ({age(st.get('cang_date', ''))}) {env}"
                     + (f"·{note}" if note else ""))
    else:
        lines.append("  私募仓位: 未更新")
    if style is None:
        style = _style_gauge()
    if style is not None:
        mood = "扩散友好" if style > 0.5 else ("缩圈防守" if style < -0.5 else "均衡")
        lines.append(f"  风格温度: 中证1000-沪深300 5日{style:+.1f}% {mood}(自动)")

    print("=" * 96)
    print("【A股资金面周频 — 环境判定, 不给买卖信号】")
    for ln in lines:
        print(ln)
    print("=" * 96)
    return {"lines": lines}


def _set(argv):
    st = _load()
    today = dt.date.today().isoformat()
    date = None
    if "--date" in argv:
        date = argv[argv.index("--date") + 1]
    for key, skey in (("--zzchao", "zzchao"), ("--cang", "cang")):
        if key in argv:
            st[skey] = float(argv[argv.index(key) + 1].replace("%", ""))
            st[skey + "_date"] = date or today
    if "--note" in argv:
        st["note"] = argv[argv.index("--note") + 1]
    STATE.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"已写入 {STATE.name}: {st}")


if __name__ == "__main__":
    if any(a.startswith("--") for a in sys.argv[1:]):
        _set(sys.argv[1:])
    else:
        run()
