# -*- coding: utf-8 -*-
"""
模块16：波哥信号总汇总网页版 —— 把《波哥信号总汇总_0608起.xlsx》(3 sheet)发布成 summary.html。
2026-08-12 起汇总以网页为准，不再回写 Drive 本地文件（用户要求）。
本地: 读项目 xlsx → 落 .bogo_sum.json(供云端CI无xlsx时回退) → 出 docs/summary.html。
列: 精选 13 列(长文本叙事列不进网页,在 deck/bogo 明细里看)。带前端即时筛选框。
"""
import html as H
import json
from pathlib import Path

from .m15_bogo_cn import CSS

STORE = Path(__file__).resolve().parent / ".bogo_sum.json"
XLSX = Path("/Users/clair/Documents/Claude/Projects/波哥系统 a 股/信号总汇总/波哥信号总汇总_0608起.xlsx")
KEEP = ["信号日", "信号", "代码", "名称", "主题", "当日%", "Fit", "胜率%", "CA%", "Pnls%", "交易次数", "现价", "来源"]


def load() -> dict:
    if XLSX.exists():
        try:
            import openpyxl
            wb = openpyxl.load_workbook(XLSX, read_only=True)
            out = {"sheets": {}, "mtime": XLSX.stat().st_mtime}
            for ws in wb.worksheets:
                it = ws.iter_rows(values_only=True)
                hdr = [str(x) if x is not None else "" for x in next(it)]
                hdr = [h.replace("色(强/弱)", "色") for h in hdr]
                idx = [hdr.index(k) for k in KEEP if k in hdr]
                rows = []
                for r in it:
                    if not r or r[hdr.index("代码")] is None:
                        continue
                    rows.append([("" if r[i] is None else str(r[i])) for i in idx])
                out["sheets"][ws.title] = {"hdr": [hdr[i] for i in idx], "rows": rows}
            STORE.write_text(json.dumps(out, ensure_ascii=False))
            return out
        except Exception as exc:
            print(f"WARN: 汇总xlsx读取失败 {exc}")
    if STORE.exists():
        try:
            d = json.loads(STORE.read_text())
            d["_stale"] = True
            return d
        except json.JSONDecodeError:
            pass
    return {"sheets": {}}


def build_page() -> Path:
    from .m6_dashboard import OUT_DIR
    d = load()
    sheets = d.get("sheets", {})
    btns, panels = [], []
    for i, (name, s) in enumerate(sheets.items()):
        on = " on" if i == 0 else ""
        sid = f"s{i}"
        btns.append(f'<button class="tab{on}" data-t="{sid}">{H.escape(name)}（{len(s["rows"])}）</button>')
        hdr = s["hdr"]
        i_sig = hdr.index("信号") if "信号" in hdr else -1
        i_fit = hdr.index("Fit") if "Fit" in hdr else -1
        trs = []
        for r in s["rows"]:
            cls = ' class="s"' if (i_sig >= 0 and r[i_sig] == "strong") else ""
            tds = []
            for j, v in enumerate(r):
                if j == i_sig:
                    tds.append(f'<td class="l"><span class="tag {"st" if v=="strong" else "wk"}">{H.escape(v)}</span></td>')
                elif j == i_fit:
                    try:
                        g = float(v) >= 4
                    except ValueError:
                        g = False
                    tds.append(f'<td class="fitg">{H.escape(v)}</td>' if g else f'<td>{H.escape(v)}</td>')
                elif hdr[j] in ("代码",):
                    tds.append(f'<td class="l"><b>{H.escape(v)}</b></td>')
                elif hdr[j] in ("名称", "主题", "信号日", "来源"):
                    tds.append(f'<td class="l">{H.escape(v)}</td>')
                else:
                    tds.append(f'<td>{H.escape(v)}</td>')
            trs.append(f"<tr{cls}>" + "".join(tds) + "</tr>")
        head = "".join(f'<th{" class=l" if h in ("信号日","信号","代码","名称","主题","来源") else ""}>{H.escape(h)}</th>' for h in hdr)
        panels.append(f'<div class="panel{on}" id="p-{sid}">'
                      f'<table><tr>{head}</tr>{"".join(trs)}</table></div>')
    tabcss = """.tabs{position:sticky;top:0;background:var(--bg);padding:8px 0;display:flex;gap:6px;flex-wrap:wrap;align-items:center}
.tab{font:inherit;padding:5px 12px;border:1px solid var(--bd);border-radius:15px;background:var(--sf);color:var(--ink);cursor:pointer}
.tab.on{background:var(--ink);color:var(--bg);border-color:var(--ink)}
.panel{display:none}.panel.on{display:block}
#q{font:inherit;padding:5px 10px;border:1px solid var(--bd);border-radius:15px;background:var(--sf);color:var(--ink);width:150px}"""
    js = """<script>const bs=document.querySelectorAll('.tab'),ps=document.querySelectorAll('.panel');
bs.forEach(b=>b.onclick=()=>{bs.forEach(x=>x.classList.toggle('on',x===b));
ps.forEach(p=>p.classList.toggle('on',p.id==='p-'+b.dataset.t));});
document.getElementById('q').oninput=e=>{const q=e.target.value.trim().toLowerCase();
document.querySelectorAll('.panel.on tr').forEach((tr,i)=>{if(i===0)return;
tr.style.display=(!q||tr.textContent.toLowerCase().includes(q))?'':'none';});};</script>"""
    import datetime
    mt = d.get("mtime")
    upd = datetime.datetime.fromtimestamp(mt).strftime("%m-%d %H:%M") if mt else "?"
    page = (f'<meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>波哥信号总汇总</title><style>{CSS}{tabcss}</style>'
            f'<h1>波哥信号总汇总（0608 起全历史）</h1>'
            f'<div class="sub"><a href="bogo.html">← 每日信号页</a> · '
            f'<a href="pt2-signals.html">PivotTrend2 趋势追踪</a> · 数据更新 {upd}'
            f'{" · ⚠ 快照(本地xlsx不可达)" if d.get("_stale") else ""}</div>'
            f'<div class="tabs">{"".join(btns)}<input id="q" placeholder="筛选:代码/名称/主题/日期"></div>'
            + "".join(panels) + js
            + '<div class="sub" style="margin-top:16px">回测口径自波哥系统 · 信息整理非投资建议</div>')
    out = OUT_DIR / "summary.html"
    out.write_text(page, encoding="utf-8")
    n = sum(len(s["rows"]) for s in sheets.values())
    print(f"✅ 汇总网页: {len(sheets)} sheet 共 {n} 行")
    return out


if __name__ == "__main__":
    build_page()
