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
import datetime as DT
from pathlib import Path
from zoneinfo import ZoneInfo

from . import m13_bogo as m13

STORE = Path(__file__).resolve().parent / ".bogo_cn_signals.json"
ENGINE_STORE = Path(__file__).resolve().parent / ".m19_latest.json"
SG = ZoneInfo("Asia/Singapore")
BATCH_DUE = {"1050": (11, 20), "1520": (15, 55), "1600": (16, 40), "us": (6, 30)}
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
.plan{display:block;margin-top:5px;padding:4px 6px;border-left:3px solid var(--ink2);color:var(--ink2)}
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
                want = {r["代码"] for r in d["rows"]}   # 全清单导图(强+弱)
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


def _engine_plans() -> dict:
    """只读取 m19 当日快照；执行计划不改变波哥信号判定。"""
    try:
        payload = json.loads(ENGINE_STORE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    out = {}
    for profile in payload.get("profiles", {}).values():
        try:
            generated = DT.datetime.strptime(profile["generated"], "%Y-%m-%d %H:%M UTC").replace(
                tzinfo=DT.timezone.utc)
            if DT.datetime.now(DT.timezone.utc) - generated > DT.timedelta(hours=36):
                continue
        except (KeyError, TypeError, ValueError):
            continue
        for signal in profile.get("signals", []):
            ticker = str(signal.get("ticker", ""))
            out[ticker.split(".", 1)[0]] = signal
    return out


def _source_warning(key: str, src: str, now: DT.datetime | None = None) -> str:
    """Return a freshness notice using the scheduler's Singapore calendar.

    GitHub Actions runs in UTC, while deck filenames and launchd schedules use
    Singapore dates. Comparing them without a timezone made a fresh Saturday US
    deck (for Friday's NY session) look missing during the cloud build.
    """
    if not src[:4].isdigit():
        return ""
    now = now or DT.datetime.now(SG)
    if now.tzinfo is None:
        now = now.replace(tzinfo=SG)
    else:
        now = now.astimezone(SG)
    if src[:4] == now.strftime("%m%d"):
        return ""

    run_days = {1, 2, 3, 4, 5} if key == "us" else {0, 1, 2, 3, 4}
    if now.weekday() not in run_days:
        return ""

    rpt = f"{src[:2]}-{src[2:4]}"
    due_h, due_m = BATCH_DUE.get(key, (23, 59))
    if (now.hour, now.minute) >= (due_h, due_m):
        return (f'<span style="color:#c0392b;font-weight:700">⚠ 今日源件未到，以下为 '
                f'{H.escape(rpt)} 批数据</span> · ')
    return f'<span style="color:#888">今日批次未到时间，以下为 {H.escape(rpt)} 批</span> · '


def _plan_line(code: str, plans: dict) -> str:
    signal = plans.get(code)
    if not signal:
        return ""
    plan = signal.get("plan")
    setups = "+".join(signal.get("setup_names", [])) or "—"
    triggers = "+".join(signal.get("triggers", [])) or "—"
    if not plan:
        return (f'\n<span class="plan"><b>三层执行计划</b>（不影响波哥信号）：'
                f'{H.escape(setups)} → {H.escape(triggers)} · ADR评级拒，不出计划</span>')
    return (f'\n<span class="plan"><b>三层执行计划</b>（不影响波哥信号）：'
            f'{H.escape(setups)} → {H.escape(triggers)} · Entry {plan["entry_stop"]:.2f}'
            f' / Limit {plan["entry_limit"]:.2f} / Stop {plan["stop"]:.2f}'
            f' / 1R {plan["target_1R"]:.2f} / 2R {plan["target_2R"]:.2f}'
            f' · Stop {plan["stop_pct"]:.2f}% / ADR {plan["adr20"]:.2f}%'
            f' · {H.escape(plan["grade"])} · 仓位上限 {plan["position_pct"]:.1f}%</span>')


def _section(key, label, d, img_prefix="bogo_cn/") -> str:
    if not d or not d.get("rows"):
        return (f'<div class="sec"><h1>{H.escape(label)}</h1>'
                f'<div class="sub">暂无数据</div></div>')
    rows = d["rows"]
    imgs = d.get("images", {})
    days3 = sorted({r["信号日"] for r in rows}, reverse=True)[:3]
    newest = days3[0] if days3 else ""
    detail_rows = rows   # 明细图=全清单(强+弱), 2026-08-11 用户要求
    plans = _engine_plans()
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
    for r in detail_rows:
        s_, url = _tvurl(r["代码"])
        link = f' · <a href="{url}" target="_blank">TV↗</a>' if url else ""
        blocks.append(
            f'<div class="blk"><pre><b>{H.escape(s_)}</b> {H.escape(r["中文名"])} · '
            f'{H.escape(r["主题"])}\n信号日 {H.escape(r["信号日"])} · Fit {H.escape(r["Fit"])} · '
            f'胜率 {H.escape(r["胜率"])}% · CA {H.escape(r["CA%"])}% · Pnls {H.escape(r["Pnls%"])}% · '
            f'当日 {H.escape(r["当日%"])}%{link}{_plan_line(r["代码"], plans)}</pre>'
            + (f'<img loading="lazy" src="{img_prefix}{H.escape(imgs[r["代码"]])}">'
               if r["代码"] in imgs else "") + "</div>")
    src = d.get("source") or ""
    warn = _source_warning(key, src)
    return (f'<div class="sec"><h1>{H.escape(label)}</h1>'
            f'<div class="sub">' + warn
            + f'{H.escape((d.get("title") or "")[:70])} · 来源 '
            f'{H.escape(src)} · 共 {len(rows)} 只'
            f'（强 {sum(1 for r in rows if r["信号"]=="strong")}）</div>'
            f'<table><tr><th class="l">信号</th><th class="l">代码</th>'
            f'<th class="l">名称</th><th class="l">信号日</th><th>当日%</th><th>Fit</th>'
            f'<th>胜率</th><th>CA%</th><th>Pnls%</th><th class="l">主题</th></tr>{tr}</table>'
            + (f'<h1 style="margin-top:14px;font-size:14px">全清单 · 明细图 强+弱（{len(blocks)}）</h1>'
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
            f'<div class="tabs">{"".join(btns)}'
            f'<a class="tab" href="etf.html" style="text-decoration:none">ETF涨幅榜⭱</a>'
            f'<a class="tab" href="summary.html" style="text-decoration:none">汇总⭱</a></div>'
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
