# -*- coding: utf-8 -*-
"""
模块6：HTML 仪表盘 — 把 m1~m5 + cross-check 渲染成一张自包含网页。

    python3 -m us_monitor.m6_dashboard               # 全部（含日内）
    python3 -m us_monitor.m6_dashboard --no-intraday # 只跑日线

输出: dashboard/dashboard_<日期>.html 和 dashboard/latest.html
"""
import contextlib
import html
import io
import shutil
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from . import config as C
from . import earnings
from . import tv
from .data import fetch_daily, fetch_intraday
from . import (m1_macro, m2_sectors, m3_themes, m4_watchlist, m5_intraday,
               m7_gao, m8_alerts, m9_premarket, m10_camslim, m12_capex, m13_bogo)
from .run_all import compute_crosscheck

OUT_DIR = Path(__file__).resolve().parent.parent / "dashboard"

# ── 调色板（dataviz 参考实例, 蓝↔红 diverging + status 四色, 双主题）──
CSS = """
:root {
  color-scheme: light;
  --page:#f9f9f7; --surface:#fcfcfb; --ink:#0b0b0b; --ink2:#52514e;
  --muted:#898781; --grid:#e1e0d9; --border:rgba(11,11,11,.10);
  --pos:#2a78d6; --neg:#e34948; --zero:#f0efec;
  --good:#0ca30c; --warn:#fab219; --serious:#ec835a; --critical:#d03b3b;
  --good-text:#006300;
}
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) {
  color-scheme: dark;
  --page:#0d0d0d; --surface:#1a1a19; --ink:#ffffff; --ink2:#c3c2b7;
  --muted:#898781; --grid:#2c2c2a; --border:rgba(255,255,255,.10);
  --pos:#3987e5; --neg:#e66767; --zero:#383835;
  --good-text:#0ca30c;
}}
:root[data-theme="dark"] {
  color-scheme: dark;
  --page:#0d0d0d; --surface:#1a1a19; --ink:#ffffff; --ink2:#c3c2b7;
  --muted:#898781; --grid:#2c2c2a; --border:rgba(255,255,255,.10);
  --pos:#3987e5; --neg:#e66767; --zero:#383835;
  --good-text:#0ca30c;
}
* { box-sizing:border-box; margin:0; }
body { background:var(--page); color:var(--ink); padding:20px;
  font:14px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif; }
h1 { font-size:19px; } h1 small { color:var(--muted); font-weight:400; font-size:12px; }
h2 { font-size:14px; color:var(--ink2); margin:0 0 10px; font-weight:600; }
.card { background:var(--surface); border:1px solid var(--border);
  border-radius:10px; padding:14px 16px; margin-top:14px; overflow-x:auto; }
.tiles { display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr)); gap:14px; margin-top:14px; }
.tile { background:var(--surface); border:1px solid var(--border); border-radius:10px; padding:12px 16px; }
.tile .k { color:var(--muted); font-size:12px; }
.tile .v { font-size:24px; font-weight:650; margin-top:2px; }
.tile .s { color:var(--ink2); font-size:12px; margin-top:2px; }
table { border-collapse:collapse; width:100%; font-variant-numeric:tabular-nums; }
th { color:var(--muted); font-weight:500; font-size:12px; text-align:right;
  padding:4px 8px; border-bottom:1px solid var(--grid); white-space:nowrap; }
td { padding:4px 8px; text-align:right; border-bottom:1px solid var(--grid); white-space:nowrap; }
tr:last-child td { border-bottom:none; }
tr:hover td { background:color-mix(in srgb, var(--ink) 4%, transparent); }
th.l, td.l { text-align:left; }
.num-pos { color:var(--pos); } .num-neg { color:var(--neg); }
.bar { display:inline-flex; width:150px; height:12px; vertical-align:middle; }
.bar i { display:block; height:12px; border-radius:0 4px 4px 0; }
.bar .n { border-radius:4px 0 0 4px; margin-left:auto; }
.bar-half { width:75px; border-left:none; }
.bar .zl { border-left:2px solid var(--zero); }
.badge { display:inline-block; padding:1px 8px; border-radius:999px; font-size:12px;
  border:1px solid; white-space:nowrap; }
.b-good { color:var(--good-text); border-color:var(--good); }
.b-warn { color:var(--warn); border-color:var(--warn); }
.b-serious { color:var(--serious); border-color:var(--serious); }
.b-critical { color:var(--critical); border-color:var(--critical); }
.b-pos { color:var(--pos); border-color:var(--pos); }
.b-muted { color:var(--muted); border-color:var(--grid); }
.hit td { background:color-mix(in srgb, var(--pos) 7%, transparent); }
.focus { display:grid; grid-template-columns:repeat(auto-fill,minmax(300px,1fr)); gap:10px; }
.fc { border:1px solid var(--border); border-left:3px solid var(--good); border-radius:8px; padding:10px 12px; }
.fc.drop { border-left-color:var(--critical); opacity:.75; }
.fc b { font-size:15px; } .fc .ctx { color:var(--ink2); font-size:12px; margin-top:4px; }
.footer { color:var(--muted); font-size:11px; margin-top:16px; }
"""


def esc(x) -> str:
    return html.escape(str(x))


def signed(v, fmt="+.2f", suffix="%"):
    cls = "num-pos" if v >= 0 else "num-neg"
    return f'<span class="{cls}">{v:{fmt}}{suffix}</span>'


def dbar(v, vmax):
    """diverging 水平条：中心零轴, 正→右蓝, 负→左红（2px 中性零轴线）"""
    w = 0 if vmax == 0 else min(abs(v) / vmax, 1.0) * 100
    if v >= 0:
        return (f'<span class="bar" title="{v:+.2f}%"><span class="bar-half"></span>'
                f'<span class="bar-half zl"><i style="width:{w:.0f}%;background:var(--pos)"></i></span></span>')
    return (f'<span class="bar" title="{v:+.2f}%"><span class="bar-half" style="display:flex">'
            f'<i class="n" style="width:{w:.0f}%;background:var(--neg);margin-left:auto"></i></span>'
            f'<span class="bar-half zl"></span></span>')


def sig_badge(sig: str) -> str:
    cls = ("b-good" if sig.startswith("🟢") else
           "b-pos" if sig.startswith("🔥") else
           "b-warn" if sig.startswith("🟡") else
           "b-critical" if "止损" in sig or "规避" in sig else
           "b-serious" if sig.startswith("🔴") else "b-muted")
    return f'<span class="badge {cls}">{esc(sig)}</span>'


def diag_badge(diag: str) -> str:
    cls = ("b-critical" if "砸盘" in diag else "b-pos" if "🔥" in diag
           else "b-serious" if "🧊" in diag else "b-muted")
    return f'<span class="badge {cls}">{esc(diag)}</span>'


# ── 各区块 ─────────────────────────────────────────────

def sec_gao(g):
    ph = g["phase"]
    ph_cls = "b-good" if ph.startswith("C1") else "b-warn" if ph.startswith("P1") else "b-critical"

    def items(lst):
        return "".join(
            f'<div>{"✅" if ok else "✗"} {esc(n)}</div>' for n, ok, _ in lst)
    tnx_txt = "N/A" if np.isnan(g["tnx"]) else f'{g["tnx"]:.2f}%'
    return f"""
<div class="card" id="gao"><h2>📐 高老师 · 双指数阶段日报 <small style="color:var(--muted)">QQQ=大盘 · SMH=进攻先锋 · 真反弹必须先锋带头</small></h2>
<p style="margin-bottom:8px"><span class="badge {ph_cls}" style="font-size:14px">阶段: {esc(ph)}</span>
&nbsp; 恐慌释放 <b>{g['p_score']}/4</b> · 资金共识 <b>{g['c_score']}/5</b></p>
<p style="color:var(--ink2);margin-bottom:10px">▎人话版: {esc(g['human'])}</p>
<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:12px">
  <div><b>第一关【恐慌释放】跌势止住了吗</b>{items(g['panic'])}</div>
  <div><b>第二关【资金共识】买家回来了吗</b>{items(g['consensus'])}</div>
</div>
<p style="margin-top:10px;color:var(--ink2)">核心值: QQQ {g['qqq']:.2f} · SMH {g['smh']:.2f} ·
SMH/QQQ={g['ratio']:.4f} (20日均 {g['ratio_ma20']:.4f}) &nbsp;|&nbsp;
<b>失效位: QQQ&lt;{g['stop_q']:.2f} 或 SMH&lt;{g['stop_s']:.2f}</b></p>
{macro_table(g)}</div>"""


def macro_table(g):
    """宏观确认层: 当前值 / 通过条件 / 判定 / 差距 —— 每项都能自查"""
    rows = "".join(
        f'<tr><td class="l">{"✅" if ok else "✗"} <b>{esc(sid)}</b></td>'
        f'<td class="l">{esc(name)}</td><td><b>{esc(cur)}</b></td>'
        f'<td class="l" style="color:var(--muted)">{esc(cond)}</td>'
        f'<td class="l"><span class="badge {"b-good" if ok else "b-critical"}">'
        f'{"满足" if ok else "不满足"}</span></td>'
        f'<td class="l" style="white-space:normal;color:var(--ink2)">{esc(gap)}'
        f'<br><span style="color:var(--muted);font-size:11px">含义: {esc(why)}</span></td></tr>'
        for sid, name, cur, cond, gap, ok, why in g["macro"])
    n, tot = g["macro_passed"], len(g["macro"])
    verdict = ("✅ 宏观环境支持加仓" if n >= 3 else
               "⚠️ 宏观仍有压制, 谨慎" if n >= 2 else "🚨 宏观环境不利, 防守")
    return f"""
<div style="margin-top:12px"><b style="font-size:13px">宏观确认层（Brendon 五信号自动化）—
通过 {n}/{tot} 项 · {verdict}</b>
<table style="margin-top:6px"><tr><th class="l">信号</th><th class="l">指标</th>
<th>当前值</th><th class="l">通过条件</th><th class="l">判定</th><th class="l">差距 / 含义</th></tr>
{rows}
{cta_row(g.get("cta", {}))}
</table></div>"""


def cta_row(r):
    if not r.get("ok"):
        return (f'<tr><td class="l">❓ <b>#3</b></td><td class="l">CTA 仓位</td>'
                f'<td>—</td><td class="l" style="color:var(--muted)">趋势基金转多</td>'
                f'<td class="l"><span class="badge b-muted">未验证</span></td>'
                f'<td class="l" style="color:var(--ink2)">{esc(r.get("note", "无可靠数据"))}'
                f'<br><span style="color:var(--muted);font-size:11px">'
                f'不沿用旧值或猜测</span></td></tr>')
    cls = ("b-good" if r["pos"] >= 20 else "b-critical" if r["pos"] <= -20 else "b-warn")
    legs = " | ".join(f'{n}日{"多" if up else "空"}({dev:+.1f}%)' for n, up, dev in r["legs"])
    prox = ", ".join(f"{t} {v:+.1f}%" for t, v in r["proxy"])
    return (f'<tr><td class="l">📐 <b>#3</b></td><td class="l">CTA 仓位<br>'
            f'<span style="color:var(--muted);font-size:11px">模型估算</span></td>'
            f'<td><b>{r["pos"]:+.0f}</b><span style="color:var(--muted)">/100</span></td>'
            f'<td class="l" style="color:var(--muted)">≥+20 净多 / ≤−20 净空</td>'
            f'<td class="l"><span class="badge {cls}">{esc(r["state"])}</span></td>'
            f'<td class="l" style="white-space:normal;color:var(--ink2)">趋势分解: {esc(legs)}'
            f'<br>ETF交叉验证: {esc(prox)} vs 大盘 {r["spx_5d"]:+.1f}% → <b>{esc(r["cross"])}</b>'
            f'<br><span style="color:var(--muted);font-size:11px">'
            f'⚠️ 趋势跟踪复制的模型估算，非真实仓位读数</span></td></tr>')


def sec_opportunities(keep, drop, intra_df, bogo, cam, gao):
    """🎯 最终落点：今日交易机会 —— 把所有过滤层的结果汇成一张可执行清单"""
    sig = {} if intra_df is None or intra_df.empty else dict(zip(intra_df["代码"], intra_df["信号"]))
    det = {} if intra_df is None or intra_df.empty else dict(zip(intra_df["代码"], intra_df["细节"]))
    bogo_map = {r["代码"]: r for r in (bogo or {}).get("rows", [])}

    ready, wait, avoid = [], [], []
    for tk, pat, ctx in keep:
        s = sig.get(tk, "")
        row = (tk, pat, ctx, s, det.get(tk, ""), bogo_map.get(tk))
        (ready if s.startswith(("🟢", "🔥")) else wait).append(row)
    for tk, pat, ctx in drop:
        avoid.append((tk, pat, ctx, sig.get(tk, ""), det.get(tk, ""), bogo_map.get(tk)))

    expo = cam.get("exposure", "—")
    phase = gao.get("phase", "—")

    def card(r, kind):
        tk, pat, ctx, s, d, bg = r
        border = {"ready": "var(--good)", "wait": "var(--warn)", "avoid": "var(--critical)"}[kind]
        bgline = (f'<div class="ctx">🔗 波哥七维: <b>{esc(bg["信号"])}</b> · Fit {esc(bg["Fit"])} '
                  f'· 胜率 {esc(bg["胜率"])}% · {esc(bg["主题"][:22])}</div>' if bg else "")
        return (f'<div class="fc" style="border-left-color:{border}">'
                f'{tv.link(tk)} <span style="color:var(--ink2)">{esc(pat)}</span>'
                f'<div class="ctx">{esc(ctx)}</div>'
                f'<div class="ctx">日内: {sig_badge(s) if s else "—"}'
                + (f' <span style="color:var(--muted)">{esc(d[:44])}</span>' if d else "")
                + f'</div>{bgline}</div>')

    def block(title, sub, rows, kind):
        if not rows:
            return (f'<div style="margin-top:12px"><b>{esc(title)}</b> '
                    f'<span style="color:var(--muted);font-size:12px">{esc(sub)}</span>'
                    f'<div class="ctx">— 无 —</div></div>')
        return (f'<div style="margin-top:12px"><b>{esc(title)}（{len(rows)}）</b> '
                f'<span style="color:var(--muted);font-size:12px">{esc(sub)}</span>'
                f'<div class="focus" style="margin-top:6px">'
                + "".join(card(r, kind) for r in rows) + "</div></div>")

    # 波哥强信号但不在本系统池 —— 作为「可考虑纳入观察」的补充线索
    extra = [r for r in (bogo or {}).get("rows", [])
             if r["信号"] == "strong" and not r.get("交集")][:8]
    extra_html = ("".join(
        f'<span class="badge b-muted" style="margin:2px 4px 2px 0">{tv.link(r["代码"], bold=False, show_exchange=False)}'
        f' {esc(r["主题"][:14])}</span>' for r in extra)
        if extra else '<span style="color:var(--muted)">—</span>')

    return f"""
<div class="card" id="ops" style="border:2px solid var(--good)">
<h2 style="font-size:16px;color:var(--ink)">📋 今日候选清单 <small style="color:var(--muted)">
各层过滤后的剩余项 · 仓位上限 {esc(expo)} · 阶段 {esc(phase)}</small></h2>
<div class="ctx" style="background:color-mix(in srgb,var(--warn) 12%,transparent);
border-radius:6px;padding:10px 12px;margin-bottom:8px">
<b>⚠️ 这份清单的性质：</b>它是「<b>没有被任何一层否决</b>」的剩余项，<b>不等于</b>「值得买」。
所有阈值都来自复刻与教科书默认值，<b>尚未做过任何历史回测验证</b>，没有已知胜率。
把它当<b>待研究名单</b>：从这里开始做功课，而不是照着下单。</div>
<p class="ctx">读法：先看仓位上限决定总投入，再逐个自己判断。每张卡标了日内动作和止损依据。</p>
{block("① 四层全过", "日线形态 + 板块资金确认 + 无财报风险 + 日内有买点信号", ready, "ready")}
{block("② 标的过关·时机未到", "等站回 VWAP 或放量突破", wait, "wait")}
{block("③ 已被否决", "财报窗口或板块背离 —— 记录下来是为了让你知道系统排除了什么", avoid, "avoid")}
<div style="margin-top:14px"><b>📋 波哥强信号补充线索</b>
<span style="color:var(--muted);font-size:12px">（七维回测选出但不在本系统池，可考虑纳入观察）</span>
<div style="margin-top:6px">{extra_html}</div></div>
<p class="ctx" style="margin-top:12px;color:var(--muted)">
系统只负责排除不该做的。剩下的做不做、做多大、止损放哪，由你判断并承担。</p></div>"""


def sec_bogo(d):
    """波哥七维信号汇总表"""
    rows = (d or {}).get("rows", [])
    if not rows:
        return ('<div class="card" id="bogo"><h2>🧭 波哥七维信号</h2>'
                '<p class="ctx">未找到当日 PDF（本地生成时可用）</p></div>')
    imgs = (d or {}).get("images", {})
    for r in (d or {}).get("rows", []):
        r["_latest"] = (d or {}).get("date")

    def code_cell(r):
        """有原图的代码加一个 🖼 展开按钮（点开显示波哥 PDF 那一页）"""
        link = tv.link(r["代码"])
        src = imgs.get(r["代码"])
        if not src:
            return link
        return (f'{link} <a href="{esc(src)}" target="_blank" title="波哥原图"'
                f' style="text-decoration:none">🖼</a>')

    tr = "".join(
        f'<tr class="{"hit" if r.get("交集") else ""}">'
        f'<td class="l"><span class="badge {"b-good" if r["信号"]=="strong" else "b-muted"}">'
        f'{esc(r["信号"])}</span></td><td class="l">{code_cell(r)}</td>'
        f'<td class="l">{esc(r["中文名"])}</td>'
        f'<td class="l">{sig_date(r)}</td><td>{esc(r["当日%"])}</td>' 
        f'<td>{esc(r["Fit"])}</td><td>{esc(r["胜率"])}</td><td>{esc(r["CA%"])}</td>'
        f'<td>{esc(r["Pnls%"])}</td>'
        f'<td class="l" style="white-space:normal">{"🔗 " if r.get("交集") else ""}{esc(r["主题"])}</td></tr>'
        for r in rows)
    stale = ' <span class="badge b-warn">上次快照</span>' if d.get("stale") else ""
    return f"""
<div class="card" id="bogo"><h2>🧭 波哥七维信号 <small style="color:var(--muted)">
{esc(d.get('title') or '')[:60]} · 交集 {len(d.get('overlap', []))} 只{stale}</small></h2>
<p class="ctx">波哥系统＝【回测+基本面七维】选股；本系统＝【技术面+资金面】过滤器。
高亮行 🔗 ＝ 两套独立方法共同覆盖，信号质量最高。</p>
<table><tr><th class="l">信号</th><th class="l">代码</th><th class="l">名称</th>
<th class="l">信号日</th><th>当日%</th><th>Fit</th><th>胜率</th><th>CA%</th><th>Pnls%</th>
<th class="l">主题</th></tr>{tr}</table>
{bogo_gallery(d)}</div>"""



def sig_date(r):
    """信号日列: 当日的高亮, 旧日期灰显（表按新日期在前排序）"""
    day = r.get("信号日", "")
    latest = r.get("_latest") or ""
    if day and latest and day == latest:
        return f'<span class="badge b-good">{esc(day)} 新</span>'
    return f'<span style="color:var(--muted)">{esc(day)}</span>'


def bogo_gallery(d):
    """波哥原图画廊 —— 与本系统池交集的标的优先展示"""
    imgs = (d or {}).get("images", {})
    if not imgs:
        return ""
    rows = (d or {}).get("rows", [])
    order = ([r for r in rows if r.get("交集")] + [r for r in rows if not r.get("交集")])
    cells = "".join(
        f'<figure style="margin:0"><a href="{esc(imgs[r["代码"]])}" target="_blank">'
        f'<img src="{esc(imgs[r["代码"]])}" loading="lazy" alt="{esc(r["代码"])}"'
        f' style="width:100%;border:1px solid var(--border);border-radius:6px"></a>'
        f'<figcaption style="font-size:12px;color:var(--ink2);margin-top:3px">'
        f'{"🔗 " if r.get("交集") else ""}<b>{esc(r["代码"])}</b> {esc(r["中文名"])}'
        f' · {esc(r["信号"])}</figcaption></figure>'
        for r in order if r["代码"] in imgs)
    return (f'<details style="margin-top:12px"><summary style="cursor:pointer;'
            f'color:var(--ink2);font-size:13px">🖼 波哥原图 · 当日强信号（{len(imgs)} 张，点开）</summary>'
            f'<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(420px,1fr));'
            f'gap:12px;margin-top:10px">{cells}</div></details>')


def nav():
    """顶部锚点导航 —— 页面 7000px+, 没有导航要滚很久"""
    items = [("macro", "① 宏观"), ("gao", "阶段/宏观层"),
             ("sector", "② 板块"), ("sectors", "板块榜"), ("capex", "AI资本"),
             ("stock", "③ 个股"), ("intraday", "日内信号"),
             ("bogo", "波哥七维"), ("earn", "财报"), ("watch", "观察池"),
             ("ops", "④ 候选清单")]
    links = "".join(
        f'<a href="#{i}" style="padding:4px 10px;border:1px solid var(--border);'
        f'border-radius:999px;color:var(--ink2);text-decoration:none;font-size:12px;'
        f'white-space:nowrap">{esc(t)}</a>' for i, t in items)
    return (f'<div style="display:flex;gap:6px;flex-wrap:wrap;margin:12px 0 4px;'
            f'position:sticky;top:0;background:var(--page);padding:8px 0;z-index:9">'
            f'{links}</div>')


def tier(anchor, title, sub):
    return (f'<h2 id="{anchor}" style="font-size:15px;margin:26px 0 2px;'
            f'padding:8px 0 6px;border-bottom:2px solid var(--pos);color:var(--ink)">'
            f'{esc(title)} <span style="color:var(--muted);font-weight:400;font-size:12px">'
            f'· {esc(sub)}</span></h2>')


def sec_capex(ev):
    """AI 资本周期看门狗（季度基本面, 不做择时）"""
    if not ev:
        return ""
    if ev.get("error"):
        return (f'<div class="card" id="capex"><h2>🏗️ AI 资本周期看门狗</h2>'
                f'<p class="ctx"><span class="badge b-muted">未验证</span> {esc(ev["error"])}</p></div>')
    rows = "".join(
        f'<tr><td class="l">{esc(metric)}</td><td class="l">{tv.link(tk)}</td>'
        f'<td><b>{esc(val)}</b></td><td class="l" style="color:var(--muted)">{esc(thr)}</td>'
        f'<td class="l"><span class="badge {"b-good" if ok else "b-critical"}">'
        f'{"正常" if ok else "越线"}</span></td>'
        f'<td class="l" style="white-space:normal;color:var(--ink2)">{esc(why)}</td></tr>'
        for metric, tk, val, thr, ok, why in ev["rows"])
    al = ("".join(f'<div class="ctx">{esc(a)}</div>' for a in ev["alerts"])
          if ev["alerts"] else '<div class="ctx">✅ 无指标越线</div>')
    return f"""
<div class="card" id="capex"><h2>🏗️ AI 资本周期看门狗 <small style="color:var(--muted)">
capexcycle.com · SEC/XBRL · 最新季 {esc(ev['quarter'] or '—')} · 抓取 {esc(ev['fetched'] or '—')}</small></h2>
<p class="ctx" style="margin-bottom:8px">给「AI算力 / 云计算 / AI电网」三个主题提供
<b>基本面否决权</b>——技术信号滞后, 资本开支的拐点先在这里出现。
⚠️ 季度频率、滞后 4-8 周，<b>只判主线是否成立，不做择时</b>。</p>
<table><tr><th class="l">指标</th><th class="l">公司</th><th>当前值</th>
<th class="l">临界值</th><th class="l">判定</th><th class="l">含义</th></tr>{rows}</table>
<div style="margin-top:10px"><b style="font-size:13px">报警</b>{al}</div></div>"""


def sec_camslim(k):
    """派发日体系: 卖压轨迹柱状图 + 建议仓位条（用户认为最有用的两个信息）"""
    st_cls = ("b-good" if k["status"] == "CONFIRMED UPTREND" else
              "b-critical" if "CORRECTION" in k["status"] else "b-warn")
    mx = max([n for _, n in k["traj"]] + [1])
    bars = "".join(
        f'<span title="{d:%m-%d}: {n:g}" style="display:inline-block;width:11px;'
        f'height:{max(3, n / mx * 44):.0f}px;margin-right:2px;vertical-align:bottom;'
        f'background:{"var(--critical)" if n >= C.CAM_CORRECTION else "var(--warn)" if n >= C.CAM_CAUTION else "var(--good)"};'
        f'border-radius:2px 2px 0 0"></span>' for d, n in k["traj"])
    expo_num = 100
    try:
        expo_num = int(str(k["exposure"]).rstrip("%").split("-")[-1])
    except ValueError:
        pass
    ramp = (f'<div class="ctx" style="color:var(--warn)">⚠️ {esc(k["ramp_note"])}</div>'
            if k["ramp_note"] else "")
    return f"""
<div class="card"><h2>📊 CAMSLIM 大盘健康度 · 派发日体系 <small style="color:var(--muted)">
欧奈尔/IBD · {C.CAM_WINDOW}日窗口 · 机构派发压力决定仓位</small></h2>
<p style="margin-bottom:10px"><span class="badge {st_cls}" style="font-size:14px">{esc(k['status'])}</span>
&nbsp; 派发日 <b style="font-size:18px">{k['dist_n']:g}</b> (对 {k['acc_n']} 吸筹日)
&nbsp;|&nbsp; 建议仓位 <b style="font-size:18px">{esc(k['exposure'])}</b>
&nbsp;|&nbsp; 方向 {esc(k['direction'])}</p>
<div style="height:48px;margin:10px 0">{bars}</div>
<div class="ctx">卖压轨迹（近{C.CAM_WINDOW}日, 悬停看数值）· {esc(k['pressure_read'])}</div>
{ramp}
<div style="margin-top:12px;background:var(--grid);border-radius:6px;height:22px;overflow:hidden">
  <div style="width:{expo_num}%;height:22px;background:var(--warn);text-align:center;
  line-height:22px;font-size:12px;color:#000;font-weight:600">{esc(k['exposure'])} 投入</div></div>
<p class="ctx" style="margin-top:8px">公式: min({C.CAM_EXPO_CAP}, max({C.CAM_EXPO_FLOOR}, ({C.CAM_EXPO_BASE}−派发日)×{C.CAM_EXPO_STEP}))
&nbsp;·&nbsp; 现价 {k['price']:,.2f} · 窗口高 {k['high']:,.2f} · 回撤 {k['drawdown']:+.2f}% · 周 {k['week']:+.2f}%</p>
<p class="ctx">关键事件: {esc("; ".join(k["events"]) or "无")}</p>
<details style="margin-top:12px"><summary style="cursor:pointer;color:var(--ink2);font-size:13px">
📖 怎么用这两个数字（点开）</summary>
<div style="color:var(--ink2);font-size:13px;line-height:1.7;margin-top:8px">
<p><b>派发日 = 机构在卖的天数。</b>指数收跌 ≥0.2% 且成交量比前一天大 —— 跌得有量，
说明是大资金在出货，不是散户砸盘。数的是最近 {C.CAM_WINDOW} 个交易日里有几天这样。</p>
<p><b>① 数字停在 6-7-8 不下来</b> → 机构<b>持续在卖</b>，市场卖方主导。这时候你<b>做多很难</b>：
反弹很容易就被人家卖出去。对策不是完全不做，而是 —— 只做<b>最强势</b>的个股，
突破/追高都要谨慎，<b>止损带窄一点</b>，仓位压住。</p>
<p><b>② 从高位（6-8）突然降到 4</b> → 在卖的机构少了，卖压真的小了。但<b>别一次满仓</b>：
第一天变 4 先给 20%，第二天还站在 4 才加到 40%……<b>站稳一天加一档</b>。
中间会经历 CAUTION 状态，再变牛。（这条是我们加的风控层，原版是直接按公式给满）</p>
<p><b>③ 降到 0-2</b> → 机构不卖了，强势股突破的成功率明显提高，可以放手做。</p>
<p><b>④ 仓位怎么用</b>：这是<b>总仓位上限</b>，不是叫你买满。比如显示 40%，意思是
"这个市场环境下，你的资金最多投 40%，剩下 60% 拿现金等更好的环境"。
它不告诉你买什么（那是下面的聚焦清单和日内信号干的活），只告诉你<b>该下多大注</b>。</p>
<p style="color:var(--muted)">⚠️ 大盘派发压力和个股信号是<b>两层独立的过滤</b>：
派发日高 = 少下注；个股形态+板块共振 = 下注在哪。两个都过关才动手。</p>
</div></details></div>"""


def sec_premarket(pre_df):
    if pre_df is None or pre_df.empty:
        return ""
    rows = ""
    for _, r in pre_df.iterrows():
        mark = ("🚨" if r["涨跌"] <= -C.EXT_MOVE_ALERT else
                "🔥" if r["涨跌"] >= C.EXT_MOVE_ALERT else "")
        efl = (f' <span class="badge b-critical">‼️ {esc(r["财报"])}</span>'
               if r["财报"] else "")
        hl = ' class="hit"' if mark else ""
        rows += (f'<tr{hl}><td class="l">{tv.link(r["代码"])}</td>'
                 f'<td>{r["昨收"]:.2f}</td><td>{r["延长价"]:.2f}</td>'
                 f'<td>{signed(r["涨跌"])}</td><td class="l">{esc(r["时段"])}</td>'
                 f'<td class="l">{esc(r["最后成交"])}</td>'
                 f'<td class="l" style="white-space:normal">{mark}{efl}</td></tr>')
    return (f'<div class="card"><h2>🌅 盘前/盘后雷达 · 延长时段异动 '
            f'<small style="color:var(--muted)">±{C.EXT_MOVE_ALERT}% 高亮 · '
            f'开盘前重设当日信号预期</small></h2>'
            f'<table><tr><th class="l">代码</th><th>昨收</th><th>延长价</th>'
            f'<th>延长涨跌</th><th class="l">时段</th><th class="l">最后成交</th>'
            f'<th class="l">异动/财报</th></tr>{rows}</table></div>')


def sec_alerts(cards):
    rows = ""
    for c in cards:
        bell = ' <span class="badge b-warn">🔔 状态变化</span>' if c["bell"] else ""
        detail = "".join(f'<div class="ctx">▎{k}: {esc(v)}</div>'
                         for k, v in [("逻辑", c["logic"]), ("动作", c["action"]),
                                      ("下一步", c["next"]), ("出处", c["source"])] if v)
        rows += (f'<div class="fc" style="border-left-color:var(--warn)">'
                 f'<b>{esc(c["emoji"])} {esc(c["head"])}</b>{bell}{detail}</div>')
    return (f'<div class="card"><h2>⚡ 信号预警卡 <small style="color:var(--muted)">'
            f'数值层每日重算 · 事件锚带失效条件 · 一次性水位触发即归档</small></h2>'
            f'<div class="focus" style="grid-template-columns:1fr">{rows}</div></div>')


def sec_earnings(cal, eflags):
    wd = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    flag_rows = "".join(
        f'<div class="fc drop">{tv.link(tk)}<div class="ctx">{esc(txt)}</div></div>'
        for tk, txt in eflags.items())
    cal_txt = (" · ".join(f"<b>{d:%m-%d}</b>({wd[d.weekday()]}) {tv.link(tk, bold=False, show_exchange=False)}" for d, tk in cal)
               if cal else "未来14日观察池无财报")
    return f"""
<div class="card" id="earn"><h2>📅 财报雷达 · 风险窗口与未来14日日历</h2>
<div class="focus">{flag_rows}</div>
<p style="color:var(--ink2);margin-top:8px">{cal_txt}</p></div>"""

def sec_tiles(m1):
    regime_hot = m1["regime"] == "MTUM"
    return f"""
<div class="tiles">
  <div class="tile"><div class="k">标普500 (SPX)</div><div class="v">{m1['spx']:,.2f}</div>
    <div class="s">MA50 偏离 {signed(m1['dev50'])}（>+5% 过热 / <0 走弱）</div></div>
  <div class="tile"><div class="k">14日 RSI 动能</div><div class="v">{m1['rsi']:.1f}</div>
    <div class="s">{'⚠️ 偏热/背离预警' if m1['rsi'] > C.RSI_HOT else '中性健康'}（阈值 >{C.RSI_HOT} 偏热）</div></div>
  <div class="tile"><div class="k">VIX 恐慌指数</div><div class="v">{m1['vix']:.2f}</div>
    <div class="s">{'🚨 去杠杆/避险升温' if m1['vix'] > C.VIX_ALERT else '情绪平稳'}（阈值 >{C.VIX_ALERT} 预警）</div></div>
  <div class="tile"><div class="k">因子轮动 MTUM/MAGS</div><div class="v">{m1['mtum_mags']:.4f}</div>
    <div class="s">{'🔥 资金偏向广义动量股' if regime_hot else '💻 资金偏向七巨头抱团'}
    （比值{'站上' if regime_hot else '跌破'}自身20日均线 {m1['mtum_mags_ma']:.4f}, 看趋势不看绝对值）</div></div>
</div>"""


def sec_sectors(df):
    vmax = df["超额Alpha"].abs().max()
    rows = "".join(
        f'<tr><td class="l">{tv.link(r["代码"])}</td><td class="l">{esc(r["板块名称"])}</td>'
        f'<td>{signed(r["前一日涨跌"])}</td><td>{dbar(r["超额Alpha"], vmax)} {signed(r["超额Alpha"])}</td>'
        f'<td>{r["量倍"]:.2f}x</td><td>{signed(r["5日超额"])}</td>'
        f'<td class="l">{diag_badge(r["诊断"])}</td></tr>'
        for _, r in df.iterrows())
    return f"""
<div class="card" id="sectors"><h2>板块 ETF · 前一日交易异动与微观动能</h2>
<table><tr><th class="l">代码</th><th class="l">板块</th><th>前一日涨跌</th>
<th>1日超额 Alpha</th><th>量倍</th><th>5日超额</th><th class="l">诊断</th></tr>{rows}</table></div>"""


def sec_themes(df):
    vmax = df["超额Alpha"].abs().max()
    rows = "".join(
        f'<tr><td class="l">{esc(r["主题"])}</td><td>{signed(r["均涨跌"])}</td>'
        f'<td>{dbar(r["超额Alpha"], vmax)} {signed(r["超额Alpha"])}</td>'
        f'<td>{r["平均量倍"]:.2f}x</td><td class="l">'
        f'{tv.linkify_text(esc(r["领头羊"]), [t for m in C.THEMES.values() for t in m])}</td>'
        f'<td class="l">{diag_badge(r["诊断"])}</td></tr>'
        for _, r in df.iterrows())
    return f"""
<div class="card"><h2>自定义主题股票池 · 前一日动能榜</h2>
<table><tr><th class="l">主题</th><th>均涨跌</th><th>1日超额 Alpha</th><th>平均量倍</th>
<th class="l">领头羊</th><th class="l">诊断</th></tr>{rows}</table></div>"""


def sec_watchlist(df):
    top5 = df.sort_values("得分", ascending=False).head(5)
    t5 = "".join(
        f'<tr><td class="l">{tv.link(r["代码"])}</td><td>{r["收盘价"]:.2f}</td>'
        f'<td>{signed(r["超额Alpha"])}</td><td>{r["量倍"]:.2f}x</td>'
        f'<td>{signed(r["CMF"], "+.2f", "")}</td><td>{r["MFI"]:.1f}</td><td><b>{r["得分"]:.2f}</b></td></tr>'
        for _, r in top5.iterrows())
    def detail_cell(r):
        d = esc(r["细节"])
        if r.get("财报"):
            d += f' <span class="badge b-critical">‼️ {esc(r["财报"])}</span>'
        return d
    rows = "".join(
        f'<tr class="{"hit" if r["标记"] != "⚪" else ""}">'
        f'<td class="l">{tv.link(r["代码"])}</td><td>{r["收盘价"]:.2f}</td>'
        f'<td>{r["EMA10"]:.2f}</td><td>{r["EMA21"]:.2f}</td><td>{r["RSI"]:.1f}</td>'
        f'<td class="l">{esc(r["标记"])} {esc(r["形态"])}</td>'
        f'<td class="l" style="white-space:normal;color:var(--ink2)">{detail_cell(r)}</td></tr>'
        for _, r in df.iterrows())
    return f"""
<div class="card" id="watch"><h2>观察池 · 日线动能与 CMF 资金强流入 TOP 5</h2>
<table><tr><th class="l">代码</th><th>收盘价</th><th>1日超额α</th><th>量倍</th>
<th>CMF</th><th>MFI</th><th>综合得分</th></tr>{t5}</table></div>
<div class="card"><h2>观察池 · 日线经典买点形态触发表（高亮 = 触发）</h2>
<table><tr><th class="l">代码</th><th>最新价</th><th>EMA10</th><th>EMA21</th><th>RSI</th>
<th class="l">形态诊断</th><th class="l">量化细节</th></tr>{rows}</table></div>"""


def sec_intraday(df):
    if df is None or df.empty:
        return '<div class="card"><h2>日内 VWAP 择时</h2><p style="color:var(--muted)">未拉取日内数据</p></div>'
    def v15(x):
        return "—" if np.isnan(x) else f"{x:.1f}x"
    def gp(x):
        return "—" if np.isnan(x) else f'{signed(x, "+.1f")}'
    rows = "".join(
        f'<tr><td class="l">{tv.link(r["代码"])}</td><td>{r["现价"]:.2f}</td>'
        f'<td>{r["VWAP"]:.2f}</td><td>{signed(r["偏离"])}</td>'
        f'<td>{gp(r["跳空"])}</td><td>{v15(r["量能15"])}</td>'
        f'<td class="l">{sig_badge(r["信号"])}</td>'
        f'<td class="l" style="white-space:normal;color:var(--ink2)">{esc(r["细节"])}</td></tr>'
        for _, r in df.iterrows())
    return f"""
<div class="card" id="intraday"><h2>观察池 · 今日日内量价择时执行信号 <small style="color:var(--muted)">session {esc(df['session'].iloc[0])}</small></h2>
<table><tr><th class="l">代码</th><th>现价</th><th>日内VWAP</th><th>偏离</th><th>跳空</th><th>15m量能</th>
<th class="l">择时信号</th><th class="l">战术细节</th></tr>{rows}</table></div>"""


def sec_focus(keep, drop, intra_df):
    sig = {} if intra_df is None or intra_df.empty else dict(zip(intra_df["代码"], intra_df["信号"]))
    cards = "".join(
        f'<div class="fc">{tv.link(tk)} {esc(pat)}'
        f'<div class="ctx">✅ 板块资金确认 · {esc(ctx)}</div>'
        f'<div class="ctx">日内: {sig_badge(sig[tk]) if tk in sig else "—"}</div></div>'
        for tk, pat, ctx in keep) + "".join(
        f'<div class="fc drop">{tv.link(tk)} {esc(pat)}'
        f'<div class="ctx">⛔ {"财报风险窗口" if "财报" in ctx else "板块资金背离"}, 仅观察不追 · {esc(ctx)}</div></div>'
        for tk, pat, ctx in drop)
    empty = '<p style="color:var(--muted)">今日无日线形态信号</p>' if not keep and not drop else ""
    return f'<div class="card" id="focus"><h2>板块共振 Cross-Check · 自动缩减聚焦清单</h2><div class="focus">{cards}</div>{empty}</div>'


def build(with_intraday=True, daily=None, refresh_sec=None) -> Path:
    """daily: 传入已拉好的日线可跳过重复下载(live 模式复用);
    refresh_sec: 写入 <meta refresh>, 浏览器自动刷新。"""
    if daily is None:
        print("拉取日线数据 ...")
        daily = fetch_daily(C.all_daily_tickers())
    tv.warm(C.all_daily_tickers())      # 预热 TradingView 符号表(缓存, 只首次联网)
    quiet = io.StringIO()
    with contextlib.redirect_stdout(quiet):
        m1 = m1_macro.run(daily)
        gao = m7_gao.run(daily)
        cam = m10_camslim.run(daily)
        alert_cards = m8_alerts.run(daily, gao)
        try:
            pre_df = m9_premarket.run(daily)
        except Exception:
            pre_df = None
        try:
            bogo = m13_bogo.run()
        except Exception as e:
            bogo = {"rows": [], "title": None, "error": str(e)}
        try:    # 季度数据, 每天抓一次即可; 站点结构变了会自己标"未验证"
            capex_ev = m12_capex.run(refresh=True)
        except Exception as e:
            capex_ev = {"error": f"抓取异常: {e}", "rows": [], "alerts": []}
        sec_df = m2_sectors.run(daily)
        theme_df = m3_themes.run(daily)
        wl_df = m4_watchlist.run(daily)
        cal = earnings.upcoming(C.WATCHLIST, days=14)
        eflags = earnings.flags(C.WATCHLIST)
    intra_df = None
    if with_intraday:
        print("拉取日内数据 ...")
        intra = fetch_intraday(C.WATCHLIST)
        with contextlib.redirect_stdout(quiet):
            intra_df = m5_intraday.run(intra, daily)
    keep, drop = compute_crosscheck(sec_df, theme_df, wl_df)

    from .data import col
    import datetime as dt
    date = col(daily, "Close", C.BENCHMARK).index[-1].strftime("%Y-%m-%d")
    stamp = dt.datetime.now().strftime("%H:%M:%S")
    meta_refresh = (f'<meta http-equiv="refresh" content="{refresh_sec}">'
                    if refresh_sec else "")
    # ── 自上而下: 宏观 → 板块 → 个股 → 最终落在「交易机会」──
    body = (
        nav()
        + tier("macro", "① 宏观", "大盘环境决定今天能下多大注")
        + sec_tiles(m1) + sec_camslim(cam) + sec_gao(gao) + sec_alerts(alert_cards)

        + tier("sector", "② 板块", "资金去哪了 —— 个股信号必须有板块背书")
        + sec_sectors(sec_df) + sec_themes(theme_df) + sec_capex(capex_ev)

        + tier("stock", "③ 个股", "信号、形态与时机")
        + sec_intraday(intra_df)
        + sec_premarket(pre_df) + sec_bogo(bogo)
        + sec_earnings(cal, eflags) + sec_watchlist(wl_df)

        + tier("ops", "④ 候选清单", "以上各层过滤后的剩余项 —— 是待研究名单, 不是买入建议")
        + sec_opportunities(keep, drop, intra_df, bogo, cam, gao))
    page = (f'<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'{meta_refresh}<title>波哥信号仪表盘 {date}</title><style>{CSS}</style>'
            f'<h1>📡 波哥信号 · 美股监控仪表盘 <small>日线数据日 {date} · 本地生成 {stamp}'
            f' · 超额基准 {C.BENCHMARK} · '
            f'<a href="manual.html" style="color:var(--pos)">📖 使用手册（看不懂点这里）</a>'
            f'</small></h1>'
            f'{body}<p class="footer">阈值配置见 us_monitor/config.py · 仅供研究, 不构成投资建议</p>')

    OUT_DIR.mkdir(exist_ok=True)
    out = OUT_DIR / f"dashboard_{date}.html"
    tmp = OUT_DIR / ".tmp_dashboard.html"          # 原子写: 避免浏览器读到半个文件
    tmp.write_text(page, encoding="utf-8")
    shutil.copy(tmp, out)
    tmp.replace(OUT_DIR / "latest.html")
    print(f"✅ 仪表盘已生成: {out} ({stamp})")
    return out


if __name__ == "__main__":
    build(with_intraday="--no-intraday" not in sys.argv)
