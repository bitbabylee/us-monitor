# -*- coding: utf-8 -*-
"""
整页截图 —— 解决「Lark 推送只有部分」的问题。

根因: Chrome headless 的 --screenshot 只截 --window-size 指定的视口,
原来钉死 1400x2400, 而看板加模块后早已远超 2400px → 被拦腰截断。

做法: 用超高视口渲染 → PIL 从底部往上找第一行非背景色 → 裁掉尾部空白。
这样不管页面多长都能完整截到, 且不会留一大片空白。

    python3 -m us_monitor.shot                     # 截 latest.html
    python3 -m us_monitor.shot dashboard_2026-08-07.html
"""
import subprocess
import sys
import tempfile
from pathlib import Path

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
WIDTH = 1400
PROBE_HEIGHT = 24000        # 渲染用的超高视口(够高即可, 多余部分会裁掉)
PAD = 24                    # 内容底部保留的留白像素


def _autocrop_bottom(png: Path, pad: int = PAD) -> tuple[int, int]:
    """从底部往上扫, 找到最后一行「有内容」的位置。返回 (宽, 裁后高)"""
    from PIL import Image
    with Image.open(png) as im:
        im = im.convert("RGB")
        w, h = im.size
        bg = im.getpixel((w - 2, h - 2))          # 右下角当作背景色
        px = im.load()
        last = 0
        for y in range(h - 1, -1, -1):
            # 抽样扫描该行(每 8 px 取一点), 命中非背景即认为有内容
            if any(px[x, y] != bg for x in range(0, w, 8)):
                last = y
                break
        new_h = min(h, last + pad) if last else h
        if new_h < h:
            im.crop((0, 0, w, new_h)).save(png)
        return w, new_h


def capture(html: Path, out: Path = None, width: int = WIDTH,
            dark: bool = False) -> Path | None:
    """整页截图。返回 PNG 路径, 失败返回 None。"""
    html = Path(html)
    if not html.exists():
        print(f"❌ 找不到 {html}", file=sys.stderr)
        return None
    if not CHROME:
        print("❌ 未找到 Chrome", file=sys.stderr)
        return None
    out = Path(out) if out else Path(tempfile.gettempdir()) / f"{html.stem}.png"
    cmd = [CHROME, "--headless", "--disable-gpu", "--hide-scrollbars",
           f"--window-size={width},{PROBE_HEIGHT}",
           "--virtual-time-budget=8000",     # 等页面渲染完(字体/布局)
           f"--screenshot={out}", f"file://{html.resolve()}"]
    if not dark:
        cmd.insert(-2, "--default-background-color=ffffff")
    try:
        subprocess.run(cmd, capture_output=True, timeout=180)
    except Exception as exc:
        print(f"❌ 渲染失败: {exc}", file=sys.stderr)
        return None
    if not out.exists() or out.stat().st_size < 10_000:
        print("❌ 截图为空或过小", file=sys.stderr)
        return None
    w, h = _autocrop_bottom(out)
    print(f"✅ 整页截图: {out}  {w}×{h}px  {out.stat().st_size/1024:.0f}KB")
    return out


def slice_vertical(png: Path, max_h: int = 4000) -> list[Path]:
    """把超长图切成多张(Lark 里超长图会显示成细条, 切片更易读)。
    不需要切时返回 [原图]。"""
    from PIL import Image
    png = Path(png)
    with Image.open(png) as im:
        w, h = im.size
        if h <= max_h:
            return [png]
        parts, n = [], (h + max_h - 1) // max_h
        for i in range(n):
            top, bot = i * max_h, min((i + 1) * max_h, h)
            p = png.with_name(f"{png.stem}_{i+1}of{n}{png.suffix}")
            im.crop((0, top, w, bot)).save(p)
            parts.append(p)
    print(f"✂️  切成 {len(parts)} 张（每张 ≤{max_h}px）")
    return parts


if __name__ == "__main__":
    from .m6_dashboard import OUT_DIR
    target = sys.argv[1] if len(sys.argv) > 1 else "latest.html"
    p = Path(target)
    if not p.is_absolute() and not p.exists():
        p = OUT_DIR / target
    png = capture(p)
    if png and "--slice" in sys.argv:
        slice_vertical(png)
