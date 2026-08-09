# -*- coding: utf-8 -*-
"""
模块12：AI 资本周期看门狗 —— AI 主题的「基本面否决权」。

数据源 capexcycle.com（SEC 8-K/10-Q/10-K + XBRL，季度频率）。
本模块只抓三个最有决策价值的比率, 存成时间序列, 跨过临界值就在看板报警:

  ① Capex/OCF        资本开支吃掉多少经营现金流。>100% = 靠外部融资扩张
  ② RPO 增速背离      (Capex增速 − RPO增速)。转正且走阔 = 资本开支跑赢订单 = 需求见顶
  ③ T1 覆盖率         未来12个月合同利润 ÷ 年化 Capex。<1× = 明年合同填不满明年建设

为什么要它: 你的「AI算力/核心芯片」「云计算」「AI电网」三个主题, 全部押在
hyperscaler 的资本开支上。这个模块告诉你那笔钱还能烧多久 —— 技术信号会滞后
好几周才反应, 基本面拐点在这里先出现。

⚠️ 季度频率 + 滞后 4-8 周, 绝不用于择时, 只用于「这条主线是否还成立」。

    python3 -m us_monitor.m12_capex            # 抓取并更新时间序列
    python3 -m us_monitor.m12_capex --show     # 只看已存数据, 不抓
"""
import json
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from . import config as C

STORE = Path(__file__).resolve().parent / ".capex_series.json"
URL = "https://capexcycle.com/"


def _find_chrome() -> str:
    """跨平台探测 Chrome/Chromium(本地 macOS / CI Linux 都能用)"""
    import shutil as _sh
    for c in ("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
              "google-chrome", "chromium-browser", "chromium",
              "/usr/bin/google-chrome", "/usr/bin/chromium"):
        if c.startswith("/") and Path(c).exists():
            return c
        w = _sh.which(c)
        if w:
            return w
    return ""


CHROME = _find_chrome()


def _fetch_html(timeout=180) -> str:
    """站点是 JS 渲染的, urllib 拿不到数据 —— 用 Chrome --dump-dom 取渲染后 DOM"""
    import subprocess
    r = subprocess.run(
        [CHROME, "--headless", "--disable-gpu", "--no-sandbox",
         "--virtual-time-budget=15000", "--dump-dom", URL],
        capture_output=True, timeout=timeout)
    return r.stdout.decode("utf-8", "ignore")


def _num(s):
    try:
        return float(str(s).replace(",", "").replace("%", "").replace("×", "").strip())
    except (ValueError, AttributeError):
        return None


def parse(html: str) -> dict:
    """从页面文本抽三组比率。页面结构变了就返回空, 由调用方标『未验证』。"""
    txt = re.sub(r"<[^>]+>", " ", html)
    txt = re.sub(r"\s+", " ", txt)
    out = {"capex_ocf": {}, "rpo_gap": {}, "t1": {}, "quarter": None}
    m = re.search(r"共同季\s*(20\d{2}Q[1-4])", txt)
    out["quarter"] = m.group(1) if m else None
    NAMES = [("ORACLE", "ORCL"), ("AMAZON", "AMZN"),
             ("GOOGLE", "GOOGL"), ("MICROSOFT", "MSFT")]

    def section(start_kw, end_kw=None, span=1400):
        i = txt.find(start_kw)
        if i < 0:
            return ""
        seg = txt[i:i + span]
        if end_kw:
            j = seg.find(end_kw)
            if j > 0:
                seg = seg[:j]
        return seg

    # ① Capex/OCF —— "ORACLE · CLOUD 2026Q2 174% $-24B ..."
    s = section("融资压力排名", "读法")
    for name, key in NAMES:
        p = re.search(rf"{name}[^0-9]{{0,30}}20\d{{2}}Q[1-4]\s+(\d{{2,3}})%", s)
        if p:
            out["capex_ocf"][key] = _num(p.group(1))

    # ② RPO 背离 —— "MICROSOFT · IC 2026Q2 $678B +81% +80% -1pp"
    s = section("背离探测", "已并入上表")
    for name, key in NAMES:
        p = re.search(rf"{name}[^$]{{0,30}}\$[\d.]+B\s+[+-][\d.]+%\s+[+-][\d.]+%\s+"
                      rf"([+-][\d.]+)pp", s)
        if p:
            out["rpo_gap"][key] = _num(p.group(1))

    # ③ T1 覆盖 —— "MICROSOFT · IC $678B $170B 41.4% $70B $116B 0.61×"
    s = section("T1 · 近端流量", "读法", span=1800) or section("近12m合同收入", "读法", 1800)
    for name, key in NAMES:
        p = re.search(rf"{name}[^×]{{0,120}}?(\d\.\d{{2}})×", s)
        if p:
            out["t1"][key] = _num(p.group(1))
    return out


def load_store() -> dict:
    if STORE.exists():
        try:
            return json.loads(STORE.read_text())
        except json.JSONDecodeError:
            pass
    return {"series": {}, "fetched": None}


def update(force=False) -> dict:
    st = load_store()
    try:
        data = parse(_fetch_html())
    except Exception as exc:
        st["error"] = f"抓取失败: {exc}"
        return st
    if not data.get("capex_ocf"):
        st["error"] = "页面结构变化, 未解析到数据（标未验证, 不沿用旧值猜测）"
        return st
    q = data["quarter"] or datetime.now(timezone.utc).strftime("%YQ?")
    st["series"][q] = {k: data[k] for k in ("capex_ocf", "rpo_gap", "t1")}
    st["fetched"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    st["latest_q"] = q
    st.pop("error", None)
    STORE.write_text(json.dumps(st, ensure_ascii=False, indent=1))
    return st


def evaluate(st: dict) -> dict:
    """跨过临界值就报警。返回 {alerts, rows, quarter}"""
    q = st.get("latest_q")
    cur = st.get("series", {}).get(q, {}) if q else {}
    alerts, rows = [], []

    for tk, v in sorted(cur.get("capex_ocf", {}).items(), key=lambda x: -x[1]):
        breach = v > C.CAPEX_OCF_ALERT
        rows.append(("Capex/OCF", tk, f"{v:.0f}%", f"≤{C.CAPEX_OCF_ALERT}%", not breach,
                     "资本开支已超经营现金流, 靠债务/融资租赁/客户预付扩张" if breach
                     else "自身现金流撑得住"))
        if breach:
            alerts.append(f"🔴 {tk} Capex/OCF {v:.0f}% > {C.CAPEX_OCF_ALERT}% — 外部融资依赖")

    for tk, v in sorted(cur.get("rpo_gap", {}).items(), key=lambda x: -x[1]):
        breach = v > C.RPO_GAP_ALERT
        rows.append(("RPO背离", tk, f"{v:+.0f}pp", f"≤{C.RPO_GAP_ALERT}pp", not breach,
                     "🚨 资本开支跑赢订单 = 需求侧见顶信号" if breach
                     else "订单增速仍跑赢 capex, 需求未见顶"))
        if breach:
            alerts.append(f"🚨 {tk} RPO背离 {v:+.0f}pp — 资本开支跑赢订单, 需求见顶预警")

    for tk, v in sorted(cur.get("t1", {}).items()):
        breach = v < C.T1_COVER_ALERT
        rows.append(("T1覆盖", tk, f"{v:.2f}×", f"≥{C.T1_COVER_ALERT}×", not breach,
                     "明年合同利润填不满明年建设, 缺口靠未签约的按需消费补" if breach
                     else "合同利润覆盖建设承诺"))
        if breach and v < C.T1_COVER_CRIT:
            alerts.append(f"🔴 {tk} T1覆盖 {v:.2f}× < {C.T1_COVER_CRIT}× — 覆盖严重不足")
    return {"quarter": q, "rows": rows, "alerts": alerts,
            "fetched": st.get("fetched"), "error": st.get("error")}


def run(refresh=True) -> dict:
    st = update() if refresh else load_store()
    ev = evaluate(st)
    print("=" * 96)
    print(f"【AI 资本周期看门狗】数据源 capexcycle.com (SEC/XBRL, 季度) · "
          f"最新季 {ev['quarter'] or '—'} · 抓取 {ev['fetched'] or '—'}")
    if ev.get("error"):
        print(f"⚠️ 未验证: {ev['error']}")
        print("=" * 96)
        return ev
    print(f"{'指标':<10}{'公司':<8}{'当前值':>8}  {'临界值':<8}{'判定':<6} 含义")
    for metric, tk, val, thr, ok, why in ev["rows"]:
        print(f"{metric:<10}{tk:<8}{val:>8}  {thr:<8}{'✅正常' if ok else '❌越线':<6} {why}")
    print("-" * 96)
    if ev["alerts"]:
        print("【报警】")
        for a in ev["alerts"]:
            print(f"  {a}")
        print("👉 这些是【季度基本面】信号, 滞后 4-8 周, 不做择时。")
        print("   用途: AI 主题(算力/云计算/AI电网)的主线是否还成立 —— 越线越多, "
              "AI 资本开支故事的持续性越可疑。")
    else:
        print("✅ 无指标越线, AI 资本开支主线暂无基本面否决信号")
    print("=" * 96)
    return ev


if __name__ == "__main__":
    run(refresh="--show" not in sys.argv)
