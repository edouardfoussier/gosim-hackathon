#!/usr/bin/env python3
"""Render Xiexie's brand glyph into the Tauri-required icon set.

This script ports the warm-ember triangle from ``overlay/glyph.py`` (the
Claude-Design canvas viewBox ``M24 5.4 L43 39.6 Q44.2 41.7 41.8 41.7
L6.2 41.7 Q3.8 41.7 5 39.6 Z``) and produces, in
``desktop/src-tauri/icons/``:

- ``icon.icns``           macOS app bundle icon (multi-resolution)
- ``icon.png``            1024×1024 master, used as Tauri fallback
- ``32x32.png``           Tauri-required size
- ``128x128.png``         Tauri-required size
- ``128x128@2x.png``      Tauri-required size (256×256)
- ``tray.png``            16×16 monochrome template (macOS menu bar)
- ``tray@2x.png``         32×32 monochrome template (Retina menu bar)

The colour icon uses the brand crimson fill (``#b8351c``) on a creamy
canvas (``#fbf7f0``) with a soft drop-shadow halo so the icon reads as
warmth + caution rather than alarm. The tray icons are pure-black
silhouettes so macOS auto-tints them for both light and dark menu bars
(this is how a "template image" works — anything non-zero alpha is
rendered as the menu-bar foreground colour).

Run from anywhere:

    python3 desktop/scripts/make-icons.py

Requires Pillow (already a backend dep) and macOS ``iconutil`` (ships
with Xcode CLT) for the final ``.icns`` packing.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFilter
except ImportError as exc:  # pragma: no cover
    sys.stderr.write(
        "make-icons.py requires Pillow. Install it with:\n"
        "  uv pip install --system pillow\n"
        "or rely on the backend venv that already ships Pillow.\n"
    )
    raise SystemExit(1) from exc

REPO_ROOT = Path(__file__).resolve().parents[2]
ICONS_DIR = REPO_ROOT / "desktop" / "src-tauri" / "icons"

BRAND_CRIMSON = (184, 53, 28, 255)
BRAND_CREAM = (251, 247, 240, 255)
BRAND_GLOW = (184, 53, 28, 90)
SYMBOL_CREAM = (255, 248, 235, 255)

VIEWBOX = 48.0


def _scaled(side_px: int) -> float:
    return side_px / VIEWBOX


def _triangle_polygon(side_px: int) -> list[tuple[float, float]]:
    """Approximate the rounded-base triangle as a 24-vertex polygon.

    The exact path uses two quadratic beziers on the base corners; we
    sample each curve at 8 points so the rasterised silhouette stays
    smooth at every icon size.
    """

    s = _scaled(side_px)
    apex = (24.0 * s, 5.4 * s)
    right_corner_start = (43.0 * s, 39.6 * s)
    right_corner_ctrl = (44.2 * s, 41.7 * s)
    right_corner_end = (41.8 * s, 41.7 * s)
    left_corner_start = (6.2 * s, 41.7 * s)
    left_corner_ctrl = (3.8 * s, 41.7 * s)
    left_corner_end = (5.0 * s, 39.6 * s)

    def quad(p0, p1, p2, samples=8):
        pts = []
        for i in range(samples + 1):
            t = i / samples
            x = (1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * p1[0] + t**2 * p2[0]
            y = (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * p1[1] + t**2 * p2[1]
            pts.append((x, y))
        return pts

    poly: list[tuple[float, float]] = [apex, right_corner_start]
    poly.extend(quad(right_corner_start, right_corner_ctrl, right_corner_end))
    poly.append(left_corner_start)
    poly.extend(quad(left_corner_start, left_corner_ctrl, left_corner_end))
    return poly


def _draw_bang(draw: ImageDraw.ImageDraw, side_px: int, color: tuple[int, ...]) -> None:
    """``!`` symbol: vertical pill (width 3, height 13, top y=17, x=24) + dot."""
    s = _scaled(side_px)
    bar_x0 = 22.5 * s
    bar_y0 = 17.0 * s
    bar_x1 = 25.5 * s
    bar_y1 = 30.0 * s
    radius = 1.5 * s
    draw.rounded_rectangle((bar_x0, bar_y0, bar_x1, bar_y1), radius=radius, fill=color)
    dot_cx = 24.0 * s
    dot_cy = 34.0 * s
    dot_r = 1.8 * s
    draw.ellipse(
        (dot_cx - dot_r, dot_cy - dot_r, dot_cx + dot_r, dot_cy + dot_r),
        fill=color,
    )


def render_color_icon(side_px: int) -> Image.Image:
    """Crimson triangle with cream background and soft ember halo."""
    canvas = Image.new("RGBA", (side_px, side_px), BRAND_CREAM)

    # ── ambient glow underneath the triangle ────────────────────────
    glow_layer = Image.new("RGBA", (side_px, side_px), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow_layer)
    gd.polygon(_triangle_polygon(side_px), fill=BRAND_GLOW)
    blur_radius = max(2, side_px // 32)
    glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(radius=blur_radius))
    canvas.alpha_composite(glow_layer)

    # ── solid triangle ──────────────────────────────────────────────
    body = Image.new("RGBA", (side_px, side_px), (0, 0, 0, 0))
    bd = ImageDraw.Draw(body)
    bd.polygon(_triangle_polygon(side_px), fill=BRAND_CRIMSON)
    canvas.alpha_composite(body)

    # ── exclamation mark ────────────────────────────────────────────
    sym = Image.new("RGBA", (side_px, side_px), (0, 0, 0, 0))
    sd = ImageDraw.Draw(sym)
    _draw_bang(sd, side_px, SYMBOL_CREAM)
    canvas.alpha_composite(sym)

    return canvas


def render_tray_template(side_px: int) -> Image.Image:
    """Pure-black silhouette suitable for an NSImage template image."""
    img = Image.new("RGBA", (side_px, side_px), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    # Slightly inset so the silhouette doesn't touch the menu bar edge.
    inset = max(1, side_px // 16)
    sub = side_px - 2 * inset
    poly = [(x + inset, y + inset) for (x, y) in _triangle_polygon(sub)]
    draw.polygon(poly, fill=(0, 0, 0, 255))
    _draw_bang(draw, sub, (0, 0, 0, 0))  # clear bang area for visual breathing
    # Re-draw bang with full opacity but smaller so it punches a hole-ish
    # contrast inside the silhouette (template images render anything
    # non-zero alpha as foreground colour, so we lighten the bang to 0
    # alpha for a "knocked-out" feel).
    sym = Image.new("RGBA", (side_px, side_px), (0, 0, 0, 0))
    sd = ImageDraw.Draw(sym)
    _draw_bang(sd, sub, (0, 0, 0, 255))
    # Subtract the bang from the silhouette (alpha-mask trick).
    img_pixels = img.load()
    sym_pixels = sym.load()
    for y in range(side_px):
        for x in range(side_px):
            sx, sy = x - inset, y - inset
            if 0 <= sx < sub and 0 <= sy < sub:
                if sym_pixels[x, y][3] > 0:
                    img_pixels[x, y] = (0, 0, 0, 0)
    return img


def write_icns(master_png: Path, out_icns: Path) -> None:
    """Pack a multi-resolution ``.icns`` from a 1024×1024 master."""
    iconutil = shutil.which("iconutil")
    sips = shutil.which("sips")
    if iconutil is None or sips is None:
        sys.stderr.write(
            "iconutil/sips not found — skipping .icns packing. Install Xcode "
            "Command Line Tools (`xcode-select --install`) and re-run.\n"
        )
        return

    sizes = [
        ("icon_16x16.png", 16),
        ("icon_16x16@2x.png", 32),
        ("icon_32x32.png", 32),
        ("icon_32x32@2x.png", 64),
        ("icon_128x128.png", 128),
        ("icon_128x128@2x.png", 256),
        ("icon_256x256.png", 256),
        ("icon_256x256@2x.png", 512),
        ("icon_512x512.png", 512),
        ("icon_512x512@2x.png", 1024),
    ]

    with tempfile.TemporaryDirectory() as tmpdir:
        iconset = Path(tmpdir) / "Xiexie.iconset"
        iconset.mkdir()
        for name, size in sizes:
            img = render_color_icon(size)
            img.save(iconset / name, "PNG")
        subprocess.run(
            [iconutil, "-c", "icns", str(iconset), "-o", str(out_icns)],
            check=True,
        )


def main() -> int:
    ICONS_DIR.mkdir(parents=True, exist_ok=True)

    print(f"[icons] writing into {ICONS_DIR}")

    # ── master colour PNGs ──────────────────────────────────────────
    master = render_color_icon(1024)
    master.save(ICONS_DIR / "icon.png", "PNG")

    for size in (32, 128):
        render_color_icon(size).save(ICONS_DIR / f"{size}x{size}.png", "PNG")
    render_color_icon(256).save(ICONS_DIR / "128x128@2x.png", "PNG")

    # ── tray template PNGs ──────────────────────────────────────────
    render_tray_template(18).save(ICONS_DIR / "tray.png", "PNG")
    render_tray_template(36).save(ICONS_DIR / "tray@2x.png", "PNG")

    # ── icns ────────────────────────────────────────────────────────
    write_icns(ICONS_DIR / "icon.png", ICONS_DIR / "icon.icns")

    files = sorted(ICONS_DIR.iterdir())
    print("[icons] generated:")
    for f in files:
        size_kb = f.stat().st_size / 1024
        print(f"  {f.name:<22} {size_kb:7.1f} KiB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
