# -*- coding: utf-8 -*-
"""波哥系统全部 Ticker 主表：解析 Markdown、固化快照并渲染公开页签。"""

from __future__ import annotations

import html as H
import json
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


LOCAL_MASTER = Path("/Users/clair/Documents/Claude/波哥系统_全部Ticker主表.md")
SNAPSHOT = Path(__file__).resolve().parent / ".ticker_master.json"
SG = ZoneInfo("Asia/Singapore")

SECTION_RE = re.compile(r"^##\s+(\d+)\.\s+(.+?)\s*$")
ROW_RE = re.compile(r"^\|\s*`([A-Z0-9]+:[A-Z0-9.!_-]+)`\s*\|\s*(.*?)\s*\|\s*$")


def parse_markdown(text: str, updated: str | None = None) -> dict:
    """从主表的分类表格提取代码和标注；跳过“待核实”区。"""
    categories: list[dict] = []
    current: dict | None = None
    for line in text.splitlines():
        section = SECTION_RE.match(line)
        if section:
            number = int(section.group(1))
            current = None
            if number < 15:
                current = {"number": number, "title": section.group(2), "items": []}
                categories.append(current)
            continue
        if current is None:
            continue
        row = ROW_RE.match(line)
        if row:
            current["items"].append({"ticker": row.group(1), "note": row.group(2).strip()})

    categories = [category for category in categories if category["items"]]
    for category in categories:
        seen = set()
        category["items"] = [
            item for item in category["items"]
            if not (item["ticker"] in seen or seen.add(item["ticker"]))
        ]

    all_tickers = []
    seen_all = set()
    for category in categories:
        for item in category["items"]:
            ticker = item["ticker"]
            if ticker not in seen_all:
                seen_all.add(ticker)
                all_tickers.append(ticker)

    return {
        "updated": updated or datetime.now(SG).strftime("%Y-%m-%d %H:%M SGT"),
        "source": LOCAL_MASTER.name,
        "categories": categories,
        "all_tickers": all_tickers,
    }


def load_catalog() -> dict:
    """本机优先读主表并刷新快照；GitHub Actions 使用仓库内快照。"""
    snapshot = None
    if SNAPSHOT.exists():
        try:
            candidate = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
            if candidate.get("categories") and candidate.get("all_tickers"):
                snapshot = candidate
        except (json.JSONDecodeError, OSError):
            snapshot = None

    if LOCAL_MASTER.exists():
        modified = datetime.fromtimestamp(LOCAL_MASTER.stat().st_mtime, SG).strftime("%Y-%m-%d %H:%M SGT")
        catalog = parse_markdown(LOCAL_MASTER.read_text(encoding="utf-8"), updated=modified)
        if catalog["categories"] and catalog["all_tickers"]:
            serialized = json.dumps(catalog, ensure_ascii=False, indent=2) + "\n"
            if not SNAPSHOT.exists() or SNAPSHOT.read_text(encoding="utf-8") != serialized:
                SNAPSHOT.write_text(serialized, encoding="utf-8")
            return catalog
        if snapshot:
            print(f"警告：{LOCAL_MASTER} 为空或无法解析，保留上次有效 Ticker 快照。")
            return snapshot
        raise ValueError(f"Ticker 主表为空或无法解析：{LOCAL_MASTER}")
    if snapshot:
        return snapshot
    raise FileNotFoundError("Ticker 主表与有效快照均不存在，已停止生成以避免发布空页面。")


CSS = """
.ticker-hero{display:flex;gap:10px;align-items:flex-start;justify-content:space-between;flex-wrap:wrap}
.ticker-actions{display:flex;gap:7px;flex-wrap:wrap;margin:10px 0}
.copy-btn{font:inherit;padding:7px 12px;border:1px solid var(--ink);border-radius:8px;background:var(--ink);color:var(--bg);cursor:pointer}
.copy-btn.subtle{background:var(--sf);color:var(--ink);border-color:var(--bd)}
.ticker-search{width:100%;box-sizing:border-box;font:inherit;padding:9px 10px;border:1px solid var(--bd);border-radius:8px;background:var(--sf);color:var(--ink);margin:2px 0 10px}
.ticker-group{background:var(--sf);border:1px solid var(--bd);border-radius:9px;margin:8px 0;overflow:hidden}
.ticker-group summary{display:flex;align-items:center;gap:8px;cursor:pointer;padding:10px 11px;font-weight:650;list-style:none}
.ticker-group summary::-webkit-details-marker{display:none}
.ticker-group summary:before{content:'▸';color:var(--mut)}
.ticker-group[open] summary:before{content:'▾'}
.ticker-group .count{color:var(--mut);font-size:11px;font-weight:400;margin-right:auto}
.ticker-group-body{padding:0 10px 10px}
.ticker-row{display:grid;grid-template-columns:minmax(115px,170px) minmax(0,1fr);gap:10px;padding:6px 2px;border-top:1px solid var(--bd)}
.ticker-row code{font:600 12px ui-monospace,SFMono-Regular,Menlo,monospace;overflow-wrap:anywhere}
.ticker-note{color:var(--ink2);min-width:0}
.ticker-copybox{width:100%;min-height:112px;box-sizing:border-box;margin-top:8px;padding:8px;border:1px solid var(--bd);border-radius:7px;background:var(--bg);color:var(--ink);font:12px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace;resize:vertical;white-space:pre;overflow:auto}
.ticker-empty{display:none;color:var(--mut);padding:14px 2px}
@media(max-width:560px){.ticker-row{grid-template-columns:1fr;gap:2px}.copy-btn{flex:1 1 auto}.ticker-group summary{align-items:flex-start;flex-wrap:wrap}}
"""


def render_panel(catalog: dict | None = None) -> str:
    catalog = catalog or load_catalog()
    categories = catalog.get("categories", [])
    all_tickers = catalog.get("all_tickers", [])
    cards = []
    for category in categories:
        items = category["items"]
        codes = "\n".join(item["ticker"] for item in items)
        rows = "".join(
            f'<div class="ticker-row" data-search="{H.escape((item["ticker"] + " " + item["note"]).lower())}">'
            f'<code>{H.escape(item["ticker"])}</code><span class="ticker-note">{H.escape(item["note"])}</span></div>'
            for item in items
        )
        cards.append(
            f'<details class="ticker-group"><summary><span>{category["number"]}. {H.escape(category["title"])}</span>'
            f'<span class="count">{len(items)} 只</span>'
            f'<button type="button" class="copy-btn subtle" data-copy-target="ticker-copy-{category["number"]}">复制本组</button>'
            f'</summary><div class="ticker-group-body">{rows}'
            f'<textarea id="ticker-copy-{category["number"]}" class="ticker-copybox" readonly spellcheck="false" '
            f'aria-label="{H.escape(category["title"])}代码列表">{H.escape(codes)}</textarea></div></details>'
        )
    all_codes = "\n".join(all_tickers)
    return (
        '<div class="panel ticker-panel" id="p-tickers"><div class="sec">'
        '<div class="ticker-hero"><div><h1>波哥系统 · 全部 Ticker 主表</h1>'
        f'<div class="sub">{len(all_tickers)} 个不重复代码 · {len(categories)} 个分类 · '
        f'主表同步 {H.escape(catalog.get("updated", "—"))}</div></div></div>'
        '<div class="sub">用于趋势追踪与波哥系统输入整理；代码和标注来自主表，不代表当期信号或投资建议。</div>'
        '<div class="ticker-actions">'
        '<button type="button" class="copy-btn" data-copy-target="ticker-copy-all">复制全部（每行一个）</button>'
        '<button type="button" class="copy-btn subtle" id="ticker-expand-all">展开全部</button>'
        '<button type="button" class="copy-btn subtle" id="ticker-collapse-all">收起全部</button></div>'
        '<input id="ticker-search" class="ticker-search" type="search" placeholder="搜索代码、公司或主题，例如 CRDO、银行、有色" autocomplete="off">'
        f'<textarea id="ticker-copy-all" class="ticker-copybox" readonly spellcheck="false" aria-label="全部 Ticker">{H.escape(all_codes)}</textarea>'
        '<div id="ticker-empty" class="ticker-empty">没有匹配的代码或标注。</div>'
        + "".join(cards) + '</div></div>'
    )


JS = r"""
function tickerCopyText(text,button){
  const done=()=>{const old=button.textContent;button.textContent='已复制 ✓';setTimeout(()=>button.textContent=old,1400)};
  if(navigator.clipboard&&window.isSecureContext){navigator.clipboard.writeText(text).then(done);return;}
  const area=document.createElement('textarea');area.value=text;area.style.position='fixed';area.style.opacity='0';
  document.body.appendChild(area);area.select();document.execCommand('copy');area.remove();done();
}
document.querySelectorAll('[data-copy-target]').forEach(button=>button.addEventListener('click',event=>{
  event.preventDefault();event.stopPropagation();const target=document.getElementById(button.dataset.copyTarget);
  if(target)tickerCopyText(target.value,button);
}));
const tickerGroups=[...document.querySelectorAll('.ticker-group')];
document.getElementById('ticker-expand-all')?.addEventListener('click',()=>tickerGroups.forEach(group=>group.open=true));
document.getElementById('ticker-collapse-all')?.addEventListener('click',()=>tickerGroups.forEach(group=>group.open=false));
document.getElementById('ticker-search')?.addEventListener('input',event=>{
  const query=event.target.value.trim().toLowerCase();let visible=0;
  tickerGroups.forEach(group=>{let groupVisible=0;group.querySelectorAll('.ticker-row').forEach(row=>{
    const show=!query||row.dataset.search.includes(query);row.hidden=!show;if(show){groupVisible++;visible++;}
  });group.hidden=groupVisible===0;if(query&&groupVisible)group.open=true;});
  const empty=document.getElementById('ticker-empty');if(empty)empty.style.display=visible?'none':'block';
});
"""


if __name__ == "__main__":
    data = load_catalog()
    print(f"Ticker 主表快照：{len(data['all_tickers'])} 个不重复代码 / {len(data['categories'])} 类")
