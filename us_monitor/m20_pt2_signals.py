# -*- coding: utf-8 -*-
"""PivotTrend2 全信号归档与潜在趋势追踪页。

本地扫描 Drive 中已经生成的 PivotTrend2 PDF，按 ``ticker / 周期 / 日期 / 方向``
去重，并生成一个可搜索、可复制的独立网页。公开 CI 看不到本地 Drive，因此该模块由
``publish_pt2_signals.sh`` 在 Mac 上调用；网页只包含解析后的信号与来源文件名，不包含
任何本地路径。
"""
from __future__ import annotations

import argparse
import csv
import html
import io
import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable


DEFAULT_SOURCE = Path(
    "/Users/clair/My Drive (0xamberlbb01@gmail.com)/波哥信号归档/PivotTrend2产出"
)
DEFAULT_OUTPUT = Path(__file__).resolve().parents[1] / "docs" / "pt2-signals.html"
TF_ORDER = {"1W": 0, "3D": 1, "1D": 2, "3H": 3, "2H": 4}
SCORE_WEIGHTS = {"3D": 0.45, "1D": 0.35, "3H": 0.20, "2H": 0.15, "1W": 0.55}
SIDE_LABEL = {"long": "多", "short": "空"}
SIDE_SYMBOL = {"long": "▲", "short": "▼"}
SYMBOL_RE = re.compile(
    r"(?<![A-Z0-9])((?:NASDAQ|NYSE|AMEX|CBOE|HKEX|SSE|SZSE|BSE|TVC|OKX|SGX|OSE|KRX):"
    r"[A-Z0-9._!\-]+)(?![A-Z0-9._!\-])"
)
SIGNAL_RE = re.compile(r"\b(1W|3D|1D|3H|2H)\s+(\d{2}-\d{2})\s*([▲▼↑↓])")
SCORE_ROW_RE = re.compile(
    r"^\s*((?:NASDAQ|NYSE|AMEX|CBOE|HKEX|SSE|SZSE|BSE|TVC|OKX|SGX|OSE|KRX|OTC):"
    r"[A-Z0-9._!\-]+)\s+(1W|3D|1D|3H|2H)\s+(\d{1,3})\s+(\d{1,3})\s*$",
    re.MULTILINE,
)
STAMP_RE = re.compile(r"_(\d{8})\.pdf$", re.IGNORECASE)
GENERATED_DATE_RE = re.compile(r"\bGenerated:\s*(\d{4}-\d{2}-\d{2})\b", re.IGNORECASE)


@dataclass(frozen=True)
class ParsedSignal:
    symbol: str
    timeframe: str
    signal_date: date
    side: str


@dataclass(frozen=True)
class ScoreSnapshot:
    symbol: str
    timeframe: str
    long_score: int
    short_score: int
    document_date: date
    source: str


@dataclass
class SignalEvent:
    symbol: str
    timeframe: str
    signal_date: date
    side: str
    first_seen: date
    last_seen: date
    sources: set[str] = field(default_factory=set)
    source_methods: set[str] = field(default_factory=set)

    @property
    def key(self) -> tuple[str, str, date, str]:
        return self.symbol, self.timeframe, self.signal_date, self.side


def _document_date(path: Path) -> date:
    match = STAMP_RE.search(path.name)
    if match:
        return datetime.strptime(match.group(1), "%Y%m%d").date()
    return datetime.fromtimestamp(path.stat().st_mtime).date()


def _score_document_date(path: Path, cover_text: str) -> date:
    generated = GENERATED_DATE_RE.search(cover_text)
    if generated:
        return date.fromisoformat(generated.group(1))
    return _document_date(path)


def resolve_signal_date(mm_dd: str, document_date: date) -> date:
    """把 PDF 中不含年份的 MM-DD 还原为最接近文档生成日的过去日期。"""
    month, day = map(int, mm_dd.split("-"))
    candidate = date(document_date.year, month, day)
    if candidate > document_date + timedelta(days=31):
        candidate = date(document_date.year - 1, month, day)
    return candidate


def parse_page_text(text: str, document_date: date) -> list[ParsedSignal]:
    """解析单个明细页；无 ``信号归纳`` 的封面、索引和图页不会产生事件。"""
    if "信号归纳" not in text:
        return []
    symbol_match = SYMBOL_RE.search(text.upper())
    if not symbol_match:
        return []
    symbol = symbol_match.group(1)
    summary = text.split("信号归纳", 1)[1]
    # 防止图页正文中的其他日期被误当成信号，只读归纳后的首行。
    summary = summary.splitlines()[0].lstrip("：: ")
    parsed = []
    for timeframe, mm_dd, marker in SIGNAL_RE.findall(summary):
        parsed.append(
            ParsedSignal(
                symbol=symbol,
                timeframe=timeframe,
                signal_date=resolve_signal_date(mm_dd, document_date),
                side="long" if marker in "▲↑" else "short",
            )
        )
    return parsed


def parse_score_rows(
    text: str,
    document_date: date,
    source: str = "",
) -> list[ScoreSnapshot]:
    """解析 PDF 索引页中的 ``市场:TICKER / TF / long / short`` 原始分数。"""
    rows = []
    for symbol, timeframe, long_score, short_score in SCORE_ROW_RE.findall(text.upper()):
        long_value, short_value = int(long_score), int(short_score)
        if not (0 <= long_value <= 100 and 0 <= short_value <= 100):
            continue
        rows.append(
            ScoreSnapshot(
                symbol=symbol,
                timeframe=timeframe,
                long_score=long_value,
                short_score=short_value,
                document_date=document_date,
                source=source,
            )
        )
    return rows


def _source_method(cover_text: str) -> str:
    labels = []
    if "图页矢量反推" in cover_text:
        labels.append("图页反推")
    else:
        labels.append("索引表")
    if "人工核对修正" in cover_text:
        labels.append("含人工修正")
    return "+".join(labels)


def parse_pdf(path: Path) -> tuple[list[ParsedSignal], str, date]:
    import fitz

    document_date = _document_date(path)
    signals: list[ParsedSignal] = []
    with fitz.open(path) as doc:
        cover_text = "\n".join(page.get_text("text") for page in list(doc)[:3])
        method = _source_method(cover_text)
        for page in doc:
            signals.extend(parse_page_text(page.get_text("text"), document_date))
    return signals, method, document_date


def discover_pdfs(source_dir: Path) -> list[Path]:
    return sorted(
        path
        for path in source_dir.glob("PivotTrend2_*.pdf")
        if ".before_" not in path.name.lower()
    )


def discover_score_pdfs(source_dir: Path) -> list[Path]:
    """评分导出文件名不固定；目录内 PDF 由严格评分行正则进一步筛选。"""
    return sorted(path for path in source_dir.glob("*.pdf") if ".before_" not in path.name.lower())


def collect_scores(paths: Iterable[Path]) -> list[ScoreSnapshot]:
    """收集所有 PDF 的评分表；同日同 ticker/周期重复项合并为一个截面。"""
    import fitz

    merged: dict[tuple[str, str, date], ScoreSnapshot] = {}
    for path in paths:
        with fitz.open(path) as doc:
            cover_text = doc[0].get_text("text") if len(doc) else ""
            document_date = _score_document_date(path, cover_text)
            for page in doc:
                for row in parse_score_rows(page.get_text("text"), document_date, path.name):
                    key = (row.symbol, row.timeframe, row.document_date)
                    current = merged.get(key)
                    if current is None or (row.long_score, row.short_score) != (
                        current.long_score,
                        current.short_score,
                    ):
                        merged[key] = row
    return sorted(
        merged.values(),
        key=lambda row: (row.document_date, row.symbol, -TF_ORDER.get(row.timeframe, 99)),
        reverse=True,
    )


def collect_events(paths: Iterable[Path]) -> tuple[list[SignalEvent], list[dict]]:
    merged: dict[tuple[str, str, date, str], SignalEvent] = {}
    documents: list[dict] = []
    for path in paths:
        signals, method, document_date = parse_pdf(path)
        documents.append(
            {
                "name": path.name,
                "date": document_date.isoformat(),
                "method": method,
                "signal_count": len(signals),
            }
        )
        for signal in signals:
            key = (signal.symbol, signal.timeframe, signal.signal_date, signal.side)
            event = merged.get(key)
            if event is None:
                event = SignalEvent(
                    symbol=signal.symbol,
                    timeframe=signal.timeframe,
                    signal_date=signal.signal_date,
                    side=signal.side,
                    first_seen=document_date,
                    last_seen=document_date,
                )
                merged[key] = event
            event.first_seen = min(event.first_seen, document_date)
            event.last_seen = max(event.last_seen, document_date)
            event.sources.add(path.name)
            event.source_methods.add(method)
    events = sorted(
        merged.values(),
        key=lambda event: (
            event.signal_date,
            event.last_seen,
            event.symbol,
            -TF_ORDER.get(event.timeframe, 99),
        ),
        reverse=True,
    )
    return events, documents


def _latest_for_timeframe(events: list[SignalEvent]) -> tuple[SignalEvent, bool]:
    newest_date = max(event.signal_date for event in events)
    newest = [event for event in events if event.signal_date == newest_date]
    newest.sort(key=lambda event: (event.last_seen, event.side), reverse=True)
    return newest[0], len({event.side for event in newest}) > 1


def build_states(events: list[SignalEvent]) -> list[dict]:
    grouped: dict[str, dict[str, list[SignalEvent]]] = defaultdict(lambda: defaultdict(list))
    for event in events:
        grouped[event.symbol][event.timeframe].append(event)

    states = []
    for symbol, timeframe_events in grouped.items():
        latest: dict[str, dict] = {}
        reversal_labels = []
        for timeframe, history in timeframe_events.items():
            history.sort(key=lambda event: (event.signal_date, event.last_seen))
            current, same_day_conflict = _latest_for_timeframe(history)
            previous = next(
                (
                    event
                    for event in reversed(history)
                    if event.signal_date < current.signal_date
                ),
                None,
            )
            changed = previous is not None and previous.side != current.side
            if changed:
                reversal_labels.append(
                    f"{timeframe}翻{'多' if current.side == 'long' else '空'} {current.signal_date:%m-%d}"
                )
            latest[timeframe] = {
                "side": current.side,
                "date": current.signal_date.isoformat(),
                "same_day_conflict": same_day_conflict,
                "changed": changed,
            }
        clear_sides = {
            item["side"] for item in latest.values() if not item["same_day_conflict"]
        }
        has_conflict = any(item["same_day_conflict"] for item in latest.values())
        if has_conflict:
            structure = "同日来源冲突"
        elif len(clear_sides) > 1:
            structure = "多空并存"
        elif len(latest) >= 2:
            structure = "多周期同向"
        else:
            structure = "单周期"
        latest_date = max(date.fromisoformat(item["date"]) for item in latest.values())
        dominant = next(iter(clear_sides)) if len(clear_sides) == 1 else "mixed"
        states.append(
            {
                "symbol": symbol,
                "latest": latest,
                "latest_date": latest_date.isoformat(),
                "structure": structure,
                "dominant": dominant,
                "change": " · ".join(reversal_labels) if reversal_labels else "未见方向切换",
                "event_count": sum(len(history) for history in timeframe_events.values()),
            }
        )
    return sorted(states, key=lambda row: (row["latest_date"], row["symbol"]), reverse=True)


def _score_bias(row: ScoreSnapshot | None) -> str:
    if row is None:
        return "neutral"
    spread = row.long_score - row.short_score
    if spread >= 5 and row.long_score >= 55:
        return "long"
    if spread <= -5 and row.short_score >= 55:
        return "short"
    return "neutral"


def _score_phase(latest: dict[str, ScoreSnapshot]) -> tuple[str, str]:
    biases = {timeframe: _score_bias(row) for timeframe, row in latest.items()}
    daily, base, fast = biases.get("1D"), biases.get("3D"), biases.get("3H")
    if daily == base == "long":
        return "趋势多", "long"
    if daily == base == "short":
        return "趋势空", "short"
    if daily == "long" and base != "short" and fast in ("long", "neutral"):
        return "转多观察", "long"
    if daily == "short" and base != "long" and fast in ("short", "neutral"):
        return "转空观察", "short"
    directional = {bias for bias in biases.values() if bias != "neutral"}
    if not directional:
        return "震荡", "mixed"
    if len(directional) > 1:
        return "多空拉扯", "mixed"
    direction = next(iter(directional))
    return ("单周期偏多", "long") if direction == "long" else ("单周期偏空", "short")


def _phase_score(latest: dict[str, ScoreSnapshot], phase: str, dominant: str) -> int:
    available = [(tf, row) for tf, row in latest.items() if tf in SCORE_WEIGHTS]
    total_weight = sum(SCORE_WEIGHTS[tf] for tf, _ in available) or 1.0
    weighted_spread = sum(
        SCORE_WEIGHTS[tf] * (row.long_score - row.short_score) for tf, row in available
    ) / total_weight
    separation = min(35.0, abs(weighted_spread) * 1.75)
    alignment = {
        "趋势多": 40.0,
        "趋势空": 40.0,
        "转多观察": 28.0,
        "转空观察": 28.0,
        "单周期偏多": 15.0,
        "单周期偏空": 15.0,
    }.get(phase, 0.0)
    base_bias = _score_bias(latest.get("3D"))
    if dominant == "mixed":
        base_confirm = 0.0
    elif base_bias == dominant:
        base_confirm = 25.0
    elif base_bias == "neutral":
        base_confirm = 12.0
    else:
        base_confirm = 0.0
    return max(0, min(100, round(alignment + separation + base_confirm)))


def build_score_states(scores: list[ScoreSnapshot]) -> list[dict]:
    """把多周期 long/short 原始分数转换成震荡→趋势状态机。"""
    grouped: dict[str, dict[date, dict[str, ScoreSnapshot]]] = defaultdict(
        lambda: defaultdict(dict)
    )
    for row in scores:
        grouped[row.symbol][row.document_date][row.timeframe] = row

    states = []
    range_phases = {"震荡", "多空拉扯", "单周期偏多", "单周期偏空"}
    trend_phases = {"转多观察", "转空观察", "趋势多", "趋势空"}
    for symbol, history in grouped.items():
        dates = sorted(history)
        latest_date = dates[-1]
        latest = history[latest_date]
        phase, dominant = _score_phase(latest)
        previous_phase = None
        if len(dates) > 1:
            previous_phase, _ = _score_phase(history[dates[-2]])
        just_transitioned = previous_phase in range_phases and phase in trend_phases
        score_cells = {
            timeframe: {
                "long": row.long_score,
                "short": row.short_score,
                "spread": row.long_score - row.short_score,
                "bias": _score_bias(row),
            }
            for timeframe, row in latest.items()
        }
        states.append(
            {
                "symbol": symbol,
                "latest_date": latest_date.isoformat(),
                "scores": score_cells,
                "phase": phase,
                "dominant": dominant,
                "phase_score": _phase_score(latest, phase, dominant),
                "change": (
                    f"{previous_phase} → {phase}" if just_transitioned else
                    f"前值 {previous_phase}" if previous_phase else "仅当前截面"
                ),
                "just_transitioned": just_transitioned,
                "sources": sorted({row.source for row in latest.values() if row.source}),
            }
        )
    return sorted(
        states,
        key=lambda row: (row["just_transitioned"], row["phase_score"], row["latest_date"]),
        reverse=True,
    )


def _event_payload(event: SignalEvent) -> dict:
    return {
        "symbol": event.symbol,
        "timeframe": event.timeframe,
        "signal_date": event.signal_date.isoformat(),
        "side": event.side,
        "first_seen": event.first_seen.isoformat(),
        "last_seen": event.last_seen.isoformat(),
        "sources": sorted(event.sources),
        "methods": sorted(event.source_methods),
    }


def _csv_text(events: list[SignalEvent]) -> str:
    stream = io.StringIO()
    writer = csv.writer(stream)
    writer.writerow(
        ["市场:TICKER", "周期", "方向", "信号日期", "首次收录", "最近收录", "来源文档"]
    )
    for event in events:
        writer.writerow(
            [
                event.symbol,
                event.timeframe,
                SIDE_LABEL[event.side],
                event.signal_date.isoformat(),
                event.first_seen.isoformat(),
                event.last_seen.isoformat(),
                " | ".join(sorted(event.sources)),
            ]
        )
    return stream.getvalue()


def render_page(
    events: list[SignalEvent],
    documents: list[dict],
    output: Path,
    *,
    scores: list[ScoreSnapshot] | None = None,
    generated_at: datetime | None = None,
) -> Path:
    scores = scores or []
    if not events and not scores:
        raise ValueError("未解析到任何 PivotTrend2 信号或评分，保留旧页面")
    generated_at = generated_at or datetime.now().astimezone()
    states = build_states(events)
    score_states = build_score_states(scores)
    event_rows = [_event_payload(event) for event in events]
    payload = {
        "score_states": score_states,
        "states": states,
        "events": event_rows,
        "timeframes": sorted(
            {event.timeframe for event in events} | {row.timeframe for row in scores},
            key=lambda tf: TF_ORDER.get(tf, 99),
        ),
    }
    data_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    csv_json = json.dumps(_csv_text(events), ensure_ascii=False).replace("<", "\\u003c")
    observed_dates = [event.signal_date for event in events] + [row.document_date for row in scores]
    first_date = min(observed_dates).isoformat()
    latest_date = max(observed_dates).isoformat()
    source_latest = max(doc["date"] for doc in documents)
    initial_panel = "scores" if score_states else "states"
    html_page = f'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
<title>PivotTrend2 全信号趋势追踪</title>
<style>
:root{{--ink:#18201d;--mut:#68716c;--bg:#f5f6f3;--sf:#fff;--bd:#d8ddd8;--up:#087a55;--dn:#b54444;--mix:#986a00;--accent:#2859a8}}
*{{box-sizing:border-box;min-width:0}}html,body{{max-width:100%;overflow-x:hidden}}
body{{margin:0;background:var(--bg);color:var(--ink);font:14px/1.5 -apple-system,BlinkMacSystemFont,"PingFang SC","Helvetica Neue",sans-serif}}
main{{width:min(1220px,100%);margin:auto;padding:10px 14px 48px}}a{{color:inherit;text-underline-offset:3px}}
.nav{{position:sticky;top:0;z-index:10;display:flex;gap:6px;flex-wrap:wrap;padding:8px 0;background:var(--bg)}}
.nav a,.tab,button{{border:1px solid var(--bd);border-radius:999px;background:var(--sf);padding:7px 12px;text-decoration:none;color:var(--ink);font:inherit;cursor:pointer}}
.nav a.on,.tab.on,button.primary{{background:var(--ink);color:white;border-color:var(--ink)}}
h1{{font-size:26px;margin:8px 0 3px}}.meta,.note{{color:var(--mut);font-size:12px}}.note{{margin-top:5px}}
.stats{{display:grid;grid-template-columns:repeat(5,1fr);gap:8px;margin:16px 0}}.stat,.box{{background:var(--sf);border:1px solid var(--bd);border-radius:11px;padding:11px}}
.stat b{{display:block;font-size:21px}}.toolbar{{display:flex;gap:7px;flex-wrap:wrap;align-items:center;margin:12px 0}}
input,select{{font:inherit;color:var(--ink);background:var(--sf);border:1px solid var(--bd);border-radius:9px;padding:8px 10px}}
input{{flex:1 1 230px}}select{{flex:0 1 150px}}.tab-panel{{display:none}}.tab-panel.on{{display:block}}
.count{{margin:8px 0;color:var(--mut)}}.table-wrap{{background:var(--sf);border:1px solid var(--bd);border-radius:11px;overflow:hidden}}
table{{width:100%;border-collapse:collapse;table-layout:fixed}}th,td{{padding:9px 8px;border-bottom:1px solid var(--bd);text-align:left;vertical-align:top;overflow-wrap:anywhere}}
th{{background:#ecefeb;color:var(--mut);font-size:12px}}tbody tr:last-child td{{border-bottom:0}}tbody tr:hover{{background:#eef5f1}}
.symbol{{font-weight:750}}.sig{{display:inline-flex;gap:4px;align-items:center;border:1px solid currentColor;border-radius:999px;padding:2px 7px;white-space:nowrap;margin:1px 3px 1px 0}}
.long{{color:var(--up)}}.short{{color:var(--dn)}}.mixed{{color:var(--mix)}}.muted{{color:var(--mut)}}.sources{{font-size:12px;color:var(--mut)}}
.disclosure{{margin-top:15px;padding-top:12px;border-top:1px solid var(--bd);color:var(--mut);font-size:12px}}
#statesTable th:nth-child(1){{width:145px}}#statesTable th:nth-child(2){{width:105px}}#statesTable th:nth-child(3){{width:43%}}
#eventsTable th:nth-child(1){{width:145px}}#eventsTable th:nth-child(2){{width:65px}}#eventsTable th:nth-child(3){{width:65px}}#eventsTable th:nth-child(4){{width:105px}}
#scoresTable th:nth-child(1){{width:145px}}#scoresTable th:nth-child(2){{width:95px}}#scoresTable th:nth-child(3){{width:85px}}#scoresTable th:nth-child(4){{width:40%}}
@media(max-width:720px){{main{{padding:10px 9px 34px}}h1{{font-size:22px}}.stats{{grid-template-columns:repeat(2,1fr)}}
.table-wrap{{border:0;background:transparent;overflow:visible}}table,tbody,tr,td{{display:block;width:100%}}thead{{display:none}}tbody{{display:grid;gap:9px}}
tr{{background:var(--sf);border:1px solid var(--bd);border-radius:10px;padding:7px 9px}}th:nth-child(n),td:nth-child(n){{width:100%!important}}
td{{display:grid;grid-template-columns:minmax(76px,31%) minmax(0,1fr);gap:8px;padding:5px 0;border:0}}td:before{{content:attr(data-label);color:var(--mut);font-size:12px}}
.toolbar>*{{flex:1 1 calc(50% - 7px)}}.toolbar input{{flex-basis:100%}}}}
</style></head><body><main>
<nav class="nav" aria-label="页面导航"><a href="bogo.html">波哥信号</a><a href="etf.html">ETF涨幅榜</a><a href="prescreen.html">走势预筛</a><a href="summary.html">七维历史</a><a class="on" href="pt2-signals.html">PT2趋势追踪</a></nav>
<header><h1>PivotTrend2 全信号趋势追踪</h1>
<div class="meta">信号范围 {first_date}—{latest_date} · 来源 PDF 更新至 {source_latest} · 页面生成 {html.escape(generated_at.strftime('%Y-%m-%d %H:%M %Z'))}</div>
<div class="note">先读 long/short 原始分数判断“震荡 → 转向观察 → 多周期趋势”，趋势成立后再接信号监控。阶段分是多周期分差与对齐度的透明启发式，不是收益预测，需另行回测。</div></header>
<section class="stats"><div class="stat"><b>{len(score_states)}</b>评分 Ticker</div><div class="stat"><b>{sum(1 for row in score_states if row['just_transitioned'])}</b>新近转势</div><div class="stat"><b>{len(states)}</b>信号 Ticker</div><div class="stat"><b>{len(events)}</b>唯一信号事件</div><div class="stat"><b>{len(documents)}</b>来源 PDF</div></section>
<div class="toolbar" id="globalTools"><button class="tab {'on' if initial_panel == 'scores' else ''}" data-panel="scores">趋势评分</button><button class="tab {'on' if initial_panel == 'states' else ''}" data-panel="states">最新信号</button><button class="tab" data-panel="events">全部事件</button><input id="q" placeholder="搜索 市场:TICKER / 来源文档"><select id="tf"><option value="">全部周期</option>{''.join(f'<option>{tf}</option>' for tf in payload['timeframes'])}</select><select id="side"><option value="">全部方向</option><option value="long">多</option><option value="short">空</option><option value="mixed">混合</option></select></div>
<div class="toolbar"><button class="primary" id="copyTickers">复制当前 Ticker</button><button id="copySignals">复制当前信号</button><button id="downloadCsv">下载全部 CSV</button><span class="meta">复制结果每个 ticker / 信号各占一行</span></div>
<section class="tab-panel {'on' if initial_panel == 'scores' else ''}" id="panel-scores"><div class="count" id="scoreCount"></div><div class="table-wrap"><table id="scoresTable"><thead><tr><th>市场:TICKER</th><th>阶段</th><th>阶段分</th><th>各周期 long / short（分差）</th><th>变化</th><th>来源</th></tr></thead><tbody></tbody></table></div></section>
<section class="tab-panel {'on' if initial_panel == 'states' else ''}" id="panel-states"><div class="count" id="stateCount"></div><div class="table-wrap"><table id="statesTable"><thead><tr><th>市场:TICKER</th><th>最新日期</th><th>各周期最新信号</th><th>结构</th><th>方向变化</th><th>历史事件</th></tr></thead><tbody></tbody></table></div></section>
<section class="tab-panel" id="panel-events"><div class="count" id="eventCount"></div><div class="table-wrap"><table id="eventsTable"><thead><tr><th>市场:TICKER</th><th>周期</th><th>方向</th><th>信号日期</th><th>首次/最近收录</th><th>来源 PDF</th></tr></thead><tbody></tbody></table></div></section>
<div class="disclosure">本页先用 PDF 原始 long/short 分数描述震荡、转向与多周期趋势，再把已出现的信号接到趋势状态之后。阶段分是本站启发式：对齐度 40 分、long-short 分离度 35 分、3D 确认 25 分；没有历史评分截面时只能判断当前结构，不能声称刚从震荡转出。未包含收益回测、现价确认或基本面判断，不构成投资建议。</div>
<script>const DATA={data_json};const CSV_TEXT={csv_json};const TF_ORDER={json.dumps(TF_ORDER)};
const q=document.getElementById('q'),tf=document.getElementById('tf'),side=document.getElementById('side');let active={json.dumps(initial_panel)};let visibleScores=[],visibleStates=[],visibleEvents=[];
const esc=s=>String(s).replace(/[&<>"']/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));
function sigHtml(v,tfName){{if(v.same_day_conflict)return `<span class="sig mixed">${{tfName}} 同日冲突</span>`;const cls=v.side==='long'?'long':'short',mark=v.side==='long'?'▲':'▼';return `<span class="sig ${{cls}}">${{tfName}} ${{mark}} ${{v.date.slice(5)}}</span>`;}}
function scoreHtml(v,tfName){{const cls=v.bias==='long'?'long':v.bias==='short'?'short':'mixed',sign=v.spread>0?'+':'';return `<span class="sig ${{cls}}">${{tfName}} ${{v.long}} / ${{v.short}} (${{sign}}${{v.spread}})</span>`;}}
function filtersScore(r){{const text=(r.symbol+' '+r.phase+' '+r.change+' '+r.sources.join(' ')).toLowerCase();const wanted=q.value.trim().toLowerCase();if(wanted&&!text.includes(wanted))return false;if(tf.value&&!r.scores[tf.value])return false;if(side.value&&r.dominant!==side.value)return false;return true;}}
function filtersState(r){{const text=(r.symbol+' '+r.structure+' '+r.change).toLowerCase();const wanted=q.value.trim().toLowerCase();if(wanted&&!text.includes(wanted))return false;if(tf.value&&!r.latest[tf.value])return false;if(side.value&&side.value!=='mixed'&&r.dominant!==side.value)return false;if(side.value==='mixed'&&r.dominant!=='mixed')return false;return true;}}
function filtersEvent(r){{const text=(r.symbol+' '+r.sources.join(' ')+' '+r.methods.join(' ')).toLowerCase();const wanted=q.value.trim().toLowerCase();return(!wanted||text.includes(wanted))&&(!tf.value||r.timeframe===tf.value)&&(!side.value||(side.value!=='mixed'&&r.side===side.value));}}
function render(){{visibleScores=DATA.score_states.filter(filtersScore);visibleStates=DATA.states.filter(filtersState);visibleEvents=DATA.events.filter(filtersEvent);document.getElementById('scoreCount').textContent=`显示 ${{visibleScores.length}} / ${{DATA.score_states.length}} 个评分 ticker；阶段分越高表示多周期方向分离与确认越充分，不等于越接近低风险入口`;document.getElementById('stateCount').textContent=`显示 ${{visibleStates.length}} / ${{DATA.states.length}} 个 ticker`;document.getElementById('eventCount').textContent=`显示 ${{visibleEvents.length}} / ${{DATA.events.length}} 条事件`;
document.querySelector('#scoresTable tbody').innerHTML=visibleScores.map(r=>{{const cells=Object.entries(r.scores).sort((a,b)=>(TF_ORDER[a[0]]??99)-(TF_ORDER[b[0]]??99)).map(([k,v])=>scoreHtml(v,k)).join('');const cls=r.dominant==='long'?'long':r.dominant==='short'?'short':'mixed';return `<tr><td data-label="市场:TICKER" class="symbol">${{esc(r.symbol)}}</td><td data-label="阶段" class="${{cls}}">${{r.just_transitioned?'★ ':''}}${{esc(r.phase)}}</td><td data-label="阶段分"><strong>${{r.phase_score}}</strong></td><td data-label="各周期 long / short">${{cells}}</td><td data-label="变化">${{esc(r.change)}}</td><td data-label="来源" class="sources">${{esc(r.sources.join(' · '))}}</td></tr>`;}}).join('');
document.querySelector('#statesTable tbody').innerHTML=visibleStates.map(r=>{{const sigs=Object.entries(r.latest).sort((a,b)=>(TF_ORDER[a[0]]??99)-(TF_ORDER[b[0]]??99)).map(([k,v])=>sigHtml(v,k)).join('');const cls=r.dominant==='long'?'long':r.dominant==='short'?'short':'mixed';return `<tr><td data-label="市场:TICKER" class="symbol">${{esc(r.symbol)}}</td><td data-label="最新日期">${{r.latest_date}}</td><td data-label="各周期最新信号">${{sigs}}</td><td data-label="结构" class="${{cls}}">${{esc(r.structure)}}</td><td data-label="方向变化">${{esc(r.change)}}</td><td data-label="历史事件">${{r.event_count}}</td></tr>`;}}).join('');
document.querySelector('#eventsTable tbody').innerHTML=visibleEvents.map(r=>`<tr><td data-label="市场:TICKER" class="symbol">${{esc(r.symbol)}}</td><td data-label="周期">${{r.timeframe}}</td><td data-label="方向" class="${{r.side}}">${{r.side==='long'?'▲ 多':'▼ 空'}}</td><td data-label="信号日期">${{r.signal_date}}</td><td data-label="首次/最近收录">${{r.first_seen}}<br><span class="muted">${{r.last_seen}}</span></td><td data-label="来源 PDF" class="sources">${{esc(r.sources.join(' · '))}}<br>${{esc(r.methods.join(' · '))}}</td></tr>`).join('');}}
async function copyText(text,button){{const old=button.textContent;try{{if(navigator.clipboard&&window.isSecureContext)await navigator.clipboard.writeText(text);else{{const area=document.createElement('textarea');area.value=text;area.style.position='fixed';area.style.opacity='0';document.body.appendChild(area);area.select();document.execCommand('copy');area.remove();}}button.textContent='已复制';}}catch(e){{button.textContent='复制失败';}}setTimeout(()=>button.textContent=old,1300);}}
document.querySelectorAll('[data-panel]').forEach(b=>b.onclick=()=>{{active=b.dataset.panel;document.querySelectorAll('[data-panel]').forEach(x=>x.classList.toggle('on',x===b));document.querySelectorAll('.tab-panel').forEach(p=>p.classList.toggle('on',p.id==='panel-'+active));}});
[q,tf,side].forEach(el=>el.addEventListener(el===q?'input':'change',render));
document.getElementById('copyTickers').onclick=e=>{{const rows=active==='scores'?visibleScores:active==='states'?visibleStates:visibleEvents;copyText([...new Set(rows.map(r=>r.symbol))].join('\\n'),e.currentTarget);}};
document.getElementById('copySignals').onclick=e=>{{if(active==='scores'){{copyText(visibleScores.map(r=>`${{r.symbol}} | ${{r.phase}} | 阶段分 ${{r.phase_score}}`).join('\\n'),e.currentTarget);return;}}const rows=active==='events'?visibleEvents:visibleStates.flatMap(s=>Object.entries(s.latest).map(([timeframe,v])=>({{symbol:s.symbol,timeframe,side:v.side,signal_date:v.date}})));copyText(rows.map(r=>`${{r.symbol}} | ${{r.timeframe}} | ${{r.signal_date}} | ${{r.side==='long'?'long':'short'}}`).join('\\n'),e.currentTarget);}};
document.getElementById('downloadCsv').onclick=()=>{{const blob=new Blob(['\ufeff'+CSV_TEXT],{{type:'text/csv;charset=utf-8'}}),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download='PivotTrend2_all_signals.csv';a.click();URL.revokeObjectURL(url);}};render();</script>
</main></body></html>'''
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html_page, encoding="utf-8")
    return output


def build_page(
    source_dir: Path = DEFAULT_SOURCE,
    output: Path = DEFAULT_OUTPUT,
    score_source: Path | None = None,
) -> Path:
    paths = discover_pdfs(source_dir)
    if not paths:
        raise FileNotFoundError(f"未找到 PivotTrend2 PDF: {source_dir}")
    events, documents = collect_events(paths)
    scores = collect_scores(paths)
    if score_source is not None:
        scores = collect_scores(discover_score_pdfs(score_source))
    return render_page(events, documents, output, scores=scores)


def main() -> None:
    parser = argparse.ArgumentParser(description="生成 PivotTrend2 全信号趋势追踪页")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--score-source", type=Path, help="含 long/short 评分表 PDF 的目录")
    args = parser.parse_args()
    output = build_page(args.source, args.output, args.score_source)
    print(f"OK {output}")


if __name__ == "__main__":
    main()
