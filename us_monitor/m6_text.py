# -*- coding: utf-8 -*-
"""
模块6b：纯文本看板（姐姐原版审美: 等宽、分隔线、文字+符号）

两个产物:
  latest.html / latest.txt  精编版 —— 只列结论和例外, 60 行以内, 每天扫一眼用
  full.html                 全量版 —— 13 个模块的完整输出, 查细节用

精编原则: ①只显示有信号/有异动的, 不列全表 ②每个来源压成 1-3 行
③统一 64 字符分隔线 ④结论置顶

    python3 -m us_monitor.m6_text               # 全部（含日内）
    python3 -m us_monitor.m6_text --no-intraday
"""
import contextlib
import datetime as dt
import html
import io
import shutil
import sys
from pathlib import Path

import numpy as np

from . import config as C
from . import earnings
from .data import fetch_daily, fetch_intraday, col, NY
from . import (m1_macro, m2_sectors, m3_themes, m4_watchlist, m5_intraday,
               m7_gao, m8_alerts, m9_premarket, m10_camslim, m12_capex, m13_bogo)
from .run_all import compute_crosscheck, cross_check

OUT_DIR = Path(__file__).resolve().parent.parent / "dashboard"
W = 64

WRAP_CSS = """
:root { color-scheme: light dark; }
body { margin:0; padding:18px 14px; background:#fcfcfb; color:#111; }
@media (prefers-color-scheme: dark) { body { background:#111110; color:#e8e6dd; } }
pre { margin:0; font:13px/1.6 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
      white-space:pre; overflow-x:auto; }
a { color:#2a78d6; }
"""


def _digest(daily, m1, cam, gao, sec_df, theme_df, wl_df, intra_df,
            keep, drop, bogo, cal, pre_df) -> str:
    L = []
    bar, thin = "=" * W, "-" * W
    date = col(daily, "Close", C.BENCHMARK).index[-1].strftime("%Y-%m-%d")
    sig = {} if intra_df is None or intra_df.empty else dict(zip(intra_df["代码"], intra_df["信号"]))

    L += [bar, f"  波哥信号 · 美股日报  数据日 {date} · 生成 {dt.datetime.now():%m-%d %H:%M}", bar]

    # ── 一页结论 ──
    regime = "抱团MAGS" if m1["regime"] == "MAGS" else "广义动量MTUM"
    L += ["【结论】",
          f"  仓位上限 {cam['exposure']}（派发日{cam['dist_n']:g}/{cam['status'].split()[0]}）"
          f" · 阶段{gao['phase'].split()[0]} · 宏观{gao['macro_passed']}/{len(gao['macro'])}"
          f" · 风格:{regime}"]
    if keep:
        cc = " ".join(f"{tk}({pat.strip('【】')[:5]}·{(sig.get(tk) or '—')[:1]})" for tk, pat, _ in keep)
        L.append(f"  候选: {cc}")
    else:
        L.append("  候选: 无")
    if drop:
        L.append(f"  否决: {' '.join(tk for tk, _, _ in drop)}（{'财报' if any('财报' in c for _, _, c in drop) else '板块背离'}）")
    risks = []
    today_ny = dt.datetime.now(NY).date()
    near = [f"{d:%m-%d}{tk}" for d, tk in cal if (d - today_ny).days <= 1]
    if near:
        risks.append("财报临近: " + " ".join(near))
    if not gao.get("jpy_ok", True):
        risks.append(f"日元⚠️{gao['jpy']:.1f}")
    L.append(f"  风险: {' · '.join(risks) if risks else '无近端风险事件'}")
    L.append(thin)

    # ── 大盘 ──
    hot = "⚠️偏热" if m1["rsi"] > C.RSI_HOT else "中性"
    L += ["【大盘】",
          f"  SPX {m1['spx']:.0f} (MA50{m1['dev50']:+.1f}%) · RSI {m1['rsi']:.0f}{hot}"
          f" · VIX {m1['vix']:.1f} · MTUM/MAGS {m1['mtum_mags']:.2f}"
          f"({'破' if m1['regime'] == 'MAGS' else '上'}20日均)"]
    spark = "".join("▁▂▃▄▅▆▇█"[min(int(n), 7)] for _, n in cam["traj"][-25:])
    L.append(f"  派发轨迹 {spark} ({cam['traj'][0][1]:g}→{cam['dist_n']:g})"
             + (f" · {cam['ramp_note'][:26]}" if cam.get("ramp_note") else ""))
    miss = [n.replace("(必选)", "*") for n, ok, _ in gao["consensus"] if not ok]
    L.append(f"  阶段{gao['phase']}: 恐慌{gao['p_score']}/4 共识{gao['c_score']}/5"
             + (f" 缺:{';'.join(m[:14] for m in miss)}" if miss else ""))
    mac = " ".join(f"{'✅' if ok else '✗'}{name.split()[0]}{cur}"
                   for _, name, cur, _, _, ok, _ in gao["macro"])
    L += [f"  宏观 {mac}", thin]

    # ── 板块（只列 🔥 和 🚨）──
    strong = sec_df[sec_df["诊断"].str.contains("🔥")]
    dump = sec_df[sec_df["诊断"].str.contains("🚨")]
    t_hot = theme_df[theme_df["诊断"].str.contains("🔥")]
    t_cold = theme_df[theme_df["诊断"].str.contains("🧊")]
    L.append("【板块】")
    L.append("  强: " + (" ".join(f"{r['代码']}{r['超额Alpha']:+.1f}%" for _, r in strong.iterrows()) or "无"))
    if len(dump):
        L.append("  🚨砸盘: " + " ".join(f"{r['代码']}{r['超额Alpha']:+.1f}%(量{r['量倍']:.1f}x)"
                                        for _, r in dump.iterrows()))
    if len(t_hot):
        L.append("  主题🔥: " + " ".join(f"{r['主题'].split('/')[0][-6:]}{r['超额Alpha']:+.1f}%[{r['领头羊'].split()[0]}]"
                                        for _, r in t_hot.iterrows()))
    if len(t_cold):
        L.append("  主题🧊: " + " ".join(f"{r['主题'].split('/')[0][-6:]}{r['超额Alpha']:+.1f}%"
                                        for _, r in t_cold.iterrows()))
    L.append(thin)

    # ── 个股（只列有信号的）──
    L.append("【个股信号】")
    hits = wl_df[wl_df["标记"] != "⚪"]
    for _, r in hits.iterrows():
        efl = f"  ‼️{r['财报'][:16]}" if r["财报"] else ""
        L.append(f"  {r['标记']}{r['代码']:>5} {r['形态'].strip('【】')}"
                 f"  日内:{(sig.get(r['代码']) or '—')[:14]}{efl}")
    if hits.empty:
        L.append("  无日线形态触发")
    # 日内例外（非观望非未成型, 且不在上面出现过）
    if intra_df is not None and not intra_df.empty:
        shown = set(hits["代码"])
        act = intra_df[~intra_df["信号"].str.startswith(("⚪", "⏳")) & ~intra_df["代码"].isin(shown)]
        if len(act):
            L.append("  其余日内异动: " + " ".join(f"{r['代码']}{r['信号'][:2]}" for _, r in act.iterrows()))
    # 盘前大动
    if pre_df is not None and len(pre_df):
        mv = pre_df[pre_df["涨跌"].abs() >= C.EXT_MOVE_ALERT]
        if len(mv):
            L.append("  盘前/盘后±2%: " + " ".join(f"{r['代码']}{r['涨跌']:+.1f}%" for _, r in mv.iterrows()))
    L.append(thin)

    # ── 波哥 ──
    rows = (bogo or {}).get("rows", [])
    if rows:
        d0 = bogo.get("date")
        s_today = [r["代码"] for r in rows if r["信号"] == "strong" and r["信号日"] == d0]
        ov = [r["代码"] for r in bogo.get("overlap", [])]
        L += ["【波哥七维】",
              f"  当日strong: {' '.join(s_today) or '无'} · 全单{len(rows)}只"
              f" · 与本池交集: {' '.join(ov) or '无'}", thin]

    # ── 财报（未来7日, 一行一天）──
    wk = ["一", "二", "三", "四", "五", "六", "日"]
    nxt = [(d, tk) for d, tk in cal if (d - today_ny).days <= 7]
    if nxt:
        by = {}
        for d, tk in nxt:
            by.setdefault(d, []).append(tk)
        L.append("【财报7日】 " + " · ".join(f"{d:%m-%d}(周{wk[d.weekday()]}){'/'.join(v)}"
                                          for d, v in sorted(by.items())))
    L += [bar, "免责: 信息整理非投资建议 · 各方法互相独立且未回测, 详见手册", bar]
    return "\n".join(L)


def build(with_intraday=True) -> Path:
    # 先跑全量版（顺便拿到所有返回值）
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        daily = fetch_daily(C.all_daily_tickers())
        m1 = m1_macro.run(daily)
        print()
        cam = m10_camslim.run(daily)
        print()
        gao = m7_gao.run(daily)
        print()
        m8_alerts.run(daily, gao)
        print()
        sec_df = m2_sectors.run(daily)
        print()
        theme_df = m3_themes.run(daily)
        print()
        wl_df = m4_watchlist.run(daily)
        print()
        intra_df = None
        if with_intraday:
            intra = fetch_intraday(C.WATCHLIST)
            intra_df = m5_intraday.run(intra, daily)
            print()
        cross_check(sec_df, theme_df, wl_df, intra_df)
        print()
        pre_df = m9_premarket.run(daily)
        print()
        bogo = m13_bogo.run()
        print()
        try:
            m12_capex.run(refresh=True)
        except Exception as exc:
            print(f"【AI 资本周期看门狗】未验证: {exc}")
    full_text = buf.getvalue()

    keep, drop = compute_crosscheck(sec_df, theme_df, wl_df)
    cal = earnings.upcoming(C.WATCHLIST, days=14)
    digest = _digest(daily, m1, cam, gao, sec_df, theme_df, wl_df, intra_df,
                     keep, drop, bogo, cal, pre_df)

    OUT_DIR.mkdir(exist_ok=True)
    date = col(daily, "Close", C.BENCHMARK).index[-1].strftime("%Y-%m-%d")

    (OUT_DIR / "latest.txt").write_text(digest, encoding="utf-8")

    def page(title, links, text):
        return (f'<meta charset="utf-8">'
                f'<meta name="viewport" content="width=device-width,initial-scale=1">'
                f'<title>{title}</title><style>{WRAP_CSS}</style>'
                f'<pre>{links}\n\n' + html.escape(text) + "</pre>")

    out = OUT_DIR / f"dashboard_{date}.html"
    out.write_text(page(f"波哥信号 {date}",
                        '[<a href="full.html">全量明细</a>] [<a href="rich.html">图形版</a>] '
                        '[<a href="manual.html">手册</a>] [<a href="history.html">历史</a>]',
                        digest), encoding="utf-8")
    shutil.copy(out, OUT_DIR / "latest.html")

    (OUT_DIR / "full.html").write_text(
        page(f"波哥信号 全量 {date}", '[<a href="latest.html">← 精编版</a>]', full_text),
        encoding="utf-8")

    print(f"✅ 精编版: {out}（{len(digest.splitlines())} 行）+ full.html", file=sys.stderr)
    return out


if __name__ == "__main__":
    build(with_intraday="--no-intraday" not in sys.argv)
