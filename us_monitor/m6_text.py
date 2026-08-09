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
W = 48   # 48字符≈360px, iPhone竖屏不横滚

WRAP_CSS = """
:root { color-scheme: light dark; }
body { margin:0; padding:18px 14px; background:#fcfcfb; color:#111; }
@media (prefers-color-scheme: dark) { body { background:#111110; color:#e8e6dd; } }
pre { margin:0; font:13px/1.6 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
      white-space:pre; overflow-x:auto; }
@media (max-width:640px) {
  body { padding:12px 8px; }
  pre { font-size:12px; white-space:pre-wrap; overflow-wrap:anywhere; }
}
a { color:#2a78d6; }
"""


def _digest(daily, m1, cam, gao, sec_df, theme_df, wl_df, intra_df,
            keep, drop, bogo, cal, pre_df) -> str:
    from . import tv
    rows_b = (bogo or {}).get("rows", [])
    tv.warm(C.all_daily_tickers() + [r["代码"] for r in rows_b])
    S = tv.symbol                      # 'PLTR' -> 'NASDAQ:PLTR'
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
        cc = " ".join(f"{S(tk)}({pat.strip('【】')[:5]}·{(sig.get(tk) or '—')[:1]})" for tk, pat, _ in keep)
        L.append(f"  候选: {cc}")
    else:
        L.append("  候选: 无")
    if drop:
        L.append("  否决: " + " ".join(
            f"{S(tk)}({'财报' if '财报' in c else '板块背离'})" for tk, _, c in drop))
    risks = []
    today_ny = dt.datetime.now(NY).date()
    near = [f"{d:%m-%d}{S(tk)}{chr(10003) if tk in C.EARNINGS_VERIFIED else chr(63)}" for d, tk in cal if (d - today_ny).days <= 1]
    if near:
        risks.append("财报临近: " + " ".join(near))
    if not gao.get("jpy_ok", True):
        risks.append(f"日元⚠️{gao['jpy']:.1f}")
    L.append(f"  风险: {' · '.join(risks) if risks else '无近端风险事件'}")
    L += ["【口径】各节相互独立·未互相验证:",
          "  仓位=CAMSLIM(欧奈尔) 阶段=高老师 宏观=Brendon 均独立",
          "  个股信号=日线形态×日内择时(同一价格两个粒度的串联,",
          "  资格+时机, 不构成互证) · 波哥独立, 唯一交叉点=🔗交集",
          thin]

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
    L.append("  强: " + (" ".join(f"{S(r['代码'])}{r['超额Alpha']:+.1f}%" for _, r in strong.iterrows()) or "无"))
    if len(dump):
        L.append("  🚨砸盘: " + " ".join(f"{S(r['代码'])}{r['超额Alpha']:+.1f}%(量{r['量倍']:.1f}x)"
                                        for _, r in dump.iterrows()))
    if len(t_hot):
        L.append("  主题🔥: " + " ".join(f"{r['主题'].split('/')[0][-6:]}{r['超额Alpha']:+.1f}%[{S(r['领头羊'].split()[0])}]"
                                        for _, r in t_hot.iterrows()))
    if len(t_cold):
        L.append("  主题🧊: " + " ".join(f"{r['主题'].split('/')[0][-6:]}{r['超额Alpha']:+.1f}%"
                                        for _, r in t_cold.iterrows()))
    L.append(thin)

    # ── 波哥（近三天强信号, 放个股最上面）──
    if rows_b:
        days3 = sorted({r["信号日"] for r in rows_b}, reverse=True)[:3]
        s3 = [r for r in rows_b if r["信号"] == "strong" and r["信号日"] in days3]
        ov = [S(r["代码"]) for r in bogo.get("overlap", [])]
        L.append("【波哥七维】近3日strong:")
        for d0 in days3:
            grp = [r for r in s3 if r["信号日"] == d0]
            if grp:
                L.append(f"  {d0}: " + " ".join(
                    f"{S(r['代码'])}(Fit{r['Fit']})" for r in grp))
        L.append(f"  与本池交集: {' '.join(ov) or '无'}")
        L.append(thin)

    # ── 个股（按行动分类, 不是平铺）──
    L.append("【个股信号】= 日线资格 × 日内时机（同源串联）")
    hits = wl_df[wl_df["标记"] != "⚪"]
    execu, wait, clash, earn = [], [], [], []
    for _, r in hits.iterrows():
        tk, pat = r["代码"], r["形态"].strip("【】")[:8]
        s_ = sig.get(tk, "")
        item = f"{S(tk)}[{r['标记']}{pat}"
        if r["财报"]:
            vfy = "✓" if tk in C.EARNINGS_VERIFIED else "?"
            earn.append(f"{item}] {r['财报'][:12]}{vfy}")
        elif s_.startswith(("🟢", "🔥")):
            execu.append(f"{item}+{s_[:6].strip()}]")
        elif s_.startswith("🔴"):
            clash.append(f"{item}/日内{s_[:6].strip()}]")
        else:
            wait.append(f"{item}] {(s_[:5] or '—')}")
    if execu:
        L.append("  ▶ 日线+日内同向: " + " ".join(execu))
    if wait:
        L.append("  ▶ 等时机(日内未给买点): " + " ".join(wait))
    if clash:
        L.append("  ▶ 冲突(日线买点/日内破位): " + " ".join(clash))
    if earn:
        L.append("  ▶ 财报窗口(信号作废): " + " ".join(earn))
    if hits.empty:
        L.append("  无日线形态触发")
    if intra_df is not None and not intra_df.empty:
        shown = set(hits["代码"])
        act = intra_df[~intra_df["信号"].str.startswith(("⚪", "⏳")) & ~intra_df["代码"].isin(shown)]
        if len(act):
            L.append("  其余日内异动: " + " ".join(f"{S(r['代码'])}{r['信号'][:2]}" for _, r in act.iterrows()))
    if pre_df is not None and len(pre_df):
        mv = pre_df[pre_df["涨跌"].abs() >= C.EXT_MOVE_ALERT]
        if len(mv):
            L.append("  盘前/盘后±2%: " + " ".join(f"{S(r['代码'])}{r['涨跌']:+.1f}%" for _, r in mv.iterrows()))
    L.append(thin)

    # ── 财报（未来7日, 一行一天）──
    wk = ["一", "二", "三", "四", "五", "六", "日"]
    nxt = [(d, tk) for d, tk in cal if (d - today_ny).days <= 7]
    if nxt:
        by = {}
        for d, tk in nxt:
            by.setdefault(d, []).append(tk)
        L.append("【财报7日】(✓=已核实官方公告 ?=仅来自yahoo/xlsx需二次核实) " + " · ".join(f"{d:%m-%d}(周{wk[d.weekday()]}){'/'.join(S(x) + ('✓' if x in C.EARNINGS_VERIFIED else '?') for x in v)}"
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
                        '[<a href="bogo.html">波哥强信号</a>] [<a href="rich.html">图形版(全量明细)</a>] '
                        '[<a href="manual.html">手册</a>] [<a href="history.html">历史</a>]',
                        digest), encoding="utf-8")
    shutil.copy(out, OUT_DIR / "latest.html")

    print(f"✅ 精编版: {out}（{len(digest.splitlines())} 行）", file=sys.stderr)
    return out


if __name__ == "__main__":
    build(with_intraday="--no-intraday" not in sys.argv)
