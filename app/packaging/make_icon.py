"""Generate lecturepack.ico from the design's logo mark.

Orange (#EF5A1E) rounded square with a white rotated-square glyph, matching the
header logo in the design. Run once; the .ico is committed so builds don't need
Pillow. Re-run only if the brand mark changes.
"""

from __future__ import annotations

import os

from PIL import Image, ImageDraw

ORANGE = (239, 90, 30, 255)
WHITE = (255, 255, 255, 255)
SIZES = [16, 24, 32, 48, 64, 128, 256]


def render(size: int) -> Image.Image:
    # Supersample for clean edges, then downscale.
    scale = 8
    s = size * scale
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    radius = int(s * 0.28)
    d.rounded_rectangle([0, 0, s - 1, s - 1], radius=radius, fill=ORANGE)

    # White rotated square (diamond) in the center — same glyph as the web logo.
    diamond = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    dd = ImageDraw.Draw(diamond)
    half = int(s * 0.19)
    cx = cy = s // 2
    dd.rounded_rectangle([cx - half, cy - half, cx + half, cy + half],
                         radius=int(half * 0.22), fill=WHITE)
    diamond = diamond.rotate(45, resample=Image.BICUBIC, center=(cx, cy))
    img.alpha_composite(diamond)

    return img.resize((size, size), Image.LANCZOS)


def main() -> None:
    out = os.path.join(os.path.dirname(__file__), "lecturepack.ico")
    base = render(256)
    base.save(out, format="ICO", sizes=[(sz, sz) for sz in SIZES])
    # Also emit a PNG for docs/README use.
    base.save(os.path.join(os.path.dirname(__file__), "lecturepack.png"))
    print("wrote", out)


if __name__ == "__main__":
    main()
