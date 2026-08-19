# -*- coding: utf-8 -*-
"""
模块13：波哥七维信号聚合 —— 把波哥系统当日 US 盘后 PDF 的第一页汇总表读进来。

数据源: 归档目录里的 `MMDD us 1630 bo sig.pdf`（波哥 pipeline 每日产出）。
只解析第 1 页「七维信号汇总」表: 信号强弱 / 代码 / 主题 / CA% / Pnls% / 胜率 / Fit / 当日%。

价值: 波哥系统是【回测+基本面七维】选出来的候选, 我们这套是【技术面+资金面】过滤器。
两者交集 = 两套独立方法共同看好的标的, 信号质量最高。本模块自动标出交集。

解析结果落 .bogo_signals.json, 供云端站点在没有 PDF 时也能显示最近一次。
"""
import json
import re
import sys
from pathlib import Path

from . import config as C

STORE = Path(__file__).resolve().parent / ".bogo_signals.json"
# 列名 → 该列左边界 x 坐标（PDF 版式固定, 用坐标切列比表格线可靠）
COLS = [("代码", 78), ("中文名", 130), ("信号日", 219), ("主题", 282),
        ("CA%", 438), ("Pnls%", 497), ("胜率", 564), ("Fit", 623),
        ("价系统", 678), ("当日%", 753)]


def _cluster_words_by_top(words, tolerance: float = 2.5):
    """Group PDF words into visual rows without rounding-boundary loss."""
    lines = []
    for word in sorted(words, key=lambda w: (w["top"], w["x0"])):
        if not lines or word["top"] - lines[-1][0]["top"] > tolerance:
            lines.append([word])
        else:
            lines[-1].append(word)
    return lines


def find_pdf() -> Path | None:
    """找最新的 `MMDD us 1630 bo sig.pdf`"""
    for d in C.BOGO_DIRS:
        p = Path(d).expanduser()
        if not p.exists():
            continue
        pdfs = sorted(p.glob("* us 1630 bo sig.pdf"),
                      key=lambda f: f.stat().st_mtime, reverse=True)
        if pdfs:
            return pdfs[0]
    return None


def parse(pdf: Path) -> dict:
    import pdfplumber
    with pdfplumber.open(pdf) as doc:
        page = doc.pages[0]
        title = (page.extract_text() or "").split("\n")[0]
        words = page.extract_words()

    rows, tag = [], None
    for words_in_line in _cluster_words_by_top(words):
        line = sorted(words_in_line, key=lambda w: w["x0"])
        first = line[0]["text"]
        if first in ("strong", "weak"):
            tag = first
        elif "以下为弱信号" in "".join(w["text"] for w in line):
            tag = "weak"
            continue
        else:
            continue
        cell = {}
        for name, x in COLS:
            nxt = next((xx for n2, xx in COLS if xx > x), 9999)
            vals = [w["text"] for w in line if x - 6 <= w["x0"] < nxt - 6]
            cell[name] = " ".join(vals).strip()
        if not re.fullmatch(r"[A-Z0-9.!]{1,8}", cell.get("代码", "")):
            continue
        cell["信号"] = tag
        rows.append(cell)

    m = re.search(r"US盘后\s*([\d-]+)", title)
    return {"title": title, "date": m.group(1) if m else None,
            "source": pdf.name, "rows": rows}


def export_pages(pdf: Path, out_dir: Path, scale: float = None, only=None) -> dict:
    """把 PDF 第 2 页起的每只票单页图导成 PNG。返回 {代码: 相对路径}。
    页首格式固定为 `CODE 中文名 · 主题`, 用它认代码。"""
    import fitz
    scale = scale or C.BOGO_IMG_SCALE
    out_dir.mkdir(parents=True, exist_ok=True)
    mapping, doc = {}, fitz.open(pdf)
    for i in range(1, doc.page_count):
        head = (doc[i].get_text() or "").split("\n")[0].strip()
        m = re.match(r"([A-Z0-9.!]{1,8})\s", head)
        if not m:
            continue                       # 末页是 TradingView 链接页, 跳过
        code = m.group(1)
        if only is not None and code not in only:
            continue
        png = out_dir / f"{code}.png"
        if not png.exists():               # 已导出的不重复渲染
            doc[i].get_pixmap(matrix=fitz.Matrix(scale, scale)).save(png)
        mapping[code] = f"{out_dir.name}/{png.name}"
    doc.close()
    return mapping


def _num(s, default=None):
    try:
        return float(str(s).replace("+", "").replace("%", "").strip())
    except (ValueError, AttributeError):
        return default


def load() -> dict:
    """优先解析本地最新 PDF; 没有(如云端)则读上次落盘的快照"""
    pdf = find_pdf()
    if pdf:
        try:
            d = parse(pdf)
            if d["rows"]:
                try:
                    from .m6_dashboard import OUT_DIR
                    # 只导当日强信号的原图（全导 34 张 6MB, 且弱信号/旧日期用处不大）
                    days3 = sorted({r["信号日"] for r in d["rows"]}, reverse=True)[:3]
                    want = {r["代码"] for r in d["rows"]
                            if r["信号"] == "strong" and r["信号日"] in days3}
                    d["images"] = export_pages(pdf, OUT_DIR / "bogo", only=want)
                except Exception as exc:
                    print(f"WARN: 导出波哥单页图失败 {exc}", file=sys.stderr)
                    d["images"] = {}
                STORE.write_text(json.dumps(d, ensure_ascii=False, indent=1))
                return d
        except Exception as exc:
            print(f"WARN: 解析波哥 PDF 失败 {exc}", file=sys.stderr)
    if STORE.exists():
        try:
            d = json.loads(STORE.read_text())
            d["stale"] = True
            return d
        except json.JSONDecodeError:
            pass
    return {"rows": [], "title": None, "date": None, "source": None}


def cross(d: dict) -> dict:
    """标出与本系统观察池/主题池的交集 —— 两套独立方法共同看好"""
    mine = set(C.WATCHLIST) | {t for m in C.THEMES.values() for t in m}
    for r in d.get("rows", []):
        r["交集"] = r["代码"] in mine
    hit = [r for r in d.get("rows", []) if r["交集"]]
    d["overlap"] = hit
    return d


def run() -> dict:
    d = cross(load())
    rows = d.get("rows", [])
    print("=" * 100)
    print(f"【波哥七维信号聚合】{d.get('title') or '（无数据）'}")
    if d.get("stale"):
        print("⚠️ 未找到当日 PDF, 显示上次快照")
    if not rows:
        print("👉 无数据（本地未找到 `MMDD us 1630 bo sig.pdf`）")
        print("=" * 100)
        return d
    strong = [r for r in rows if r["信号"] == "strong"]
    print(f"共 {len(rows)} 只（强 {len(strong)} / 弱 {len(rows)-len(strong)}）· "
          f"与本系统池交集 {len(d['overlap'])} 只 · 来源 {d.get('source')}")
    print(f"{'信号':<7}{'代码':>7} {'当日%':>7} {'Fit':>6} {'胜率':>6} {'CA%':>6} "
          f"{'Pnls%':>7}  主题")
    for r in rows:
        mark = "🔗" if r["交集"] else "  "
        print(f"{r['信号']:<7}{r['代码']:>7} {r['当日%']:>7} {r['Fit']:>6} {r['胜率']:>6} "
              f"{r['CA%']:>6} {r['Pnls%']:>7}  {mark}{r['主题'][:22]}")
    if d["overlap"]:
        print("-" * 100)
        print("🔗 与本系统池交集（两套独立方法共同覆盖, 优先看）:")
        for r in d["overlap"]:
            print(f"   {r['代码']:>6} [{r['信号']}] Fit {r['Fit']} · 当日 {r['当日%']}% · {r['主题'][:26]}")
    print("=" * 100)
    return d


if __name__ == "__main__":
    run()


def _stamp() -> str:
    """页面生成时间: 纽约=新加坡双时区(裸 ET 时分会被误读成旧数据)"""
    import datetime as _dt
    from zoneinfo import ZoneInfo as _Z
    ny = _dt.datetime.now(_Z("America/New_York"))
    sg = ny.astimezone(_Z("Asia/Singapore"))
    return f"{ny:%m-%d %H:%M}纽约={sg:%m-%d %H:%M}新加坡"


def build_page() -> Path:
    """公开页: 完整七维表(强+弱) + 仅近3日强信号带原图明细。无私人引用。"""
    import html as H
    from . import tv
    from .m6_dashboard import OUT_DIR
    d = load()
    rows = d.get("rows", [])
    imgs = d.get("images", {})
    tv.warm([r["代码"] for r in rows])
    days3 = sorted({r["信号日"] for r in rows}, reverse=True)[:3]
    latest = d.get("date")
    strong3 = [r for r in rows if r["信号"] == "strong" and r["信号日"] in days3]

    css = """
:root{color-scheme:light dark;--ink:#111;--ink2:#555;--mut:#888;--bd:#8883;
--good:#0ca30c;--pos:#2a78d6;--bg:#fcfcfb;--sf:#fff}
@media(prefers-color-scheme:dark){:root{--ink:#e8e6dd;--ink2:#b5b3a8;--mut:#888;
--bg:#111110;--sf:#1a1a19}}
body{margin:0;padding:14px 10px;background:var(--bg);color:var(--ink);
 font:12.5px/1.45 system-ui,-apple-system,sans-serif;max-width:1100px;margin:auto}
h1{font-size:15px;margin:6px 0 2px} .sub{color:var(--mut);font-size:11px;margin-bottom:8px}
table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}
th{color:var(--mut);font-weight:500;font-size:11px;text-align:right;padding:2px 6px;
 border-bottom:1px solid var(--bd);white-space:nowrap}
td{padding:2px 6px;text-align:right;border-bottom:1px solid var(--bd);
 white-space:nowrap;font-size:12px}
th.l,td.l{text-align:left}
a{color:inherit;text-decoration:none;border-bottom:1px dotted var(--mut)}
.tag{display:inline-block;padding:0 6px;border-radius:999px;font-size:11px;border:1px solid}
.st{color:var(--good);border-color:var(--good)} .wk{color:var(--mut);border-color:var(--bd)}
.new{color:var(--good);border-color:var(--good)} .old{color:var(--mut);border:none}
.blk{margin:16px 0;padding-bottom:12px;border-bottom:1px dashed var(--bd)}
.blk pre{margin:0 0 6px;font:12px/1.5 ui-monospace,Menlo,monospace;white-space:pre-wrap}
img{max-width:100%;border:1px solid var(--bd);border-radius:6px}
.ex{color:var(--mut);font-size:10px}
"""

    def sym(tk):
        s_ = tv.symbol(tk)
        ex, _, code = s_.partition(":")
        url = "https://www.tradingview.com/chart/?symbol=" + s_.replace(":", "%3A")
        return f'<a href="{url}" target="_blank"><span class="ex">{ex}:</span><b>{code}</b></a>'

    def day_cell(r):
        d0 = r["信号日"]
        if d0 == latest:
            return f'<span class="tag new">{H.escape(d0)} 新</span>'
        return f'<span class="old">{H.escape(d0)}</span>'

    tr = "".join(
        f'<tr><td class="l"><span class="tag {"st" if r["信号"]=="strong" else "wk"}">'
        f'{r["信号"]}</span></td>'
        f'<td class="l">{sym(r["代码"])}'
        + (' 🖼' if r["代码"] in imgs and r in strong3 else '') + '</td>'
        f'<td class="l">{H.escape(r["中文名"])}</td>'
        f'<td class="l">{day_cell(r)}</td>'
        f'<td>{H.escape(r["当日%"])}</td><td>{H.escape(r["Fit"])}</td>'
        f'<td>{H.escape(r["胜率"])}</td><td>{H.escape(r["CA%"])}</td>'
        f'<td>{H.escape(r["Pnls%"])}</td>'
        f'<td class="l" style="white-space:normal">{H.escape(r["主题"])}</td></tr>'
        for r in rows)

    blocks = []
    for r in strong3:
        s_ = tv.symbol(r["代码"])
        url = "https://www.tradingview.com/chart/?symbol=" + s_.replace(":", "%3A")
        blocks.append(
            f'<div class="blk" id="d-{r["代码"]}"><pre><b>{H.escape(s_)}</b> '
            f'{H.escape(r["中文名"])} · {H.escape(r["主题"])}\n'
            f'信号日 {H.escape(r["信号日"])} · Fit {H.escape(r["Fit"])} · 胜率 '
            f'{H.escape(r["胜率"])}% · CA {H.escape(r["CA%"])}% · Pnls '
            f'{H.escape(r["Pnls%"])}% · 当日 {H.escape(r["当日%"])}% · '
            f'<a href="{url}" target="_blank">TV↗</a></pre>'
            + (f'<img loading="lazy" src="{H.escape(imgs[r["代码"]])}">'
               if r["代码"] in imgs else "") + "</div>")

    page = (f'<meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>波哥七维信号</title><style>{css}</style>'
            f'<h1>波哥系统七维信号汇总</h1>'
            f'<div class="sub">{H.escape(d.get("title") or "")[:70]} · '
            f'生成 {_stamp()} · '
            f'共 {len(rows)} 只（强 {sum(1 for r in rows if r["信号"]=="strong")}）· '
            f'下方明细图仅近3日强信号（{" / ".join(days3)}）</div>'
            f'<table><tr><th class="l">信号</th><th class="l">代码</th>'
            f'<th class="l">名称</th><th class="l">信号日</th><th>当日%</th><th>Fit</th>'
            f'<th>胜率</th><th>CA%</th><th>Pnls%</th><th class="l">主题</th></tr>'
            f'{tr}</table>'
            f'<h1 style="margin-top:18px">近3日强信号 · 明细图（{len(blocks)}）</h1>'
            + "".join(blocks)
            + '<div class="sub">CA/Pnls/胜率/Fit 为波哥系统自身回测口径 · '
              '信息整理非投资建议</div>')
    out = OUT_DIR / "bogo.html"
    out.write_text(page, encoding="utf-8")
    print(f"✅ 波哥公开页: 表 {len(rows)} 行 + 强信号明细 {len(blocks)} 块")
    return out
