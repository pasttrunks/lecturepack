"""Generate the installer wizard's branded images.

The Inno wizard used to ship with Inno's own stock artwork, so the first thing
a student ever saw of LecturePack was a generic blue-and-white setup box. These
render the app's own mark -- the orange rounded square with the white diamond
(the same glyph make_icon.py draws) -- on the dark shell colour, with the aqua
accent the UI uses.

**Every size is rendered natively.** That is not decoration: Inno's Setup binary
is only SYSTEM DPI aware (see BUG-67), so on a scaled display it resamples
anything it was not given at the right size, and a resampled banner is the most
visible thing in the window. Inno picks the closest match from the
comma-separated list in lecturepack.iss.

Run once; the .bmp files are committed so builds don't need Pillow. Re-run only
if the brand mark changes:

    python app/packaging/make_wizard_images.py
"""

from __future__ import annotations

import os

from PIL import Image, ImageDraw, ImageFilter

# Dark-theme tokens, copied from app/ui/app.css so the installer and the app it
# installs are the same product.
BG = (0x16, 0x19, 0x1F)
PANEL = (0x1F, 0x24, 0x2C)
ORANGE = (0xFF, 0x6C, 0x36)
AQUA = (0xB3, 0xEB, 0xF2)
WHITE = (0xFF, 0xFF, 0xFF)

# Inno Setup's own wizard image sizes, in the order it looks for them.
LARGE_SIZES = [(164, 314), (192, 386), (205, 393), (246, 471), (273, 525), (328, 628)]
SMALL_SIZES = [(55, 58), (64, 68), (69, 73), (83, 88), (92, 97), (110, 116)]

SUPERSAMPLE = 4


def _mark(size: int) -> Image.Image:
    """The app mark: orange rounded square, white rotated square inside.

    Kept byte-for-byte in step with make_icon.py's proportions -- radius 0.28 of
    the side, diamond half-extent 0.19, corner 0.22 of that -- so the installer
    banner and the taskbar icon are recognisably one mark.
    """
    s = size * SUPERSAMPLE
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, s - 1, s - 1], radius=int(s * 0.28), fill=ORANGE + (255,))

    diamond = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    dd = ImageDraw.Draw(diamond)
    half = int(s * 0.19)
    cx = cy = s // 2
    dd.rounded_rectangle([cx - half, cy - half, cx + half, cy + half],
                         radius=int(half * 0.22), fill=WHITE + (255,))
    diamond = diamond.rotate(45, resample=Image.BICUBIC, center=(cx, cy))
    img.alpha_composite(diamond)
    return img.resize((size, size), Image.LANCZOS)


def _glow(canvas: Image.Image, cx: int, cy: int, radius: int) -> None:
    """A soft orange bloom behind the mark, so it sits on the dark field rather
    than floating on it. Blurred rather than a hard gradient: at 164px wide a
    banded gradient shows its steps."""
    layer = Image.new("RGB", canvas.size, BG)
    d = ImageDraw.Draw(layer)
    d.ellipse([cx - radius, cy - radius, cx + radius, cy + radius],
              fill=(0x3A, 0x25, 0x1C))
    layer = layer.filter(ImageFilter.GaussianBlur(radius * 0.45))
    canvas.paste(layer, (0, 0))


def render_large(width: int, height: int) -> Image.Image:
    img = Image.new("RGB", (width, height), BG)
    cx, cy = width // 2, int(height * 0.38)
    _glow(img, cx, cy, int(width * 0.62))

    mark_size = int(width * 0.40)
    mark = _mark(mark_size)
    img.paste(mark, (cx - mark_size // 2, cy - mark_size // 2), mark)

    d = ImageDraw.Draw(img)
    # Aqua rule under the mark -- the UI's own accent, and the only other colour
    # in the app's palette.
    rule_w = int(width * 0.30)
    rule_y = cy + int(mark_size * 0.78)
    rule_h = max(2, int(height * 0.008))
    d.rectangle([cx - rule_w // 2, rule_y, cx + rule_w // 2, rule_y + rule_h], fill=AQUA)

    # Three stacked bars toward the foot, narrowing: the "lecture becomes a
    # study pack" idea the Home screen's cards carry, at banner scale.
    bar_h = max(3, int(height * 0.014))
    gap = max(4, int(height * 0.022))
    top = int(height * 0.74)
    for i, (frac, colour) in enumerate(
            ((0.46, PANEL), (0.34, PANEL), (0.22, ORANGE))):
        w = int(width * frac)
        y = top + i * (bar_h + gap)
        d.rounded_rectangle([cx - w // 2, y, cx + w // 2, y + bar_h],
                            radius=bar_h // 2, fill=colour)
    return img


def render_small(width: int, height: int) -> Image.Image:
    """The header icon on every inner page. Inno draws it on the page's own
    background, so this is padded rather than bled to the edge."""
    img = Image.new("RGB", (width, height), BG)
    mark_size = int(min(width, height) * 0.78)
    mark = _mark(mark_size)
    img.paste(mark, ((width - mark_size) // 2, (height - mark_size) // 2), mark)
    return img


def main() -> None:
    here = os.path.dirname(os.path.abspath(__file__))
    written = []
    for width, height in LARGE_SIZES:
        path = os.path.join(here, f"wizard-large-{width}x{height}.bmp")
        render_large(width, height).save(path, "BMP")
        written.append(path)
    for width, height in SMALL_SIZES:
        path = os.path.join(here, f"wizard-small-{width}x{height}.bmp")
        render_small(width, height).save(path, "BMP")
        written.append(path)
    for path in written:
        print("wrote", os.path.relpath(path, here))


if __name__ == "__main__":
    main()
