"""Generate the aivoice .icns bundle icon.

Produces a 1024x1024 rounded-square background with a white microphone glyph,
then `iconutil` packs the multi-resolution .iconset into Resources/icon.icns.

Run via:  uv run --with pillow python scripts/gen_icon.py
"""

from __future__ import annotations

import math
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw

REPO = Path(__file__).resolve().parent.parent
ICONSET = REPO / "build" / "icon.iconset"
OUT_ICNS = REPO / "build" / "icon.icns"

# Macaron-style flat gradient — deep teal to slate, easy on the eye in both
# light and dark menu bars.
BG_TOP = (37, 99, 109)      # teal
BG_BOTTOM = (24, 30, 45)    # near-black slate
FG = (255, 255, 255, 255)   # white mic glyph

CANVAS = 1024
CORNER_RADIUS = 224  # macOS Big Sur+ continuous-curve squircle radius (~22%)


def _rounded_mask(size: int, radius: int) -> Image.Image:
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size, size), radius=radius, fill=255)
    return mask


def _gradient_bg(size: int, top: tuple[int, int, int], bottom: tuple[int, int, int]) -> Image.Image:
    bg = Image.new("RGB", (size, size), top)
    px = bg.load()
    for y in range(size):
        t = y / (size - 1)
        r = int(top[0] * (1 - t) + bottom[0] * t)
        g = int(top[1] * (1 - t) + bottom[1] * t)
        b = int(top[2] * (1 - t) + bottom[2] * t)
        for x in range(size):
            px[x, y] = (r, g, b)
    return bg


def _draw_mic(draw: ImageDraw.ImageDraw, size: int, color: tuple[int, int, int, int]) -> None:
    """A clean studio-microphone glyph centred in the canvas."""
    cx = size // 2
    cy = int(size * 0.46)

    # Capsule body
    body_w = int(size * 0.30)
    body_h = int(size * 0.46)
    left = cx - body_w // 2
    right = cx + body_w // 2
    top = cy - body_h // 2
    bottom = cy + body_h // 2
    draw.rounded_rectangle((left, top, right, bottom), radius=body_w // 2, fill=color)

    # Stand: arc cradle below the capsule
    stand_w = int(size * 0.48)
    stand_h = int(size * 0.34)
    stand_thickness = int(size * 0.035)
    sl = cx - stand_w // 2
    sr = cx + stand_w // 2
    st = bottom - stand_h // 3
    sb = bottom + (stand_h * 2) // 3
    # arc from 0deg-180deg (bottom half) -- PIL counts 0 at 3 o'clock, sweeping CW.
    draw.arc((sl, st, sr, sb), start=0, end=180, fill=color, width=stand_thickness)

    # Vertical post from arc bottom down to base
    post_top = sb - stand_thickness // 2
    post_bot = post_top + int(size * 0.11)
    draw.rounded_rectangle(
        (cx - stand_thickness // 2, post_top, cx + stand_thickness // 2, post_bot),
        radius=stand_thickness // 2,
        fill=color,
    )

    # Base bar
    base_w = int(size * 0.24)
    base_h = stand_thickness
    draw.rounded_rectangle(
        (cx - base_w // 2, post_bot - stand_thickness // 2,
         cx + base_w // 2, post_bot + base_h // 2),
        radius=base_h // 2,
        fill=color,
    )


def render_master() -> Image.Image:
    bg = _gradient_bg(CANVAS, BG_TOP, BG_BOTTOM).convert("RGBA")

    # Draw the mic glyph onto a transparent layer first so we can apply a
    # subtle drop shadow.
    glyph = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    _draw_mic(ImageDraw.Draw(glyph), CANVAS, FG)

    shadow = glyph.copy()
    shadow_alpha = shadow.split()[-1].point(lambda v: int(v * 0.35))
    shadow.putalpha(shadow_alpha)
    shadow_offset = (0, int(CANVAS * 0.012))

    bg.alpha_composite(shadow, dest=shadow_offset)
    bg.alpha_composite(glyph)

    mask = _rounded_mask(CANVAS, CORNER_RADIUS)
    out = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    out.paste(bg, (0, 0), mask=mask)
    return out


def emit_iconset(master: Image.Image) -> None:
    ICONSET.mkdir(parents=True, exist_ok=True)
    # macOS expects: 16, 32, 64, 128, 256, 512, 1024 at @1x and @2x flavours.
    sizes = [
        (16, "icon_16x16.png"),
        (32, "icon_16x16@2x.png"),
        (32, "icon_32x32.png"),
        (64, "icon_32x32@2x.png"),
        (128, "icon_128x128.png"),
        (256, "icon_128x128@2x.png"),
        (256, "icon_256x256.png"),
        (512, "icon_256x256@2x.png"),
        (512, "icon_512x512.png"),
        (1024, "icon_512x512@2x.png"),
    ]
    for size, name in sizes:
        master.resize((size, size), Image.LANCZOS).save(ICONSET / name, "PNG")


def pack_icns() -> None:
    subprocess.run(
        ["iconutil", "-c", "icns", str(ICONSET), "-o", str(OUT_ICNS)],
        check=True,
    )


def main() -> int:
    master = render_master()
    emit_iconset(master)
    pack_icns()
    print(f"wrote {OUT_ICNS}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
