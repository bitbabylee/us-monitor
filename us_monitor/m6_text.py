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
               m7_gao, m8_alerts, m9_premarket, m10_camslim, m12_capex, m13_bogo,
               m15_cn, m16_weekly, m17_optflow, m18_trend)
from .run_all import compute_crosscheck, cross_check

OUT_DIR = Path(__file__).resolve().parent.parent / "dashboard"
W = 48   # 48字符≈360px, iPhone竖屏不横滚

WRAP_CSS = """
:root { color-scheme: light dark; }
body { margin:0; padding:18px 14px; background:#fcfcfb; color:#111; }
@media (prefers-color-scheme: dark) { body { background:#111110; color:#e8e6dd; } }
pre { margin:0; font:13px/1.6 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
      white-space:pre-wrap; overflow-wrap:anywhere; }
@media (max-width:640px) {
  body { padding:12px 8px; }
  pre { font-size:12px; white-space:pre-wrap; overflow-wrap:anywhere; }
}
a { color:#2a78d6; }
"""


SHORT_PAT = {"Pocket Pivot 口袋支点": "口袋支点", "20日箱体突破": "箱体突破",
             "EMA10/21 金叉启动": "EMA金叉", "10 EMA 强动能回调": "10EMA回调",
             "超跌反弹起爆点": "超跌反弹"}


def _sp(pat):
    return SHORT_PAT.get(pat.strip("【】"), pat.strip("【】")[:6])


def _ss(sig):
    """日内信号短名: 去括号尾巴 '🟢 稳健买点（温和...' -> '🟢稳健买点'"""
    return (sig or "—").split("（")[0].replace(" ", "")[:10]


def _digest(daily, m1, cam, gao, sec_df, theme_df, wl_df, intra_df,
            keep, drop, bogo, cal, pre_df, cn=None, wkly=None, opt=None,
            trd=None) -> str:
    from . import tv
    tv.warm(C.all_daily_tickers())
    S = tv.symbol
    L = []
    bar, thin = "=" * W, "-" * W
    date = col(daily, "Close", C.BENCHMARK).index[-1].strftime("%Y-%m-%d")
    sig = {} if intra_df is None or intra_df.empty else dict(zip(intra_df["代码"], intra_df["信号"]))
    det = {} if intra_df is None or intra_df.empty else dict(zip(intra_df["代码"], intra_df["细节"]))
    today_ny = dt.datetime.now(NY).date()
    vfy = lambda tk: "✓" if tk in C.EARNINGS_VERIFIED else "?"

    L += [bar, f"  波哥信号 · 美股日报  {date} · 生成 {dt.datetime.now():%m-%d %H:%M}", bar]

    # ── 结论: 一行 ──
    regime = "抱团MAGS" if m1["regime"] == "MAGS" else "动量MTUM"
    L += [f"【结论】仓位上限 {cam['exposure']} · 阶段{gao['phase'].split(' ')[0]}"
          f" · 宏观{gao['macro_passed']}/{len(gao['macro'])} · {regime}", thin]

    # ── 候选/否决/风险: 一项一行, 列对齐 ──
    L.append(f"【候选】{len(keep)} 只（形态+板块确认+无财报风险·未回测）")
    for tk, pat, _ in keep:
        s_ = sig.get(tk, "—")
        L.append(f"  {S(tk):<13} {_sp(pat):<9} 日内:{_ss(s_)}")
    if not keep:
        L.append("  无")
    if drop:
        L.append("【否决】")
        for tk, _, c in drop:
            why = "财报窗口" if "财报" in c else "板块背离"
            L.append(f"  {S(tk):<13} {why}{vfy(tk) if '财报' in c else ''}")
    near = [f"{d:%m-%d} {S(tk)}{vfy(tk)}" for d, tk in cal if (d - today_ny).days <= 1]
    risk = []
    if near:
        risk.append("财报临近 " + " · ".join(near))
    if not gao.get("jpy_ok", True):
        risk.append(f"日元⚠️{gao['jpy']:.1f}")
    L += [f"【风险】{' · '.join(risk) if risk else '无近端风险事件'}", thin]

    # ── 大盘: 每行一个主题 ──
    hot = "⚠️偏热" if m1["rsi"] > C.RSI_HOT else ""
    L += ["【大盘】",
          f"  SPX {m1['spx']:.0f} (MA50{m1['dev50']:+.1f}%) · RSI {m1['rsi']:.0f}{hot} · VIX {m1['vix']:.1f}",
          f"  风格: MTUM/MAGS {m1['mtum_mags']:.2f} {'跌破' if m1['regime']=='MAGS' else '站上'}20日均 → {regime}"]
    if m1.get("factors"):
        L.append("  日性质(因子ETF超额·非纯因子): "
                 + " ".join(f"{n}{v:+.1f}" for n, v in m1["factors"].items())
                 + f" → {m1['day_nature']}")
    spark = "".join("▁▂▃▄▅▆▇█"[min(int(n), 7)] for _, n in cam["traj"][-25:])
    L.append(f"  派发 {spark} ({cam['dist_n']:g}/吸{cam.get('acc_n', '?')}) → 仓位{cam['exposure']}")
    miss = [n.replace("(必选)", "*") for n, ok, _ in gao["consensus"] if not ok]
    L.append(f"  阶段{gao['phase']} 恐慌{gao['p_score']}/4 共识{gao['c_score']}/5"
             + (f" 缺:{miss[0][:12]}" if miss else ""))
    L.append("  宏观 " + " ".join(f"{'✅' if ok else '✗'}{name.split()[0]}{cur}"
                                 for _, name, cur, _, _, ok, _ in gao["macro"]))
    L.append(thin)

    # ── 板块: 一类一行, 主题竖排 ──
    strong = sec_df[sec_df["诊断"].str.contains("🔥")]
    dump = sec_df[sec_df["诊断"].str.contains("🚨")]
    L.append("【板块】")
    L.append("  强: " + (" · ".join(f"{S(r['代码'])}{r['超额Alpha']:+.1f}%"
                                   for _, r in strong.iterrows()) or "无"))
    if len(dump):
        L.append("  🚨砸盘: " + " · ".join(f"{S(r['代码'])}{r['超额Alpha']:+.1f}%(量{r['量倍']:.1f}x)"
                                          for _, r in dump.iterrows()))
    t_hot = theme_df[theme_df["诊断"].str.contains("🔥")]
    for _, r in t_hot.iterrows():
        nm = r["主题"].split("/")[0].replace("\ufe0f", "").strip()[-6:]
        L.append(f"  主题🔥 {nm:<7}{r['超额Alpha']:+.1f}%  龙头 {S(r['领头羊'].split()[0])}")
    t_cold = theme_df[theme_df["诊断"].str.contains("🧊")]
    for _, r in t_cold.iterrows():
        nm = r["主题"].split("/")[0].strip()[-6:]
        L.append(f"  主题🧊 {nm:<7}{r['超额Alpha']:+.1f}%")
    L.append(thin)

    # ── 个股: 分类, 一票一行 ──
    L.append("【个股信号】日线资格 × 日内时机（同源串联·未回测）")
    hits = wl_df[wl_df["标记"] != "⚪"]
    cats = {"exec": [], "wait": [], "clash": [], "earn": []}
    for _, r in hits.iterrows():
        tk = r["代码"]
        s_ = sig.get(tk, "")
        if r["财报"]:
            cats["earn"].append((r, s_))
        elif s_.startswith(("🟢", "🔥")):
            cats["exec"].append((r, s_))
        elif s_.startswith("🔴"):
            cats["clash"].append((r, s_))
        else:
            cats["wait"].append((r, s_))
    def emit(key, title):
        if not cats[key]:
            return
        L.append(f" ▶ {title}")
        for r, s_ in cats[key]:
            tail = (f"{r['财报'][:14]}{vfy(r['代码'])}" if key == "earn" else _ss(s_))
            L.append(f"   {S(r['代码']):<13} {r['标记']}{_sp(r['形态']):<9} {tail}")
    emit("exec", "日线+日内同向")
    emit("wait", "等时机（日内未给买点）")
    emit("clash", "冲突（日线买点/日内破位）")
    emit("earn", "财报窗口（信号作废）")
    if hits.empty:
        L.append("  无日线形态触发")
    if intra_df is not None and not intra_df.empty:
        shown = set(hits["代码"])
        act = intra_df[~intra_df["信号"].str.startswith(("⚪", "⏳")) & ~intra_df["代码"].isin(shown)]
        if len(act):
            items = [f"{S(r['代码'])}{r['信号'][:2]}" for _, r in act.iterrows()]
            for k in range(0, len(items), 4):        # 每行最多4个
                L.append(("  日内异动: " if k == 0 else "            ") + " ".join(items[k:k+4]))
    if pre_df is not None and len(pre_df):
        mv = pre_df[pre_df["涨跌"].abs() >= C.EXT_MOVE_ALERT]
        if len(mv):
            L.append("  盘前±2%: " + " ".join(f"{S(r['代码'])}{r['涨跌']:+.1f}%" for _, r in mv.iterrows()))
    L.append(thin)

    # ── 走势中频: 只报广度与迁移, 全表看控制台 ──
    if trd:
        L.append("【走势中频】Weinstein阶段·周~月尺度(中美混池)")
        L += trd["lines"]
        L.append(thin)

    # ── 期权异动: 佐证层, 不进信号链 ──
    if opt:
        L.append("【期权异动】新钱过滤(v/oi≥1.5)·T+1确认·仅佐证")
        L += opt["lines"]
        L.append(thin)

    # ── 财报: 一天一行 ──
    nxt = [(d, tk) for d, tk in cal if (d - today_ny).days <= 7]
    if nxt:
        wk = ["一", "二", "三", "四", "五", "六", "日"]
        by = {}
        for d, tk in nxt:
            by.setdefault(d, []).append(tk)
        L.append("【财报7日】✓=已核官方 ?=仅yahoo/xlsx待核")
        for d, v in sorted(by.items()):
            L.append(f"  {d:%m-%d} 周{wk[d.weekday()]}  " + " ".join(f"{S(x)}{vfy(x)}" for x in v))
        L.append(thin)

    # ── A股重演: 五条件判定, 一条一行 ──
    if cn:
        L.append(f"【A股重演】反转/反弹五条件 (截至{cn['date']}·独立体系)")
        L.append(f"  判定: {cn['verdict']}  反转条件 {cn['score']}/{cn['valid']}")
        for name, ok, detail in cn["checks"]:
            mark = "？" if ok is None else ("✅" if bool(ok) else "✗")
            L.append(f"  {mark}{name} {detail}")
        L.append("  四棒5日α(领/改/弱/落·↑↓=加速): "
                 + " ".join(f"{n}{a:+.0f}{q}{'↑' if acc > 0 else '↓'}"
                            for n, a, q, acc in cn["batons"]))
        if wkly:
            L.append("  资金面周频(环境非信号):")
            L += ["  " + ln.lstrip() for ln in wkly["lines"]]
        today_cn = dt.date.today()
        rvs = [(dt.date.fromisoformat(d), s) for d, s in getattr(C, "CN_REVIEWS", [])]
        due = [(d, s) for d, s in rvs if (d - today_cn).days >= -3]
        if due:
            L.append("  复评节点(到期强制重估):")
            for d, s in due:
                n = (d - today_cn).days
                flag = "🔔到期" if n <= 3 else f"T-{n}"
                L.append(f"  {d:%m-%d} {flag} {s}")
        L.append(thin)

    # ── 口径移到底部 ──
    L += ["【口径】仓位=CAMSLIM 阶段=高老师 宏观=Brendon 均独立未互证;",
          "  个股=日线×日内同源串联; 波哥独立成页与本报无交互",
          bar, "免责: 信息整理非投资建议 · 全部方法未回测", bar]
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
        print()
        try:
            cn = m15_cn.run()
        except Exception as exc:
            cn = None
            print(f"【A股重演监控】失败: {exc}")
        print()
        try:
            wk = m16_weekly.run()
        except Exception as exc:
            wk = None
            print(f"【A股资金面周频】失败: {exc}")
        print()
        try:
            opt = m17_optflow.run()
        except Exception as exc:
            opt = None
            print(f"【期权异动】失败: {exc}")
        print()
        try:
            trd = m18_trend.run(daily)
        except Exception as exc:
            trd = None
            print(f"【走势中频】失败: {exc}")
    full_text = buf.getvalue()

    keep, drop = compute_crosscheck(sec_df, theme_df, wl_df)
    cal = earnings.upcoming(C.WATCHLIST, days=14)
    digest = _digest(daily, m1, cam, gao, sec_df, theme_df, wl_df, intra_df,
                     keep, drop, bogo, cal, pre_df, cn, wk, opt, trd)

    OUT_DIR.mkdir(exist_ok=True)
    date = col(daily, "Close", C.BENCHMARK).index[-1].strftime("%Y-%m-%d")

    (OUT_DIR / "latest.txt").write_text(digest, encoding="utf-8")

    def _clickable(escaped: str) -> str:
        """把正文里所有 '交易所:代码' 变成 TradingView 图表链接(转义后再替换, 防注入)。"""
        import re as _re
        return _re.sub(
            r"\b([A-Z]{2,6}):([A-Z0-9]{1,6})\b",   # NASDAQ 有6个字母, 别写成{2,5}
            lambda m: (f'<a href="https://www.tradingview.com/chart/?symbol='
                       f'{m.group(1)}%3A{m.group(2)}" target="_blank" '
                       f'rel="noopener" style="color:inherit">{m.group(0)}</a>'),
            escaped)

    def page(title, links, text):
        return (f'<meta charset="utf-8">'
                f'<meta name="viewport" content="width=device-width,initial-scale=1">'
                f'<title>{title}</title><style>{WRAP_CSS}</style>'
                f'<pre>{links}\n\n' + _clickable(html.escape(text)) + "</pre>")

    out = OUT_DIR / f"dashboard_{date}.html"
    out.write_text(page(f"波哥信号 {date}",
                        '[<a href="rich.html">图形版</a>] '
                        '[<a href="manual.html">手册</a>] [<a href="history.html">历史</a>]',
                        digest), encoding="utf-8")
    shutil.copy(out, OUT_DIR / "latest.html")

    print(f"✅ 精编版: {out}（{len(digest.splitlines())} 行）", file=sys.stderr)
    return out


if __name__ == "__main__":
    build(with_intraday="--no-intraday" not in sys.argv)
