# -*- coding: utf-8 -*-
"""Jack 趋势候选逐股可视化。

把一次技术预筛的候选池做成自包含静态页：每只股票都有日 K、EMA10、EMA21、
SMA50、历史状态切换、前瞻收益（只在已有后续数据时计算）与当前结构明细。

这里的事件是可复算的价格结构状态，不冒充 PivotTrend2 的 TriggerDay。
"""
from __future__ import annotations

import argparse
import html
import json
import math
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd
import yfinance as yf


DEFAULT_OUTPUT = Path(__file__).resolve().parents[1] / "docs" / "jack-screen.html"
BENCHMARK = "SPY"
DISPLAY_BARS = 260
FORWARD_WINDOWS = (5, 10, 20, 40, 63)


@dataclass(frozen=True)
class Candidate:
    ticker: str
    symbol: str
    name: str
    group: str


CANDIDATES = (
    Candidate("ATI", "NYSE:ATI", "ATI Inc.", "优先研究"),
    Candidate("VIRT", "NYSE:VIRT", "Virtu Financial, Inc.", "优先研究"),
    Candidate("DXPE", "NASDAQ:DXPE", "DXP Enterprises, Inc.", "优先研究"),
    Candidate("NESR", "NASDAQ:NESR", "National Energy Services Reunited", "优先研究"),
    Candidate("HPE", "NYSE:HPE", "Hewlett Packard Enterprise", "优先研究"),
    Candidate("IVZ", "NYSE:IVZ", "Invesco Ltd.", "优先研究"),
    Candidate("GDXJ", "AMEX:GDXJ", "VanEck Junior Gold Miners ETF", "ETF 主题趋势"),
    Candidate("SIL", "AMEX:SIL", "Global X Silver Miners ETF", "ETF 主题趋势"),
    Candidate("ARKG", "AMEX:ARKG", "ARK Genomic Revolution ETF", "ETF 主题趋势"),
    Candidate("COPX", "AMEX:COPX", "Global X Copper Miners ETF", "ETF 主题趋势"),
    Candidate("URA", "AMEX:URA", "Global X Uranium ETF", "ETF 主题趋势"),
    Candidate("PICK", "AMEX:PICK", "iShares MSCI Global Metals & Mining Producers ETF", "ETF 主题趋势"),
    Candidate("XBI", "AMEX:XBI", "SPDR S&P Biotech ETF", "ETF 主题趋势"),
    Candidate("IEO", "AMEX:IEO", "iShares U.S. Oil & Gas Exploration & Production ETF", "ETF 主题趋势"),
    Candidate("NLR", "AMEX:NLR", "VanEck Uranium and Nuclear ETF", "ETF 主题趋势"),
    Candidate("BLOK", "AMEX:BLOK", "Amplify Transformational Data Sharing ETF", "ETF 主题趋势"),
    Candidate("FET", "NYSE:FET", "Forum Energy Technologies, Inc.", "走势过关·等结构"),
    Candidate("KRO", "NYSE:KRO", "Kronos Worldwide, Inc.", "走势过关·等结构"),
    Candidate("HZO", "NYSE:HZO", "MarineMax, Inc.", "走势过关·等结构"),
    Candidate("CRON", "NASDAQ:CRON", "Cronos Group Inc.", "走势过关·等结构"),
    Candidate("NGL", "NYSE:NGL", "NGL Energy Partners LP", "走势过关·等结构"),
    Candidate("CHYM", "NASDAQ:CHYM", "Chime Financial, Inc.", "早期观察"),
    Candidate("AVAH", "NASDAQ:AVAH", "Aveanna Healthcare Holdings", "早期观察"),
    Candidate("NEO", "NASDAQ:NEO", "NeoGenomics, Inc.", "早期观察"),
    Candidate("CORT", "NASDAQ:CORT", "Corcept Therapeutics", "早期观察"),
    Candidate("APPN", "NASDAQ:APPN", "Appian Corporation", "早期观察"),
    Candidate("ATRC", "NASDAQ:ATRC", "AtriCure, Inc.", "早期观察"),
)


STATE_LABELS = {
    "range": "震荡/观察",
    "base": "基础改善",
    "expansion": "早期扩张",
    "trend": "趋势确认",
    "mature": "趋势延续",
}


def _finite(value, digits: int = 2):
    if value is None:
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return round(value, digits) if math.isfinite(value) else None


def _return(series: pd.Series, periods: int) -> pd.Series:
    return (series / series.shift(periods) - 1) * 100


def enrich_frame(frame: pd.DataFrame, benchmark_close: pd.Series) -> pd.DataFrame:
    """计算图表指标和无前视的历史状态序列。"""
    out = frame.copy().sort_index()
    close = out["Close"].astype(float)
    out["EMA10"] = close.ewm(span=10, adjust=False).mean()
    out["EMA21"] = close.ewm(span=21, adjust=False).mean()
    out["SMA50"] = close.rolling(50).mean()
    out["SMA150"] = close.rolling(150).mean()
    out["SMA200"] = close.rolling(200).mean()
    out["SMA200Slope20"] = _return(out["SMA200"], 20)
    out["High52"] = out["High"].rolling(252, min_periods=126).max()
    out["RS21"] = _return(close, 21) - _return(benchmark_close.reindex(out.index).ffill(), 21)
    out["RS63"] = _return(close, 63) - _return(benchmark_close.reindex(out.index).ffill(), 63)
    previous_close = close.shift(1)
    true_range = pd.concat(
        [out["High"] - out["Low"], (out["High"] - previous_close).abs(), (out["Low"] - previous_close).abs()],
        axis=1,
    ).max(axis=1)
    out["ATR14"] = true_range.rolling(14).mean()

    stage2 = (
        (close > out["SMA50"])
        & (out["SMA50"] > out["SMA150"])
        & (out["SMA150"] > out["SMA200"])
        & (out["SMA200Slope20"] > 0)
    ).fillna(False)
    ordered = ((close > out["EMA10"]) & (out["EMA10"] > out["EMA21"]) & (out["EMA21"] > out["SMA50"])).fillna(False)
    score = (
        (close > out["EMA10"]).astype(int) * 20
        + (out["EMA10"] > out["EMA21"]).astype(int) * 15
        + (out["EMA21"] > out["SMA50"]).astype(int) * 15
        + (out["SMA50"] > out["SMA150"]).astype(int) * 15
        + (out["SMA150"] > out["SMA200"]).astype(int) * 15
        + (out["SMA200Slope20"] > 0).astype(int) * 10
        + (out["RS21"] > 0).astype(int) * 5
        + (out["RS63"] > 0).astype(int) * 5
    )
    out["Score"] = score
    out["Stage2"] = stage2
    out["Ordered"] = ordered

    ages = []
    age = 0
    for active in stage2:
        age = age + 1 if active else 0
        ages.append(age)
    out["Stage2Age"] = ages

    states = []
    for idx, row in out.iterrows():
        if bool(row["Stage2"]) and row["Score"] >= 85:
            state = "trend" if int(row["Stage2Age"]) <= 20 else "mature"
        elif bool(row["Ordered"]) and row["Score"] >= 70:
            state = "expansion"
        elif row["Score"] >= 55:
            state = "base"
        else:
            state = "range"
        states.append(state)
    out["State"] = states
    return out


def state_events(frame: pd.DataFrame, limit: int = 12) -> list[dict]:
    """状态改变才产生事件；未来收益不足时保持空值，避免前视。"""
    events = []
    states = frame["State"].tolist()
    for pos, state in enumerate(states):
        if pos == 0 or state == states[pos - 1]:
            continue
        row = frame.iloc[pos]
        event = {
            "date": frame.index[pos].strftime("%Y-%m-%d"),
            "state": state,
            "label": STATE_LABELS[state],
            "previous": STATE_LABELS.get(states[pos - 1], "—"),
            "score": int(row["Score"]),
            "duration": 1,
            "forward": {},
        }
        for window in FORWARD_WINDOWS:
            event["forward"][str(window)] = (
                _finite((frame["Close"].iloc[pos + window] / row["Close"] - 1) * 100)
                if pos + window < len(frame)
                else None
            )
        events.append(event)

    for index, event in enumerate(events):
        start = frame.index.get_loc(pd.Timestamp(event["date"]))
        end = frame.index.get_loc(pd.Timestamp(events[index + 1]["date"])) if index + 1 < len(events) else len(frame)
        event["duration"] = int(end - start)
    return events[-limit:]


def candidate_payload(candidate: Candidate, frame: pd.DataFrame, benchmark_close: pd.Series) -> dict:
    enriched = enrich_frame(frame, benchmark_close)
    latest = enriched.iloc[-1]
    chart = enriched.tail(DISPLAY_BARS)
    events = state_events(enriched)
    gap_high = (latest["Close"] / latest["High52"] - 1) * 100 if latest["High52"] else None
    ema_ext = (latest["Close"] / latest["EMA10"] - 1) * 100 if latest["EMA10"] else None
    atr_ext = (latest["Close"] - latest["EMA10"]) / latest["ATR14"] if latest["ATR14"] else None
    avg_dollar_volume = (enriched["Close"] * enriched["Volume"]).tail(21).mean()

    bars = []
    for idx, row in chart.iterrows():
        bars.append(
            {
                "d": idx.strftime("%Y-%m-%d"),
                "o": _finite(row["Open"]), "h": _finite(row["High"]),
                "l": _finite(row["Low"]), "c": _finite(row["Close"]),
                "e10": _finite(row["EMA10"]), "e21": _finite(row["EMA21"]),
                "s50": _finite(row["SMA50"]),
            }
        )

    state = str(latest["State"])
    return {
        "ticker": candidate.ticker,
        "symbol": candidate.symbol,
        "name": candidate.name,
        "group": candidate.group,
        "date": enriched.index[-1].strftime("%Y-%m-%d"),
        "state": state,
        "state_label": STATE_LABELS[state],
        "score": int(latest["Score"]),
        "stage2_age": int(latest["Stage2Age"]),
        "rs21": _finite(latest["RS21"]),
        "rs63": _finite(latest["RS63"]),
        "gap52": _finite(gap_high),
        "ema10_extension": _finite(ema_ext),
        "atr_extension": _finite(atr_ext),
        "avg_dollar_volume21": _finite(avg_dollar_volume, 0),
        "bars": bars,
        "events": events,
    }


def _extract_frame(download: pd.DataFrame, ticker: str) -> pd.DataFrame | None:
    try:
        if isinstance(download.columns, pd.MultiIndex):
            frame = download.xs(ticker, axis=1, level=1)
        else:
            frame = download
    except (KeyError, ValueError):
        return None
    wanted = [field for field in ("Open", "High", "Low", "Close", "Volume") if field in frame]
    if len(wanted) < 5:
        return None
    frame = frame[wanted].dropna(subset=["Open", "High", "Low", "Close"])
    return frame if len(frame) >= 230 else None


def download_payload(candidates: tuple[Candidate, ...] = CANDIDATES) -> list[dict]:
    tickers = [candidate.ticker for candidate in candidates] + [BENCHMARK]
    raw = yf.download(
        tickers,
        period="2y",
        interval="1d",
        auto_adjust=True,
        progress=False,
        group_by="column",
        threads=True,
    )
    benchmark = _extract_frame(raw, BENCHMARK)
    if benchmark is None:
        raise RuntimeError("未取得 AMEX:SPY 基准行情")
    rows = []
    missing = []
    for candidate in candidates:
        frame = _extract_frame(raw, candidate.ticker)
        if frame is None:
            missing.append(candidate.symbol)
            continue
        rows.append(candidate_payload(candidate, frame, benchmark["Close"]))
    if not rows:
        raise RuntimeError("未取得任何候选股票行情")
    if missing:
        print("WARN 缺少行情: " + ", ".join(missing))
    return rows


def render_page(rows: list[dict], output: Path, generated_at: datetime | None = None) -> Path:
    if not rows:
        raise ValueError("没有可渲染的候选标的")
    generated_at = generated_at or datetime.now().astimezone()
    payload = json.dumps(rows, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    data_date = max(row["date"] for row in rows)
    group_counts = {group: sum(row["group"] == group for row in rows) for group in dict.fromkeys(row["group"] for row in rows)}
    group_summary = " · ".join(f"{html.escape(group)} {count}" for group, count in group_counts.items())

    page = f'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
<title>Jack 趋势候选逐股图</title>
<style>
:root{{--ink:#1a211e;--mut:#68716c;--bg:#f5f6f3;--sf:#fff;--bd:#d9ded9;--grid:#e9edea;--up:#08a66c;--dn:#d94b4b;--amber:#986a00;--blue:#176eb2;--e10:#e64d55;--e21:#16a261;--s50:#7655d9;--shadow:0 8px 28px rgba(31,45,38,.07)}}
@media(prefers-color-scheme:dark){{:root{{--ink:#eef2ef;--mut:#a8b0aa;--bg:#111512;--sf:#181d19;--bd:#303832;--grid:#273029;--amber:#e0a938;--blue:#68aaf0;--shadow:none}}}}
*{{box-sizing:border-box;min-width:0}}html,body{{margin:0;max-width:100%;background:var(--bg);color:var(--ink);font:14px/1.5 -apple-system,BlinkMacSystemFont,"PingFang SC","Helvetica Neue",sans-serif}}
button,a{{font:inherit}}button{{color:inherit}}main{{width:min(1500px,100%);margin:auto;padding:10px 14px 42px}}.nav{{display:flex;gap:6px;flex-wrap:wrap;position:sticky;top:0;z-index:20;padding:8px 0;background:var(--bg)}}.nav a,.chip,.ticker{{border:1px solid var(--bd);border-radius:999px;background:var(--sf);padding:7px 11px;text-decoration:none;color:inherit;cursor:pointer}}.nav a.on,.ticker.on{{background:var(--ink);color:var(--sf);border-color:var(--ink)}}
h1{{font-size:26px;margin:8px 0 2px}}.meta,.sub,.empty{{font-size:12px;color:var(--mut)}}.summary{{display:flex;gap:8px;flex-wrap:wrap;margin:13px 0}}.summary .chip{{cursor:default}}.workbench{{display:grid;grid-template-columns:235px minmax(0,1fr);gap:12px;align-items:start}}.rail,.panel,.chart-card,.events-card{{background:var(--sf);border:1px solid var(--bd);border-radius:12px;box-shadow:var(--shadow)}}.rail{{position:sticky;top:58px;max-height:calc(100vh - 72px);overflow:auto;padding:9px}}.group-title{{margin:10px 7px 5px;font-size:12px;color:var(--mut);font-weight:700}}.ticker{{display:block;width:100%;text-align:left;border-radius:8px;margin:4px 0;padding:8px 9px}}.ticker b{{display:block}}.ticker span{{font-size:11px;color:var(--mut)}}.ticker.on span{{color:inherit;opacity:.76}}
.content{{display:grid;gap:12px}}.head{{display:flex;justify-content:space-between;gap:12px;align-items:flex-start}}.head h2{{margin:0;font-size:21px}}.badge{{display:inline-flex;border:1px solid currentColor;border-radius:999px;padding:2px 8px;font-size:12px;font-weight:700}}.state-trend,.state-mature{{color:var(--up)}}.state-expansion{{color:var(--amber)}}.state-base{{color:var(--blue)}}.state-range{{color:var(--mut)}}.tv{{color:var(--blue);text-underline-offset:3px}}.chart-card{{padding:10px}}.legend{{display:flex;gap:11px;flex-wrap:wrap;align-items:center;font-size:12px;color:var(--mut)}}.dot{{display:inline-block;width:11px;height:3px;border-radius:4px;margin-right:4px;vertical-align:middle}}#chart{{display:block;width:100%;height:auto;min-height:390px}}.gridline{{stroke:var(--grid);stroke-width:1}}.axis{{fill:var(--mut);font-size:10px}}.candle-up{{stroke:var(--up);fill:var(--up)}}.candle-down{{stroke:var(--dn);fill:var(--dn)}}.event-mark{{fill:var(--blue);stroke:var(--sf);stroke-width:1;cursor:pointer}}.event-text{{fill:var(--blue);font-size:9px;font-weight:750;pointer-events:none}}.event-mark:focus{{outline:none;stroke:var(--ink);stroke-width:2}}
.lower{{display:grid;grid-template-columns:minmax(0,1.55fr) minmax(290px,.75fr);gap:12px}}.events-card{{overflow:hidden}}table{{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums}}th,td{{padding:8px 7px;border-bottom:1px solid var(--bd);text-align:left;white-space:nowrap}}th{{font-size:11px;color:var(--mut);background:color-mix(in srgb,var(--sf) 88%,var(--grid))}}tbody tr{{cursor:pointer}}tbody tr:hover,tbody tr.on{{background:color-mix(in srgb,var(--sf) 82%,var(--grid))}}.panel{{padding:12px}}.panel h3{{margin:0 0 9px}}.metrics{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:7px}}.metric{{background:color-mix(in srgb,var(--sf) 84%,var(--grid));border-radius:8px;padding:8px}}.metric span{{display:block;font-size:11px;color:var(--mut)}}.metric b{{font-variant-numeric:tabular-nums}}.note{{border-top:1px solid var(--bd);padding-top:9px;margin-top:10px;color:var(--mut);font-size:12px}}.positive{{color:var(--up)}}.negative{{color:var(--dn)}}
@media(max-width:850px){{main{{padding:8px 9px 32px}}h1{{font-size:22px}}.workbench{{grid-template-columns:1fr}}.rail{{position:static;display:flex;overflow:auto;max-height:none;gap:5px}}.group-title{{display:none}}.ticker{{min-width:132px;margin:0}}.lower{{grid-template-columns:1fr}}#chart{{min-height:300px}}.events-card{{overflow-x:auto}}}}
@media(prefers-reduced-motion:reduce){{*{{scroll-behavior:auto!important}}}}
</style></head><body><main>
<nav class="nav" aria-label="页面导航"><a href="bogo.html">波哥信号</a><a href="etf.html">ETF涨幅榜</a><a href="prescreen.html">走势预筛</a><a href="pt2-signals.html">PT2趋势追踪</a><a class="on" href="jack-screen.html">逐股趋势图</a></nav>
<header><h1>Jack 趋势候选逐股图</h1><div class="meta">数据至 {data_date} · {html.escape(generated_at.strftime('%Y-%m-%d %H:%M %Z'))} 生成 · {group_summary}</div><div class="sub">先判断“震荡 → 扩张 → 趋势”，趋势成立后才接信号监控。蓝色 T 是本页可复算的趋势状态切换，不是 PivotTrend2 TriggerDay。</div></header>
<div class="summary"><span class="chip">状态分：均线顺序 65%</span><span class="chip">SMA200 斜率 10%</span><span class="chip">相对 AMEX:SPY 强度 10%</span><span class="chip">价格位置 15%</span><span class="chip">研究用途，非买点</span></div>
<div class="workbench"><aside class="rail" id="rail" aria-label="候选标的"></aside><section class="content">
<div class="head"><div><h2 id="title"></h2><div class="meta" id="subtitle"></div></div><div><span class="badge" id="stateBadge"></span> <a class="tv" id="tvLink" target="_blank" rel="noopener">TradingView ↗</a></div></div>
<div class="chart-card"><div class="legend"><span><i class="dot" style="background:var(--e10)"></i>EMA10</span><span><i class="dot" style="background:var(--e21)"></i>EMA21</span><span><i class="dot" style="background:var(--s50)"></i>SMA50</span><span>蓝色 T：趋势状态切换，点击查看</span></div><svg id="chart" viewBox="0 0 1180 430" role="img" aria-labelledby="chartTitle"><title id="chartTitle">标的趋势图</title></svg></div>
<div class="lower"><div class="events-card"><table><thead><tr><th>日期</th><th>状态</th><th>评分</th><th>持续</th><th>T+5</th><th>T+10</th><th>T+20</th><th>T+40</th><th>T+63</th></tr></thead><tbody id="eventRows"></tbody></table></div><aside class="panel"><h3 id="detailTitle">当前结构</h3><div class="metrics" id="metrics"></div><div class="note" id="detailNote"></div></aside></div>
</section></div><div class="note">方法边界：历史事件只使用事件当日及以前的价格、均线和相对强度；T+n 仅在后续交易日已经真实存在时显示。走势过关不代表估值、基本面、流动性或风险回报已经过关，也不构成投资建议。</div>
<script>const DATA={payload};let current=0,selectedEvent=null;const NS='http://www.w3.org/2000/svg';
const fmt=(v,suffix='')=>v==null?'—':`${{Number(v).toFixed(2)}}${{suffix}}`;const cls=v=>v==null?'':v>0?'positive':v<0?'negative':'';const esc=s=>String(s).replace(/[&<>"']/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));
function svg(tag,attrs={{}}){{const el=document.createElementNS(NS,tag);Object.entries(attrs).forEach(([k,v])=>el.setAttribute(k,v));return el;}}
function buildRail(){{const rail=document.getElementById('rail');let last='';DATA.forEach((r,i)=>{{if(r.group!==last){{const h=document.createElement('div');h.className='group-title';h.textContent=r.group;rail.appendChild(h);last=r.group;}}const b=document.createElement('button');b.className='ticker';b.dataset.index=i;b.innerHTML=`<b>${{esc(r.symbol)}}</b><span>${{esc(r.state_label)}} · ${{r.score}}分</span>`;b.onclick=()=>show(i);rail.appendChild(b);}});}}
function linePath(bars,key,x,y){{let d='';bars.forEach((b,i)=>{{if(b[key]==null)return;d+=`${{d?'L':'M'}}${{x(i).toFixed(1)}},${{y(b[key]).toFixed(1)}}`;}});return d;}}
function draw(r){{const el=document.getElementById('chart');el.replaceChildren();const title=svg('title',{{id:'chartTitle'}});title.textContent=`${{r.symbol}} 日线趋势图，数据至 ${{r.date}}`;el.appendChild(title);const bars=r.bars,W=1180,H=430,p={{l:24,r:58,t:26,b:35}},iw=W-p.l-p.r,ih=H-p.t-p.b;const values=bars.flatMap(b=>[b.h,b.l,b.e10,b.e21,b.s50]).filter(v=>v!=null);let lo=Math.min(...values),hi=Math.max(...values),pad=(hi-lo)*.07;lo-=pad;hi+=pad;const x=i=>p.l+(i+.5)*iw/bars.length,y=v=>p.t+(hi-v)/(hi-lo)*ih;
for(let i=0;i<=5;i++){{const yy=p.t+i*ih/5;el.appendChild(svg('line',{{x1:p.l,y1:yy,x2:W-p.r,y2:yy,class:'gridline'}}));const t=svg('text',{{x:W-p.r+6,y:yy+3,class:'axis'}});t.textContent=(hi-i*(hi-lo)/5).toFixed(2);el.appendChild(t);}}
let lastMonth='';bars.forEach((b,i)=>{{const month=b.d.slice(0,7);if(month!==lastMonth){{const xx=x(i);el.appendChild(svg('line',{{x1:xx,y1:p.t,x2:xx,y2:H-p.b,class:'gridline'}}));const t=svg('text',{{x:xx+3,y:H-12,class:'axis'}});t.textContent=b.d.slice(2,7);el.appendChild(t);lastMonth=month;}}const c=svg('line',{{x1:x(i),x2:x(i),y1:y(b.h),y2:y(b.l),class:b.c>=b.o?'candle-up':'candle-down'}});el.appendChild(c);const width=Math.max(1.5,iw/bars.length*.62),top=y(Math.max(b.o,b.c)),bottom=y(Math.min(b.o,b.c));el.appendChild(svg('rect',{{x:x(i)-width/2,y:top,width,height:Math.max(1,bottom-top),class:b.c>=b.o?'candle-up':'candle-down'}}));}});
[['e10','var(--e10)'],['e21','var(--e21)'],['s50','var(--s50)']].forEach(([key,color])=>el.appendChild(svg('path',{{d:linePath(bars,key,x,y),fill:'none',stroke:color,'stroke-width':'1.4'}})));
const indexByDate=Object.fromEntries(bars.map((b,i)=>[b.d,i]));r.events.forEach((e,i)=>{{const idx=indexByDate[e.date];if(idx==null)return;const yy=Math.max(p.t+12,y(bars[idx].h)-14),g=svg('g',{{tabindex:'0',role:'button','aria-label':`${{e.date}} ${{e.label}}`}}),mark=svg('rect',{{x:x(idx)-5,y:yy-9,width:10,height:10,rx:1,class:'event-mark'}}),txt=svg('text',{{x:x(idx),y:yy-12,'text-anchor':'middle',class:'event-text'}});txt.textContent='T';g.append(mark,txt);g.onclick=()=>selectEvent(i);g.onkeydown=ev=>{{if(ev.key==='Enter'||ev.key===' ')selectEvent(i);}};el.appendChild(g);}});}}
function metric(label,value,klass=''){{return `<div class="metric"><span>${{label}}</span><b class="${{klass}}">${{value}}</b></div>`;}}
function showDetails(r,e=null){{document.getElementById('detailTitle').textContent=e?`${{e.date}} · ${{e.label}}`:'当前结构';const m=e?[metric('前一状态',e.previous),metric('状态评分',`${{e.score}} / 100`),metric('状态持续',`${{e.duration}} 个交易日`),...['5','10','20','40','63'].map(n=>metric(`T+${{n}}`,fmt(e.forward[n],'%'),cls(e.forward[n])))] : [metric('状态评分',`${{r.score}} / 100`),metric('Stage 2 年龄',r.stage2_age?`${{r.stage2_age}} 日`:'未成立'),metric('21日相对强度',fmt(r.rs21,'%'),cls(r.rs21)),metric('63日相对强度',fmt(r.rs63,'%'),cls(r.rs63)),metric('距52周高点',fmt(r.gap52,'%'),cls(r.gap52)),metric('距 EMA10',fmt(r.ema10_extension,'%'),cls(r.ema10_extension)),metric('EMA10 ATR延伸',fmt(r.atr_extension,' ATR'),cls(-r.atr_extension)),metric('21日均成交额',r.avg_dollar_volume21==null?'—':`$${{(r.avg_dollar_volume21/1e6).toFixed(1)}}M`)];document.getElementById('metrics').innerHTML=m.join('');document.getElementById('detailNote').textContent=e?'历史前瞻收益只是检验状态可延续性，不代表相同状态未来必然复制。':r.state==='mature'?'趋势仍在，但已不是新鲜启动；等待回踩、收缩或新基座。':r.state==='trend'?'趋势已确认，下一层才是信号监控与风险回报检查。':r.state==='expansion'?'结构正在扩张，继续观察能否形成 Stage 2 与相对强度确认。':'尚未达到趋势确认，不因单次信号升级。';}}
function selectEvent(i){{selectedEvent=i;const r=DATA[current];document.querySelectorAll('#eventRows tr').forEach((tr,j)=>tr.classList.toggle('on',j===i));showDetails(r,r.events[i]);}}
function show(i){{current=i;selectedEvent=null;const r=DATA[i];document.querySelectorAll('.ticker').forEach((b,j)=>b.classList.toggle('on',j===i));document.getElementById('title').textContent=`${{r.symbol}} · ${{r.name}}`;document.getElementById('subtitle').textContent=`${{r.group}} · 数据至 ${{r.date}} · 图表最近 ${{r.bars.length}} 个交易日`;const badge=document.getElementById('stateBadge');badge.textContent=`${{r.state_label}} · ${{r.score}}`;badge.className=`badge state-${{r.state}}`;document.getElementById('tvLink').href=`https://www.tradingview.com/chart/?symbol=${{encodeURIComponent(r.symbol)}}`;draw(r);document.getElementById('eventRows').innerHTML=r.events.map((e,j)=>`<tr data-index="${{j}}"><td>${{e.date}}</td><td>${{e.previous}} → <b>${{e.label}}</b></td><td>${{e.score}}</td><td>${{e.duration}}</td>${{['5','10','20','40','63'].map(n=>`<td class="${{cls(e.forward[n])}}">${{fmt(e.forward[n],'%')}}</td>`).join('')}}</tr>`).join('')||'<tr><td colspan="9" class="empty">最近没有状态切换</td></tr>';document.querySelectorAll('#eventRows tr[data-index]').forEach(tr=>tr.onclick=()=>selectEvent(Number(tr.dataset.index)));showDetails(r);}}
buildRail();show(0);</script></main></body></html>'''
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(page, encoding="utf-8")
    return output


def build_page(output: Path = DEFAULT_OUTPUT) -> Path:
    return render_page(download_payload(), output)


def main() -> None:
    parser = argparse.ArgumentParser(description="生成 Jack 趋势候选逐股可视化")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    output = build_page(args.output)
    print(f"OK {output}")


if __name__ == "__main__":
    main()
