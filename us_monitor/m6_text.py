# -*- coding: utf-8 -*-
"""
模块6b：纯文本看板 —— 姐姐原版审美: 等宽字体、等号分隔线、文字+符号, 无卡片无徽章。

各模块的终端输出本来就是按原版截图逐字复刻的, 这里只是把它们按顺序汇成一页。

    python3 -m us_monitor.m6_text               # 全部（含日内）
    python3 -m us_monitor.m6_text --no-intraday
输出: dashboard/latest.txt + dashboard/latest.html（等宽 <pre> 包一层, 手机可读）
"""
import contextlib
import datetime as dt
import html
import io
import shutil
import sys
from pathlib import Path

from . import config as C
from . import earnings
from .data import fetch_daily, fetch_intraday
from . import (m1_macro, m2_sectors, m3_themes, m4_watchlist, m5_intraday,
               m7_gao, m8_alerts, m9_premarket, m10_camslim, m12_capex, m13_bogo)
from .run_all import compute_crosscheck, cross_check

OUT_DIR = Path(__file__).resolve().parent.parent / "dashboard"

WRAP_CSS = """
:root { color-scheme: light dark; }
body { margin:0; padding:18px 14px; background:#fcfcfb; color:#111; }
@media (prefers-color-scheme: dark) { body { background:#111110; color:#e8e6dd; } }
pre { margin:0; font:12.5px/1.55 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
      white-space:pre; overflow-x:auto; }
a { color:#2a78d6; }
"""


def build(with_intraday=True) -> Path:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        print(f"{'=' * 64}")
        print(f"  波哥信号 · 美股监控（文本版） 生成 {dt.datetime.now():%Y-%m-%d %H:%M}")
        print(f"{'=' * 64}\n")

        daily = fetch_daily(C.all_daily_tickers())
        m1_macro.run(daily)
        print()
        m10_camslim.run(daily)
        print()
        gao = m7_gao.run(daily)
        print()
        m8_alerts.run(daily, gao)
        print()
        sec_df = m2_sectors.run(daily)
        print()
        theme_df = m3_themes.run(daily)
        print()
        wl_df = m4_watchlist.run(daily)
        print()

        cal = earnings.upcoming(C.WATCHLIST, days=14)
        print("=" * 96)
        print("【财报雷达 — 观察池未来14日财报日历】")
        wd = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
        if cal:
            for d, tk in cal:
                print(f"📅 {d:%m-%d} ({wd[d.weekday()]})  {tk}")
        else:
            print("👉 未来14日观察池无财报")
        print("=" * 96)
        print()

        intra_df = None
        if with_intraday:
            intra = fetch_intraday(C.WATCHLIST)
            intra_df = m5_intraday.run(intra, daily)
            print()

        cross_check(sec_df, theme_df, wl_df, intra_df)
        print()
        m9_premarket.run(daily)
        print()
        m13_bogo.run()
        print()
        try:
            m12_capex.run(refresh=True)
        except Exception as exc:
            print(f"【AI 资本周期看门狗】未验证: {exc}")
        print()
        print("免责: 信息整理非投资建议, 数据以官方披露与实时行情为准。")

    text = buf.getvalue()
    OUT_DIR.mkdir(exist_ok=True)
    from .data import col
    date = col(daily, "Close", C.BENCHMARK).index[-1].strftime("%Y-%m-%d")

    txt_path = OUT_DIR / f"text_{date}.txt"
    txt_path.write_text(text, encoding="utf-8")
    shutil.copy(txt_path, OUT_DIR / "latest.txt")

    page = (f'<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>波哥信号 {date}</title><style>{WRAP_CSS}</style>'
            f'<pre>[<a href="manual.html">使用手册</a>] '
            f'[<a href="rich.html">图形版</a>] [<a href="history.html">历史</a>]\n\n'
            + html.escape(text) + "</pre>")
    out = OUT_DIR / f"dashboard_{date}.html"
    out.write_text(page, encoding="utf-8")
    shutil.copy(out, OUT_DIR / "latest.html")
    print(f"✅ 文本版已生成: {out}", file=sys.stderr)
    return out


if __name__ == "__main__":
    build(with_intraday="--no-intraday" not in sys.argv)
