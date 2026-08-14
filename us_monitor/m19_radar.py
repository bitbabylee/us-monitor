# -*- coding: utf-8 -*-
"""模块19：全量 ETF 涨幅雷达。

主排序回答一个问题：过去 5/21/63 个交易日，哪些 ETF 涨得最多且不是只靠
单日脉冲。主题、产业故事与 K 线触发均不进入主分，只作为解释与后续执行层信息。

评分 = 5日涨幅百分位×25% + 21日×40% + 63日×25%
       + 近21日上涨天数占比百分位×10%。

页面始终保留完整配置宇宙；AUM 与 21 日平均成交额只作为交易准入门槛，
不参与涨幅评分。数据缺失的 ETF 也显示，不再因未进 Top N 而消失。
"""
from __future__ import annotations

import html as H
import json
import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

import pandas as pd
import yfinance as yf

from . import config as C
from .data import NY, col

_LAST_RESULT: dict | None = None
TV_LIST_FILENAME = "etf_top22_tv.txt"
TV_SYMBOLS_FILENAME = "etf_top22_symbols.txt"
TV_LIST_TIERS = ("领涨", "强势", "改善")
TV_LIST_LIQUIDITY = ("通过", "谨慎")
TV_LIST_LIMIT = 22
META_CACHE = Path(__file__).resolve().parent / ".etf_meta_cache.json"


def universe() -> dict[str, dict[str, str]]:
    """返回完整 ETF 配置宇宙；分组只用于筛选，不参与评分。"""
    group_by = {
        tk: group for group, tickers in C.RADAR_GROUPS.items() for tk in tickers
    }
    out = {
        C.BENCHMARK: {"name": "标普500", "group": "宽基/风格/宏观"},
    }
    for tk, name in C.SECTORS.items():
        out[tk] = {"name": name, "group": "标普行业"}
    for tk, name in C.RADAR_ETFS.items():
        out[tk] = {"name": name, "group": group_by.get(tk, "其他")}
    return out


def _from_daily(daily, tickers) -> dict[str, pd.DataFrame]:
    frames = {}
    if daily is None:
        return frames
    for tk in tickers:
        fields = {}
        for field in ("Close", "High", "Low", "Volume"):
            try:
                s = col(daily, field, tk).dropna()
                if len(s):
                    fields[field] = s
            except Exception:
                pass
        if "Close" in fields and len(fields["Close"]) >= max(C.ETF_RETURN_WINDOWS) + 2:
            frames[tk] = pd.concat(fields, axis=1).dropna(subset=["Close"])
    return frames


def _download(tickers) -> dict[str, pd.DataFrame]:
    if not tickers:
        return {}
    try:
        df = yf.download(
            list(tickers), period="14mo", interval="1d", auto_adjust=True,
            progress=False, group_by="column", threads=True,
        )
    except Exception as exc:
        print(f"WARN: ETF 行情下载失败: {exc}")
        return {}
    out = {}
    for tk in tickers:
        fields = {}
        for field in ("Close", "High", "Low", "Volume"):
            try:
                s = df[field][tk].dropna() if isinstance(df.columns, pd.MultiIndex) else df[field].dropna()
                if len(s):
                    fields[field] = s
            except (KeyError, TypeError):
                pass
        if "Close" in fields and len(fields["Close"]) >= max(C.ETF_RETURN_WINDOWS) + 2:
            out[tk] = pd.concat(fields, axis=1).dropna(subset=["Close"])
    return out


def _load(daily=None) -> dict[str, pd.DataFrame]:
    tickers = list(universe())
    frames = _from_daily(daily, tickers)
    missing = [tk for tk in tickers if tk not in frames]
    frames.update(_download(missing))
    return frames


def _fetch_aum(tk: str) -> float | None:
    """取 ETF 基金总资产；失败只影响该字段，不中断看板。"""
    try:
        value = (yf.Ticker(tk).get_info() or {}).get("totalAssets")
        value = _finite(value)
        return value if value is not None and value > 0 else None
    except Exception:
        return None


def _load_aum(tickers, force: bool = False) -> dict[str, float | None]:
    """每天并发刷新一次 AUM；接口抖动时保留上次成功值。"""
    today = datetime.now(NY).date().isoformat()
    cached: dict = {}
    if META_CACHE.exists():
        try:
            cached = json.loads(META_CACHE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            cached = {}
    old = cached.get("aum", {}) if isinstance(cached.get("aum", {}), dict) else {}
    if not force and cached.get("fetched") == today and set(tickers) <= set(old):
        return {tk: _finite(old.get(tk)) for tk in tickers}

    fresh = {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(_fetch_aum, tk): tk for tk in tickers}
        for future in as_completed(futures):
            tk = futures[future]
            value = future.result()
            if value is not None:
                fresh[tk] = value
    merged = {tk: fresh.get(tk, _finite(old.get(tk))) for tk in tickers}
    try:
        META_CACHE.write_text(
            json.dumps({"fetched": today, "aum": merged}, ensure_ascii=False, indent=1),
            encoding="utf-8",
        )
    except OSError as exc:
        print(f"WARN: ETF AUM 缓存写入失败: {exc}")
    print(f"ETF AUM: 本次取得 {len(fresh)}/{len(tickers)}，页面可用 {sum(v is not None for v in merged.values())}/{len(tickers)}")
    return merged


def _ret(s: pd.Series, n: int) -> float | None:
    if len(s) <= n or not s.iloc[-n - 1]:
        return None
    return (s.iloc[-1] / s.iloc[-n - 1] - 1) * 100


def _finite(v):
    return float(v) if v is not None and math.isfinite(float(v)) else None


def liquidity_status(aum: float | None,
                     avg_dollar_volume21: float | None) -> tuple[str, str]:
    """将规模和成交额转成交易准入标签；不改变涨幅评分。"""
    aum = _finite(aum)
    avg_dollar_volume21 = _finite(avg_dollar_volume21)
    if aum is None or avg_dollar_volume21 is None:
        missing = []
        if aum is None:
            missing.append("AUM")
        if avg_dollar_volume21 is None:
            missing.append("21日均成交额")
        return "数据缺失", f"缺少{'、'.join(missing)}，暂不进入交易短名单"

    excluded = []
    if aum < C.ETF_AUM_MIN_USD:
        excluded.append("AUM低于$3亿")
    if avg_dollar_volume21 < C.ETF_DOLLAR_VOLUME_MIN_USD:
        excluded.append("21日均成交额低于$200万")
    if excluded:
        return "排除", "；".join(excluded) + "，仅保留在完整列表"
    if avg_dollar_volume21 < C.ETF_DOLLAR_VOLUME_CAUTION_USD:
        return "谨慎", "21日均成交额低于$500万，宜限价并缩小仓位"
    return "通过", "AUM与21日平均成交额均通过交易门槛"


def _raw_row(tk: str, meta: dict, frame: pd.DataFrame | None,
             benchmark: pd.DataFrame | None, aum: float | None = None) -> dict:
    base = {
        "tk": tk, "name": meta["name"], "group": meta["group"],
        "date": None, "score": None, "rank": None, "tier": "数据缺失",
        "trend": "—", "position": "—", "why": "没有取得足够的已完结日线数据",
        "risk": "数据缺失，不能比较涨幅", "aum": _finite(aum),
        "volume": None, "avg_volume21": None, "avg_dollar_volume21": None,
        "volume_ratio": None, "liquidity": "数据缺失",
        "liquidity_reason": "缺少有效行情，暂不进入交易短名单", "missing": True,
    }
    if frame is None or len(frame.get("Close", [])) < max(C.ETF_RETURN_WINDOWS) + 2:
        return base

    s = frame["Close"].dropna()
    b = benchmark["Close"].dropna() if benchmark is not None else None
    rets = {n: _ret(s, n) for n in C.ETF_RETURN_WINDOWS}
    b_rets = {n: _ret(b, n) if b is not None else None for n in C.ETF_RETURN_WINDOWS}
    daily_ret = s.pct_change().dropna()
    consistency = (daily_ret.tail(21) > 0).mean() * 100
    ma20 = s.tail(20).mean()
    ma50 = s.tail(50).mean()
    ma200 = s.tail(200).mean() if len(s) >= 200 else None
    px = s.iloc[-1]

    if px > ma20 > ma50 and (ma200 is None or ma50 > ma200):
        trend = "多头"
    elif px > ma20 and rets[5] is not None and rets[5] > 0:
        trend = "转强"
    elif px > ma50:
        trend = "整理"
    else:
        trend = "弱势"

    pivot = s.iloc[-21:-1].max()
    ext20 = (px / pivot - 1) * 100 if pivot else None
    adr20 = None
    if "High" in frame and "Low" in frame:
        hl = pd.concat([frame["High"], frame["Low"]], axis=1).dropna().tail(20)
        if len(hl):
            adr20 = ((hl.iloc[:, 0] / hl.iloc[:, 1] - 1) * 100).mean()
    chase_line = max(5.0, (adr20 or 0) * C.ETF_CHASE_ADR_MULT)
    if ext20 is not None and ext20 > chase_line:
        position = "追高区"
    elif ext20 is not None and ext20 >= -2:
        position = "近20日高"
    else:
        position = "回撤中"

    rs = {
        n: rets[n] - b_rets[n]
        if rets[n] is not None and b_rets[n] is not None else None
        for n in C.ETF_RETURN_WINDOWS
    }
    rs21, rs63 = rs[21], rs[63]
    quad = ("领" if rs21 is not None and rs63 is not None and rs21 > 0 and rs63 > 0
            else "改" if rs21 is not None and rs21 > 0
            else "弱" if rs63 is not None and rs63 > 0 else "落")

    chg = daily_ret.iloc[-1] * 100 if len(daily_ret) else None
    sd = daily_ret.tail(C.RADAR_Z_WIN).std() * 100 if len(daily_ret) else None
    z = chg / sd if sd and math.isfinite(sd) else None
    stale = b is not None and len(b) and s.index[-1] != b.index[-1]
    volume = avg_volume21 = avg_dollar_volume21 = volume_ratio = None
    if "Volume" in frame:
        volumes = frame["Volume"].dropna()
        if len(volumes):
            volume = _finite(volumes.iloc[-1])
            avg_volume21 = _finite(volumes.tail(21).mean())
            if avg_volume21:
                volume_ratio = _finite(volume / avg_volume21)
        dollar_values = pd.concat([frame["Close"], frame["Volume"]], axis=1).dropna()
        if len(dollar_values):
            avg_dollar_volume21 = _finite(
                (dollar_values.iloc[:, 0] * dollar_values.iloc[:, 1]).tail(21).mean()
            )
    liquidity, liquidity_reason = liquidity_status(aum, avg_dollar_volume21)

    base.update({
        "date": str(s.index[-1].date()), "price": _finite(px),
        "r5": _finite(rets[5]), "r21": _finite(rets[21]), "r63": _finite(rets[63]),
        "rs5": _finite(rs[5]), "rs21": _finite(rs[21]), "rs63": _finite(rs[63]),
        "consistency": _finite(consistency), "ma20": _finite(ma20),
        "ma50": _finite(ma50), "ma200": _finite(ma200), "adr20": _finite(adr20),
        "ext20": _finite(ext20), "chg": _finite(chg), "z": _finite(z),
        "aum": _finite(aum), "volume": volume, "avg_volume21": avg_volume21,
        "avg_dollar_volume21": avg_dollar_volume21, "volume_ratio": volume_ratio,
        "liquidity": liquidity, "liquidity_reason": liquidity_reason,
        "quad": quad, "trend": trend, "position": position,
        "stale": stale, "missing": False,
    })
    return base


def analyze_frames(frames: dict[str, pd.DataFrame], metas: dict | None = None,
                   aum: dict[str, float | None] | None = None) -> dict:
    """纯计算入口，供生产与合成数据测试共同使用。"""
    metas = metas or universe()
    aum = aum or {}
    benchmark = frames.get(C.BENCHMARK)
    rows = [_raw_row(tk, meta, frames.get(tk), benchmark, aum.get(tk))
            for tk, meta in metas.items()]
    valid = [r for r in rows if not r["missing"]]
    if valid:
        df = pd.DataFrame(valid).set_index("tk")
        pct = {}
        for key in ("r5", "r21", "r63", "consistency"):
            pct[key] = df[key].rank(pct=True, method="average") * 100
        for r in valid:
            tk = r["tk"]
            r["score"] = _finite(
                pct["r5"].loc[tk] * C.ETF_SCORE_WEIGHTS[5]
                + pct["r21"].loc[tk] * C.ETF_SCORE_WEIGHTS[21]
                + pct["r63"].loc[tk] * C.ETF_SCORE_WEIGHTS[63]
                + pct["consistency"].loc[tk] * C.ETF_SCORE_WEIGHTS["consistency"]
            )
        ranked = sorted(valid, key=lambda r: (-(r["score"] or -1), r["tk"]))
        for i, r in enumerate(ranked, 1):
            r["rank"] = i
            if (r["score"] >= C.ETF_TIER_LEADER and r["r21"] > 0 and r["r63"] > 0):
                r["tier"] = "领涨"
            elif r["score"] >= C.ETF_TIER_STRONG and r["r21"] > 0:
                r["tier"] = "强势"
            elif r["r5"] > 0 and (r["rs5"] is None or r["rs5"] > 0):
                r["tier"] = "改善"
            else:
                r["tier"] = "观察"
            r["why"] = (
                f"5/21/63日涨幅 {r['r5']:+.1f}% / {r['r21']:+.1f}% / {r['r63']:+.1f}%；"
                f"近21日上涨天数 {r['consistency']:.0f}%；{r['trend']}"
            )
            risks = []
            if r["position"] == "追高区":
                risks.append(f"距20日枢轴已延伸 {r['ext20']:+.1f}%")
            if r["r63"] < 0:
                risks.append("63日累计涨幅仍为负")
            if r["trend"] == "弱势":
                risks.append("价格仍在50日均线下")
            if r["consistency"] < 45:
                risks.append("上涨日占比偏低，涨幅可能集中在少数交易日")
            r["risk"] = "；".join(risks) or "未见明显追高或趋势破坏，但排名不等于买点"
    rows.sort(key=lambda r: (r["rank"] is None, r["rank"] or 10**9, r["tk"]))
    dates = [r["date"] for r in rows if r["date"]]
    return {
        "rows": rows,
        "date": max(dates) if dates else "数据缺失",
        "total": len(rows),
        "valid": len(valid),
        "missing": len(rows) - len(valid),
    }


def run(daily=None) -> dict:
    global _LAST_RESULT
    frames = _load(daily)
    result = analyze_frames(frames, aum=_load_aum(list(universe())))
    rows = [r for r in result["rows"] if not r["missing"]]
    leaders = rows[:C.RADAR_TOP_N]
    improving = [r for r in rows if r["tier"] == "改善"][:6]
    cnt = {tier: sum(1 for r in rows if r["tier"] == tier)
           for tier in ("领涨", "强势", "改善", "观察")}

    print("=" * 96)
    print(f"【全量 ETF 涨幅雷达】{result['valid']}/{result['total']} 只有效数据 · 数据日 {result['date']}")
    print("  评分: 5日涨幅25% + 21日40% + 63日25% + 21日上涨天数占比10%（均为横截面百分位）")
    print(f"  分层: 领涨{cnt['领涨']} 强势{cnt['强势']} 改善{cnt['改善']} 观察{cnt['观察']}")
    if leaders:
        print("  涨幅优先: " + " · ".join(
            f"{r['name']}({r['tk']}) 分{r['score']:.0f}/21日{r['r21']:+.1f}%" for r in leaders))
    if improving:
        print("  短线改善: " + " · ".join(
            f"{r['name']}({r['tk']}) 5日{r['r5']:+.1f}%" for r in improving))
    print("=" * 96)

    from . import tv
    lines = ["  涨幅优先: " + "  ".join(f"{tv.symbol(r['tk'])} {r['name']}" for r in leaders)]
    if improving:
        lines.append("  短线改善: " + "  ".join(
            f"{tv.symbol(r['tk'])} {r['name']}" for r in improving[:5]))
    result.update({"lines": lines, "improving": improving})
    _LAST_RESULT = result
    return result


def _fmt(v, digits=1, sign=False):
    if v is None:
        return "—"
    return f"{v:+.{digits}f}" if sign else f"{v:.{digits}f}"


def _fmt_amount(v, currency=False):
    """用中文数量级压缩 AUM/成交量，保留完整值在 title 中。"""
    if v is None:
        return "—"
    value = float(v)
    prefix = "$" if currency else ""
    if abs(value) >= 1e12:
        return f"{prefix}{value / 1e12:.2f}万亿"
    if abs(value) >= 1e8:
        return f"{prefix}{value / 1e8:.1f}亿"
    if abs(value) >= 1e4:
        return f"{prefix}{value / 1e4:.1f}万"
    return f"{prefix}{value:,.0f}"


def tv_import_list(result: dict, limit: int = TV_LIST_LIMIT) -> tuple[str, list[dict]]:
    """生成 TV watchlist：按涨幅排名筛层级，再用流动性门槛做交易准入。"""
    eligible = [r for r in result["rows"]
                if r.get("tier") in TV_LIST_TIERS
                and r.get("liquidity") in TV_LIST_LIQUIDITY]
    selected = eligible[:limit]
    from . import tv
    parts = []
    for tier in TV_LIST_TIERS:
        symbols = [tv.symbol(r["tk"]) for r in selected if r["tier"] == tier]
        if symbols:
            parts.append(",".join([f"###{tier}"] + symbols))
    return ",".join(parts), selected


def tv_symbol_list(selected: list[dict]) -> str:
    """无分组的纯 `市场:TICKER` 逗号串，便于复制到其他扫描器。"""
    from . import tv
    return ",".join(tv.symbol(r["tk"]) for r in selected)


def _row_html(r: dict, i: int) -> str:
    score = _fmt(r.get("score"), 1)
    rank = r.get("rank") or "—"
    cls = {"领涨": "lead", "强势": "strong", "改善": "improve",
           "观察": "watch", "数据缺失": "missing"}.get(r["tier"], "watch")
    liquidity_cls = {"通过": "pass", "谨慎": "caution", "排除": "excluded",
                     "数据缺失": "missing"}.get(r.get("liquidity"), "missing")
    search = H.escape(f"{r['tk']} {r['name']} {r['group']}".lower(), quote=True)
    attrs = (
        f'data-search="{search}" data-group="{H.escape(r["group"], quote=True)}" '
        f'data-tier="{H.escape(r["tier"], quote=True)}" '
        f'data-liquidity="{H.escape(r.get("liquidity", "数据缺失"), quote=True)}" '
        f'data-score="{r.get("score") if r.get("score") is not None else -999}" '
        f'data-r5="{r.get("r5") if r.get("r5") is not None else -999}" '
        f'data-r21="{r.get("r21") if r.get("r21") is not None else -999}" '
        f'data-r63="{r.get("r63") if r.get("r63") is not None else -999}" '
        f'data-aum="{r.get("aum") if r.get("aum") is not None else -1}" '
        f'data-volume="{r.get("volume") if r.get("volume") is not None else -1}" '
        f'data-dollar-volume="{r.get("avg_dollar_volume21") if r.get("avg_dollar_volume21") is not None else -1}" '
        f'data-name="{H.escape(r["tk"], quote=True)}"'
    )
    aum_title = (f' title="基金总资产 ${r["aum"]:,.0f}"'
                 if r.get("aum") is not None else "")
    dollar_volume_title = (f' title="21日平均成交额 ${r["avg_dollar_volume21"]:,.0f}"'
                           if r.get("avg_dollar_volume21") is not None else "")
    return (
        f'<tr {attrs}><td>{rank}</td>'
        f'<td class="l"><button class="open" data-i="{i}" data-ticker="{H.escape(r["tk"])}">'
        f'{H.escape(r["tk"])}</button></td>'
        f'<td class="l name">{H.escape(r["name"])}</td>'
        f'<td class="l"><span class="group">{H.escape(r["group"])}</span></td>'
        f'<td class="l"><span class="tier {cls}">{H.escape(r["tier"])}</span></td>'
        f'<td{aum_title}>{_fmt_amount(r.get("aum"), currency=True)}</td>'
        f'<td{dollar_volume_title}>{_fmt_amount(r.get("avg_dollar_volume21"), currency=True)}</td>'
        f'<td class="l"><span class="tier {liquidity_cls}" title="{H.escape(r.get("liquidity_reason", ""), quote=True)}">{H.escape(r.get("liquidity", "数据缺失"))}</span></td>'
        f'<td><b>{score}</b></td><td>{_fmt(r.get("r5"), 1, True)}%</td>'
        f'<td>{_fmt(r.get("r21"), 1, True)}%</td><td>{_fmt(r.get("r63"), 1, True)}%</td>'
        f'<td>{_fmt(r.get("consistency"), 0)}%</td>'
        f'<td class="l">{H.escape(r["trend"])}</td><td class="l">{H.escape(r["position"])}</td></tr>'
    )


def build_page(result: dict | None = None) -> Path:
    """生成完整、可筛选并可点击查看详情的静态 ETF 页面。"""
    from .m6_dashboard import OUT_DIR
    from . import tv

    result = result or _LAST_RESULT or run()
    rows = result["rows"]
    tv_list, tv_selected = tv_import_list(result)
    tv_symbols = tv_symbol_list(tv_selected)
    tv_list_path = OUT_DIR / TV_LIST_FILENAME
    tv_list_path.write_text(tv_list + "\n", encoding="utf-8")
    tv_symbols_path = OUT_DIR / TV_SYMBOLS_FILENAME
    tv_symbols_path.write_text(tv_symbols + "\n", encoding="utf-8")
    groups = sorted({r["group"] for r in rows})
    group_options = "".join(f'<option>{H.escape(g)}</option>' for g in groups)
    trs = "".join(_row_html(r, i) for i, r in enumerate(rows))
    payload = json.dumps(rows, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    tv_urls = json.dumps({r["tk"]: tv.url(r["tk"]) for r in rows}, ensure_ascii=False)
    tv_list_json = json.dumps(tv_list, ensure_ascii=False)
    tv_symbols_json = json.dumps(tv_symbols, ensure_ascii=False)
    xbi = next((r for r in rows if r["tk"] == "XBI"), None)
    xbi_note = (f'XBI 当前第 {xbi["rank"]} 名、21日涨幅 {_fmt(xbi.get("r21"), 1, True)}%；'
                f'无论是否进入领涨层，都保留在全表。' if xbi and not xbi["missing"]
                else "XBI 已纳入完整宇宙；当前数据缺失时也不会被隐藏。")

    css = """
:root{color-scheme:light dark;--ink:#111;--ink2:#555;--mut:#7b7b76;--bd:#8883;
--good:#087d36;--amber:#a86400;--bad:#b42318;--bg:#fcfcfb;--sf:#fff;--soft:#f3f3ef}
@media(prefers-color-scheme:dark){:root{--ink:#e8e6dd;--ink2:#b5b3a8;--mut:#99978f;
--good:#62d18b;--amber:#f2b85b;--bad:#ff8b82;--bg:#111110;--sf:#1a1a19;--soft:#232321}}
*{box-sizing:border-box}body{margin:0 auto;padding:14px 12px 40px;max-width:1180px;background:var(--bg);
color:var(--ink);font:13px/1.5 -apple-system,"PingFang SC",sans-serif}a{color:inherit}
h1{font-size:20px;margin:4px 0}.sub{color:var(--ink2);font-size:12px}.nav{position:sticky;top:0;z-index:5;
display:flex;gap:6px;flex-wrap:wrap;padding:8px 0;background:var(--bg)}.nav a{padding:5px 11px;border:1px solid var(--bd);
border-radius:999px;text-decoration:none;background:var(--sf)}.nav a.on{background:var(--ink);color:var(--bg)}
.logic{margin:12px 0;padding:12px;background:var(--sf);border:1px solid var(--bd);border-radius:10px}
.formula{font-weight:700;font-variant-numeric:tabular-nums}.logic-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-top:10px}
.logic-grid div{padding:8px;background:var(--soft);border-radius:7px}.logic-grid b{display:block;font-size:15px}.note{margin-top:8px;color:var(--ink2)}
.tv-actions{display:flex;gap:7px;flex-wrap:wrap;margin-top:10px}.tv-actions a,.tv-actions button{padding:7px 10px;border:1px solid var(--bd);
border-radius:7px;background:var(--sf);color:var(--ink);font:inherit;text-decoration:none;cursor:pointer}.tv-actions .primary{background:var(--ink);color:var(--bg);border-color:var(--ink)}
.symbols{margin-top:9px}.symbols summary{cursor:pointer;color:var(--ink2)}.symbols textarea{width:100%;min-height:68px;margin-top:7px;padding:8px;
border:1px solid var(--bd);border-radius:7px;background:var(--soft);color:var(--ink);font:12px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace;resize:vertical}
.filters{display:grid;grid-template-columns:minmax(180px,2fr) repeat(4,minmax(115px,1fr));gap:8px;margin:14px 0 8px}
label{font-size:11px;color:var(--mut)}input,select{display:block;width:100%;margin-top:3px;padding:8px 9px;border:1px solid var(--bd);
border-radius:7px;background:var(--sf);color:var(--ink);font:inherit}.count{margin:5px 0;color:var(--ink2)}
.wrap{overflow:auto;border:1px solid var(--bd);border-radius:9px;background:var(--sf)}table{border-collapse:collapse;width:100%;min-width:1080px;
font-size:12px;font-variant-numeric:tabular-nums}th,td{border-bottom:1px solid var(--bd);padding:6px 7px;text-align:right;white-space:nowrap}
th{position:sticky;top:0;background:var(--soft);z-index:1;color:var(--ink2)}th.l,td.l{text-align:left}tbody tr:hover{background:#0ca30c0c}
.open{border:0;background:none;color:var(--ink);font:inherit;font-weight:800;padding:3px 6px;margin:-3px -6px;cursor:pointer;text-decoration:underline;
text-decoration-style:dotted;text-underline-offset:3px}.open:focus-visible{outline:2px solid var(--good);border-radius:4px}.name{max-width:190px;overflow:hidden;text-overflow:ellipsis}
.tier,.group{display:inline-block;padding:1px 6px;border-radius:999px;border:1px solid var(--bd)}.lead{color:var(--good);border-color:var(--good)}
.strong,.pass{color:var(--good)}.improve,.caution{color:var(--amber);border-color:var(--amber)}.watch{color:var(--mut)}.missing,.excluded{color:var(--bad);border-color:var(--bad)}
.empty{display:none;padding:24px;text-align:center;color:var(--mut)}dialog{width:min(680px,calc(100vw - 24px));max-height:88vh;border:1px solid var(--bd);
border-radius:12px;background:var(--sf);color:var(--ink);padding:0;box-shadow:0 20px 70px #0005}dialog::backdrop{background:#0008}.detail{padding:16px}
.detail-head{display:flex;align-items:flex-start;justify-content:space-between;gap:12px}.detail h2{margin:0;font-size:22px}.close{border:1px solid var(--bd);
border-radius:999px;background:var(--soft);color:var(--ink);width:34px;height:34px;cursor:pointer}.metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:7px;margin:14px 0}
.metric{padding:9px;background:var(--soft);border-radius:8px}.metric small{display:block;color:var(--mut)}.metric b{font-size:17px}.detail section{margin:13px 0}
.detail section b{display:block;margin-bottom:3px}.actions{display:flex;gap:8px;flex-wrap:wrap}.actions a{padding:7px 10px;border:1px solid var(--bd);border-radius:7px;text-decoration:none}
.disclaimer{margin-top:14px;padding-top:10px;border-top:1px solid var(--bd);color:var(--mut);font-size:11px}
@media(max-width:720px){.logic-grid,.metrics{grid-template-columns:repeat(2,1fr)}.filters{grid-template-columns:1fr 1fr}.filters label:first-child{grid-column:1/-1}}
@media(max-width:430px){.filters{grid-template-columns:1fr}.filters label:first-child{grid-column:auto}.logic-grid{grid-template-columns:1fr 1fr}}
@media(prefers-reduced-motion:reduce){*{scroll-behavior:auto!important}}
"""
    js = """
<script>
const DATA=__DATA__, TV=__TV__, TVLIST=__TVLIST__, TVSYMBOLS=__TVSYMBOLS__, body=document.getElementById('rows'), all=[...body.rows];
const q=document.getElementById('q'), group=document.getElementById('group'), tier=document.getElementById('tier'), liquidity=document.getElementById('liquidity'), sort=document.getElementById('sort');
const count=document.getElementById('count'), empty=document.getElementById('empty'), dlg=document.getElementById('detail'), box=document.getElementById('detailBox');
const esc=s=>String(s??'—').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const pct=(v,d=1)=>v==null?'—':`${v>=0?'+':''}${Number(v).toFixed(d)}%`;
const num=(v,d=1)=>v==null?'—':Number(v).toFixed(d);
const amount=(v,currency=false)=>{if(v==null)return '—';const n=Number(v),p=currency?'$':'';if(Math.abs(n)>=1e12)return `${p}${(n/1e12).toFixed(2)}万亿`;if(Math.abs(n)>=1e8)return `${p}${(n/1e8).toFixed(1)}亿`;if(Math.abs(n)>=1e4)return `${p}${(n/1e4).toFixed(1)}万`;return `${p}${n.toLocaleString('zh-CN',{maximumFractionDigits:0})}`};
function apply(){
  const needle=q.value.trim().toLowerCase();
  let shown=all.filter(tr=>(!needle||tr.dataset.search.includes(needle))&&(!group.value||tr.dataset.group===group.value)&&(!tier.value||tr.dataset.tier===tier.value)&&(!liquidity.value||tr.dataset.liquidity===liquidity.value));
  const key=sort.value;
  shown.sort((a,b)=>key==='name'?a.dataset.name.localeCompare(b.dataset.name):Number(b.dataset[key])-Number(a.dataset[key]));
  all.forEach(tr=>tr.remove()); shown.forEach(tr=>body.appendChild(tr));
  count.textContent=`显示 ${shown.length} / ${all.length} 只`; empty.style.display=shown.length?'none':'block';
}
[q,group,tier,liquidity,sort].forEach(x=>x.addEventListener(x===q?'input':'change',apply));
function metric(label,value){return `<div class="metric"><small>${label}</small><b>${value}</b></div>`}
function openETF(i,updateHash=true){
  const r=DATA[i], status=r.missing?'数据缺失':`${r.tier} · 总榜第 ${r.rank}`;
  box.innerHTML=`<div class="detail-head"><div><h2>${esc(r.tk)} · ${esc(r.name)}</h2><div class="sub">${esc(r.group)} · ${esc(status)} · 数据日 ${esc(r.date)}</div></div><button class="close" aria-label="关闭">×</button></div>
  <div class="metrics">${metric('基金规模 AUM',amount(r.aum,true))}${metric('21日均成交额',amount(r.avg_dollar_volume21,true))}${metric('流动性准入',esc(r.liquidity))}${metric('最新成交量',amount(r.volume))}${metric('涨幅评分',num(r.score))}${metric('5日涨幅',pct(r.r5))}${metric('21日涨幅',pct(r.r21))}${metric('63日涨幅',pct(r.r63))}</div>
  <section><b>流动性判断</b>${esc(r.liquidity_reason)}</section>
  <section><b>为什么排在这里</b>${esc(r.why)}</section>
  <section><b>相对 SPY</b>5 / 21 / 63 日：${pct(r.rs5)} / ${pct(r.rs21)} / ${pct(r.rs63)} · 象限 ${esc(r.quad)}</section>
  <section><b>趋势与位置</b>${esc(r.trend)} · ${esc(r.position)} · 21日上涨天数 ${pct(r.consistency,0)} · ADR20 ${pct(r.adr20)} · 距20日枢轴 ${pct(r.ext20)}</section>
  <section><b>主要风险</b>${esc(r.risk)}</section>
  <section><b>评分口径</b>5日涨幅百分位×25% + 21日×40% + 63日×25% + 近21日上涨天数占比百分位×10%。主题不参与评分。</section>
  <div class="actions"><a href="${esc(TV[r.tk])}" target="_blank" rel="noopener">TradingView 图表 ↗</a></div>
  <div class="disclaimer">排名只表示历史涨幅与持续性，不等于现在是买点；进场仍应交给 Setup → Trigger → Plan 执行层。</div>`;
  box.querySelector('.close').onclick=()=>dlg.close(); dlg.showModal();
  if(updateHash)history.replaceState(null,'','#'+r.tk);
}
body.addEventListener('click',e=>{const b=e.target.closest('.open');if(b)openETF(Number(b.dataset.i))});
dlg.addEventListener('close',()=>{if(location.hash)history.replaceState(null,'',location.pathname+location.search)});
apply();
function openHash(){if(!location.hash||dlg.open)return;const tk=decodeURIComponent(location.hash.slice(1)).toUpperCase(),i=DATA.findIndex(r=>r.tk===tk);if(i>=0)openETF(i,false)}
window.addEventListener('hashchange',openHash);openHash();
async function copyText(text,b){
  const old=b.textContent;
  try{if(navigator.clipboard&&window.isSecureContext)await navigator.clipboard.writeText(text);else{
    const ta=document.createElement('textarea');ta.value=text;ta.style.position='fixed';ta.style.opacity='0';document.body.appendChild(ta);ta.select();
    if(!document.execCommand('copy'))throw new Error('copy failed');ta.remove();}
    b.textContent='已复制';setTimeout(()=>b.textContent=old,1600);
  }catch(_){b.textContent='请用下载文件';setTimeout(()=>b.textContent=old,1600)}
}
document.getElementById('copyTv').addEventListener('click',e=>copyText(TVLIST,e.currentTarget));
document.getElementById('copySymbols').addEventListener('click',e=>copyText(TVSYMBOLS,e.currentTarget));
</script>
""".replace("__DATA__", payload).replace("__TV__", tv_urls).replace("__TVLIST__", tv_list_json).replace("__TVSYMBOLS__", tv_symbols_json)

    page = (
        '<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<title>全量 ETF 涨幅榜</title><style>{css}</style>'
        '<div class="nav"><a href="bogo.html">波哥信号</a><a class="on" href="etf.html">ETF涨幅榜</a>'
        '<a href="summary.html">历史汇总</a></div>'
        '<h1>全量 ETF 涨幅榜</h1>'
        f'<div class="sub">{result["total"]} 只配置 ETF · {result["valid"]} 只有效数据 · 数据日 {H.escape(result["date"])} · 点击代码查看详情</div>'
        '<div class="logic"><div class="formula">涨幅评分 = 5日涨幅百分位×25% + 21日×40% + 63日×25% + 持续性×10%</div>'
        '<div class="logic-grid"><div><b>21日 40%</b>主趋势，权重最高</div><div><b>5日 25%</b>近期加速或转弱</div>'
        '<div><b>63日 25%</b>中期累计涨幅</div><div><b>持续性 10%</b>近21日上涨天数占比</div></div>'
        f'<div class="note">主题、基金规模（AUM）和成交额不参与涨幅评分。交易准入：AUM ≥ $3亿且21日均成交额 ≥ $200万；$200万-$500万标“谨慎”，低于门槛标“排除”。TV 前22会剔除不合格并按排名向后补位，完整表仍保留全部 ETF。{H.escape(xbi_note)}</div>'
        f'<div class="tv-actions"><a class="primary" href="{TV_LIST_FILENAME}" download>下载 TV 导入 List（{len(tv_selected)}只）</a>'
        '<button id="copyTv" type="button">复制分组 TV List</button>'
        f'<a href="{TV_SYMBOLS_FILENAME}" download>下载 市场:TICKER</a><button id="copySymbols" type="button">复制 市场:TICKER</button></div>'
        f'<details class="symbols"><summary>查看纯 市场:TICKER 列表</summary><textarea readonly aria-label="市场:TICKER列表">{H.escape(tv_symbols)}</textarea></details></div>'
        '<div class="filters"><label>搜索代码、名称或主题<input id="q" type="search" placeholder="例如 XBI、生物科技、能源"></label>'
        f'<label>主题<select id="group"><option value="">全部主题</option>{group_options}</select></label>'
        '<label>层级<select id="tier"><option value="">全部层级</option><option>领涨</option><option>强势</option><option>改善</option><option>观察</option><option>数据缺失</option></select></label>'
        '<label>流动性<select id="liquidity"><option value="">全部状态</option><option>通过</option><option>谨慎</option><option>排除</option><option>数据缺失</option></select></label>'
        '<label>排序<select id="sort"><option value="score">涨幅评分</option><option value="aum">基金规模 AUM</option><option value="dollarVolume">21日均成交额</option><option value="r5">5日涨幅</option><option value="r21">21日涨幅</option><option value="r63">63日涨幅</option><option value="name">代码</option></select></label></div>'
        f'<div class="count" id="count">显示 {len(rows)} / {len(rows)} 只</div><div class="wrap"><table>'
        '<thead><tr><th>排名</th><th class="l">代码</th><th class="l">名称</th><th class="l">主题</th><th class="l">层级</th>'
        '<th title="ETF 基金总资产，不是成分股总市值">规模(AUM)</th><th title="最近21个已完结交易日的平均成交额">21日均成交额</th><th class="l">流动性</th>'
        '<th>评分</th><th>5日</th><th>21日</th><th>63日</th><th>上涨日</th><th class="l">趋势</th><th class="l">位置</th></tr></thead>'
        f'<tbody id="rows">{trs}</tbody></table><div class="empty" id="empty">没有符合当前筛选的 ETF</div></div>'
        '<dialog id="detail" aria-labelledby="detailTitle"><div class="detail" id="detailBox"></div></dialog>'
        '<div class="disclaimer">仅供研究与学习，不构成投资建议。全部指标只使用已完结日线。</div>' + js
    )
    out = OUT_DIR / "etf.html"
    out.write_text(page, encoding="utf-8")
    print(f"✅ ETF 涨幅页: {result['valid']}/{result['total']} 只有效数据 · TV导入{len(tv_selected)}只 → {out}")
    return out


if __name__ == "__main__":
    build_page()
