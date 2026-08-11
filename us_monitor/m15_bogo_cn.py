# -*- coding: utf-8 -*-
"""
模块15：波哥 A股三批合并公开页 —— ch1050 / ch1520 / aicore(1600) 一页三区。

复用 m13_bogo 的 parse/export_pages（deck 第一页版式与 us 完全一致）。
数据源: 归档目录里的 `MMDD ch 1050|ch 1520|ai 1600 bo sig.pdf`。
解析结果落 .bogo_cn_signals.json（云端无 PDF 时回退显示上次快照）。
输出: OUT_DIR/bogo_cn.html + OUT_DIR/bogo_cn/{1050,1520,1600}/<代码>.png（仅近3日强信号原图）。
与 bogo.html(美股页) 同风格，页顶互跳链接。无任何私人引用。
"""
import html as H
import json
from pathlib import Path

from . import m13_bogo as m13

STORE = Path(__file__).resolve().parent / ".bogo_cn_signals.json"
BATCHES = [
    ("1050", "A股早盘 · 10:50批", "* ch 1050 bo sig.pdf"),
    ("1520", "A股午后 · 15:20批", "* ch 1520 bo sig.pdf"),
    ("1600", "AI核心 · 16:00批（美股+A股）", "* ai 1600 bo sig.pdf"),
]

CSS = """
:root{color-scheme:light dark;--ink:#111;--ink2:#555;--mut:#888;--bd:#8883;
--good:#0ca30c;--bg:#fcfcfb;--sf:#fff}
@media(prefers-color-scheme:dark){:root{--ink:#e8e6dd;--ink2:#b5b3a8;--mut:#888;
--bg:#111110;--sf:#1a1a19}}
body{margin:0;padding:14px 10px;background:var(--bg);color:var(--ink);
font:13px/1.5 -apple-system,"PingFang SC",sans-serif;max-width:900px;margin:auto}
h1{font-size:16px;margin:6px 0 2px}
.sec{margin-top:26px;border-top:3px solid var(--bd);padding-top:10px}
.sub{color:var(--ink2);font-size:12px;margin:2px 0 8px}
table{border-collapse:collapse;width:100%;background:var(--sf);font-size:12px}
th,td{border:1px solid var(--bd);padding:3px 6px;text-align:right;white-space:nowrap}
th.l,td.l{text-align:left}
tr.s td{font-weight:600}
.tag{display:inline-block;padding:0 6px;border-radius:999px;font-size:11px;border:1px solid}
.st{color:var(--good);border-color:var(--good)}
.wk{color:var(--mut);border-color:var(--bd)}
.new{color:var(--good);border-color:var(--good);font-weight:700}
.old{color:var(--mut)}
tr.hot td{background:#0ca30c14}
.fitg{color:var(--good);font-weight:700}
.blk{margin:12px 0;background:var(--sf);border:1px solid var(--bd);border-radius:6px;padding:8px}
.blk pre{margin:0 0 6px;white-space:pre-wrap;font-size:12px}
.blk img{max-width:100%;border-radius:4px}
a{color:inherit}
"""


def _find_pdf(pattern):
    from . import config as C
    for d in C.BOGO_DIRS:
        p = Path(d).expanduser()
        if not p.exists():
            continue
        pdfs = sorted(p.glob(pattern), key=lambda f: f.stat().st_mtime, reverse=True)
        if pdfs:
            return pdfs[0]
    return None


def load() -> dict:
    """逐批: 最新PDF → parse → 近3日强信号导原图。无PDF(云端)回退快照。"""
    from .m6_dashboard import OUT_DIR
    out = {}
    fresh = False
    for key, label, pat in BATCHES:
        pdf = _find_pdf(pat)
        if pdf:
            try:
                d = m13.parse(pdf)
                days3 = sorted({r["信号日"] for r in d["rows"]}, reverse=True)[:3]
                want = {r["代码"] for r in d["rows"]
                        if r["信号"] == "strong" and r["信号日"] in days3}
                try:
                    d["images"] = m13.export_pages(pdf, OUT_DIR / "bogo_cn" / key, only=want)
                except Exception as exc:
                    print(f"WARN: {key} 导图失败 {exc}")
                    d["images"] = {}
                d["source"] = pdf.name
                out[key] = d
                fresh = True
                continue
            except Exception as exc:
                print(f"WARN: {key} 解析失败 {exc}")
        out[key] = None
    if fresh:
        STORE.write_text(json.dumps(out, ensure_ascii=False, indent=1))
        return out
    if STORE.exists():
        try:
            d = json.loads(STORE.read_text())
            d["_stale"] = True
            return d
        except json.JSONDecodeError:
            pass
    return out


def _tvurl(code):
    try:
        from . import tv
        s = tv.symbol(code)
        return s, "https://www.tradingview.com/chart/?symbol=" + s.replace(":", "%3A")
    except Exception:
        return code, None


def _section(key, label, d, img_prefix="bogo_cn/") -> str:
    if not d or not d.get("rows"):
        return (f'<div class="sec"><h1>{H.escape(label)}</h1>'
                f'<div class="sub">暂无数据</div></div>')
    rows = d["rows"]
    imgs = d.get("images", {})
    days3 = sorted({r["信号日"] for r in rows}, reverse=True)[:3]
    newest = days3[0] if days3 else ""
    strong3 = [r for r in rows if r["信号"] == "strong" and r["信号日"] in days3]
    def _day(r):
        d0 = r["信号日"]
        if d0 == newest:
            return f'<span class="tag new">{H.escape(d0)} 新</span>'
        return f'<span class="old">{H.escape(d0)}</span>'
    def _fit(r):
        try:
            g = float(r["Fit"]) >= 4
        except (TypeError, ValueError):
            g = False
        return f'<td class="fitg">{H.escape(r["Fit"])}</td>' if g else f'<td>{H.escape(r["Fit"])}</td>'
    def _cls(r):
        c = ("s" if r["信号"] == "strong" else "") + (" hot" if r["信号日"] == newest else "")
        return f' class="{c.strip()}"' if c.strip() else ""
    tr = "".join(
        f'<tr{_cls(r)}>'
        f'<td class="l"><span class="tag {"st" if r["信号"]=="strong" else "wk"}">{H.escape(r["信号"])}</span></td>'
        f'<td class="l"><b>{H.escape(r["代码"])}</b></td>'
        f'<td class="l">{H.escape(r["中文名"])}</td>'
        f'<td class="l">{_day(r)}</td>'
        f'<td>{H.escape(r["当日%"])}</td>{_fit(r)}'
        f'<td>{H.escape(r["胜率"])}</td><td>{H.escape(r["CA%"])}</td>'
        f'<td>{H.escape(r["Pnls%"])}</td>'
        f'<td class="l" style="white-space:normal">{H.escape(r["主题"])}</td></tr>'
        for r in rows)
    blocks = []
    for r in strong3:
        s_, url = _tvurl(r["代码"])
        link = f' · <a href="{url}" target="_blank">TV↗</a>' if url else ""
        blocks.append(
            f'<div class="blk"><pre><b>{H.escape(s_)}</b> {H.escape(r["中文名"])} · '
            f'{H.escape(r["主题"])}\n信号日 {H.escape(r["信号日"])} · Fit {H.escape(r["Fit"])} · '
            f'胜率 {H.escape(r["胜率"])}% · CA {H.escape(r["CA%"])}% · Pnls {H.escape(r["Pnls%"])}% · '
            f'当日 {H.escape(r["当日%"])}%{link}</pre>'
            + (f'<img loading="lazy" src="{img_prefix}{H.escape(imgs[r["代码"]])}">'
               if r["代码"] in imgs else "") + "</div>")
    return (f'<div class="sec"><h1>{H.escape(label)}</h1>'
            f'<div class="sub">{H.escape((d.get("title") or "")[:70])} · 来源 '
            f'{H.escape(d.get("source") or "")} · 共 {len(rows)} 只'
            f'（强 {sum(1 for r in rows if r["信号"]=="strong")}）</div>'
            f'<table><tr><th class="l">信号</th><th class="l">代码</th>'
            f'<th class="l">名称</th><th class="l">信号日</th><th>当日%</th><th>Fit</th>'
            f'<th>胜率</th><th>CA%</th><th>Pnls%</th><th class="l">主题</th></tr>{tr}</table>'
            + (f'<h1 style="margin-top:14px;font-size:14px">近3日强信号 · 明细图（{len(blocks)}）</h1>'
               + "".join(blocks) if blocks else "")
            + "</div>")


def build_page() -> Path:
    """主页面 bogo.html = 四批合一(tabs): 美股16:30默认 + A股三批。bogo_cn.html 留跳转壳。"""
    from .m6_dashboard import OUT_DIR
    d_us = m13.load()
    d_cn = load()
    tabs_def = [("us", "美股 16:30", d_us, "")] + [
        (k, lb.split(" · ")[0] + " " + lb.split(" · ")[1].split("批")[0], d_cn.get(k), "bogo_cn/")
        for k, lb, _ in BATCHES]
    btns, panels = [], []
    for i, (k, short, d, pref) in enumerate(tabs_def):
        on = " on" if i == 0 else ""
        btns.append(f'<button class="tab{on}" data-t="{k}">{H.escape(short)}</button>')
        label = {"us": "美股盘后 · 16:30批(NY)"}.get(k) or dict((b[0], b[1]) for b in BATCHES)[k]
        panels.append(f'<div class="panel{on}" id="p-{k}">{_section(k, label, d, pref)}</div>')
    tabcss = """.tabs{position:sticky;top:0;background:var(--bg);padding:8px 0;display:flex;gap:6px;flex-wrap:wrap}
.tab{font:inherit;padding:5px 12px;border:1px solid var(--bd);border-radius:15px;background:var(--sf);color:var(--ink);cursor:pointer}
.tab.on{background:var(--ink);color:var(--bg);border-color:var(--ink)}
.panel{display:none}.panel.on{display:block}.sec{border-top:none;margin-top:8px}"""
    js = """<script>const bs=document.querySelectorAll('.tab'),ps=document.querySelectorAll('.panel');
function go(t){bs.forEach(b=>b.classList.toggle('on',b.dataset.t===t));
ps.forEach(p=>p.classList.toggle('on',p.id==='p-'+t));}
bs.forEach(b=>b.onclick=()=>{go(b.dataset.t);history.replaceState(null,'','#'+b.dataset.t)});
if(location.hash)go(location.hash.slice(1));</script>"""
    page = (f'<meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>波哥七维信号</title><style>{CSS}{tabcss}</style>'
            f'<h1>波哥系统七维信号汇总</h1>'
            f'<div class="tabs">{"".join(btns)}</div>'
            + "".join(panels) + js
            + '<div class="sub" style="margin-top:16px">CA/Pnls/胜率/Fit 为波哥系统自身'
              '回测口径 · 信息整理非投资建议</div>')
    out = OUT_DIR / "bogo.html"
    out.write_text(page, encoding="utf-8")
    (OUT_DIR / "bogo_cn.html").write_text(
        '<meta charset="utf-8"><meta http-equiv="refresh" content="0;url=bogo.html#1050">',
        encoding="utf-8")
    n_us = len(d_us.get("rows", []))
    n_cn = sum(len((d_cn.get(k) or {}).get("rows", [])) for k, _, _ in BATCHES)
    print(f"✅ 波哥主页(tabs): 美股 {n_us} 行 + A股三批 {n_cn} 行")
    return out


if __name__ == "__main__":
    build_page()
