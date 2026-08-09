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
    man = src_dir / "manual.html"
    if man.exists():
        shutil.copy(man, DOCS / "manual.html")

    # 整页 PNG（Chrome 可用时）—— 供 Lark 推送 / 手机查看
    try:
        from us_monitor import shot
        png = shot.capture(DOCS / "index.html", DOCS / "latest.png")
        if png:
            shutil.copy(png, HIST / f"{day}.png")
    except Exception as exc:
        print(f"WARN: 截图跳过 {exc}")

    # 波哥原图（本地生成时才有；云端沿用仓库里已提交的）
    bogo_src = src_dir / "bogo"
    if bogo_src.exists():
        (DOCS / "bogo").mkdir(exist_ok=True)
        for f in bogo_src.glob("*.png"):
            shutil.copy(f, DOCS / "bogo" / f.name)

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
