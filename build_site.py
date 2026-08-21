# -*- coding: utf-8 -*-
"""
站点构建入口（GitHub Actions 调用）。
生成 docs/index.html（GitHub Pages 源）+ 使用手册 + 历史归档 + 整页 PNG。
"""
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DOCS = ROOT / "docs"
HIST = DOCS / "history"
NY = timezone(timedelta(hours=-4))          # 粗略 ET，仅用于文件名与标注


def main():
    DOCS.mkdir(exist_ok=True)
    HIST.mkdir(exist_ok=True)
    from us_monitor import m6_dashboard as D, m6_text as T, manual

    no_intraday = "--no-intraday" in sys.argv
    rich = D.build(with_intraday=not no_intraday)      # 图形版 → rich.html
    shutil.copy(rich, DOCS / "rich.html")
    out = T.build(with_intraday=not no_intraday)       # 文本版 = 首页（姐姐原版审美）
    manual.build()

    src_dir = D.OUT_DIR
    day = out.stem.replace("dashboard_", "")

    shutil.copy(out, DOCS / "index.html")
    shutil.copy(out, HIST / f"{day}.html")
    shutil.copy(src_dir / "latest.txt", DOCS / "latest.txt")
    try:
        from us_monitor import m13_bogo
        m13_bogo.build_page()
        shutil.copy(src_dir / "bogo.html", DOCS / "bogo.html")
    except Exception as exc:
        print(f"WARN: 波哥页 {exc}")
    try:
        from us_monitor import m15_bogo_cn
        m15_bogo_cn.build_page()
        shutil.copy(src_dir / "bogo_cn.html", DOCS / "bogo_cn.html")
        shutil.copy(src_dir / "bogo.html", DOCS / "bogo.html")  # tabs四批合一主页,必须晚于m13的拷贝以覆盖其单页版
        from us_monitor import m16_summary
        m16_summary.build_page()
        shutil.copy(src_dir / "summary.html", DOCS / "summary.html")
    except Exception as exc:
        print(f"WARN: 波哥A股页 {exc}")
    try:
        from us_monitor import m19_radar
        etf = m19_radar.build_page()
        shutil.copy(etf, DOCS / "etf.html")
        shutil.copy(etf.parent / m19_radar.TV_LIST_FILENAME,
                    DOCS / m19_radar.TV_LIST_FILENAME)
        shutil.copy(etf.parent / m19_radar.TV_SYMBOLS_FILENAME,
                    DOCS / m19_radar.TV_SYMBOLS_FILENAME)
        shutil.copy(etf.parent / m19_radar.ETF_TRENDS_FILENAME,
                    DOCS / m19_radar.ETF_TRENDS_FILENAME)
    except Exception as exc:
        print(f"WARN: ETF 涨幅页 {exc}")
    man = src_dir / "manual.html"
    if man.exists():
        shutil.copy(man, DOCS / "manual.html")

    # 整页 PNG 只保留最新一张（供 Lark）; 历史不存 PNG——每天 2-3MB 太占仓库
    try:
        from us_monitor import shot
        shot.capture(DOCS / "index.html", DOCS / "latest.png")
    except Exception as exc:
        print(f"WARN: 截图跳过 {exc}")
    # 历史只留文本版最近 60 天
    hist = sorted(HIST.glob("*.html"), reverse=True)
    for f in hist[60:]:
        f.unlink()
        (HIST / f"{f.stem}.png").unlink(missing_ok=True)
    for f in HIST.glob("*.png"):          # 清掉既往存的 PNG
        f.unlink()

    # 波哥原图（本地生成时才有；云端沿用仓库里已提交的）
    bogo_src = src_dir / "bogo"
    if bogo_src.exists():
        (DOCS / "bogo").mkdir(exist_ok=True)
        for f in bogo_src.glob("*.png"):
            shutil.copy(f, DOCS / "bogo" / f.name)
    cn_src = src_dir / "bogo_cn"
    if cn_src.exists():
        for sub in cn_src.iterdir():
            if sub.is_dir():
                (DOCS / "bogo_cn" / sub.name).mkdir(parents=True, exist_ok=True)
                for f in sub.glob("*.png"):
                    shutil.copy(f, DOCS / "bogo_cn" / sub.name / f.name)

    _write_history_index()
    print(f"✅ 站点已生成: docs/index.html (数据日 {day})")


def _write_history_index():
    """历史归档索引页"""
    files = sorted(HIST.glob("*.html"), reverse=True)
    rows = "\n".join(
        f'<li><a href="history/{f.name}">{f.stem}</a>'
        + (f' · <a href="history/{f.stem}.png">PNG</a>' if (HIST / f"{f.stem}.png").exists() else "")
        + "</li>" for f in files[:120])
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    (DOCS / "history.html").write_text(
        f'<meta charset="utf-8"><title>历史归档</title>'
        f'<style>body{{font:15px/1.8 system-ui;max-width:640px;margin:40px auto;padding:0 16px}}'
        f'a{{color:#2a78d6}}</style>'
        f'<h1>📚 历史归档</h1><p><a href="index.html">← 回到最新看板</a></p>'
        f'<ul>{rows}</ul><p style="color:#888;font-size:12px">更新于 {stamp}</p>',
        encoding="utf-8")


if __name__ == "__main__":
    main()
