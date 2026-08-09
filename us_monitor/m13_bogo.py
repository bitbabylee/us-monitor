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
from collections import defaultdict
from pathlib import Path

from . import config as C

STORE = Path(__file__).resolve().parent / ".bogo_signals.json"
# 列名 → 该列左边界 x 坐标（PDF 版式固定, 用坐标切列比表格线可靠）
COLS = [("代码", 78), ("中文名", 130), ("信号日", 219), ("主题", 282),
        ("CA%", 438), ("Pnls%", 497), ("胜率", 564), ("Fit", 623),
        ("价系统", 678), ("当日%", 753)]


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

    lines = defaultdict(list)
    for w in words:
        lines[round(w["top"] / 3)].append(w)

    rows, tag = [], None
    for k in sorted(lines):
        line = sorted(lines[k], key=lambda w: w["x0"])
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
