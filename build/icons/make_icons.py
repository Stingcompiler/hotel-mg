"""Draw the Sky Towers icon and the installer images (Pillow only; run from the repo root).

    python build/icons/make_icons.py

The mark: three white towers on the design's primary teal (#0F766E → #115E59), the tallest with a spire, and an
amber star in the sky. Sizes up to 32 px drop the windows so the silhouette stays crisp. Writes:
  desktop/src-tauri/icons/  icon.png (512), 32x32.png, 128x128.png, 128x128@2x.png, icon.ico (16–256)
  desktop/src-tauri/windows/installer-header.bmp (150×57), installer-sidebar.bmp (164×314)
  desktop/fallback/icon.png (128, the start page)
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
ICONS = ROOT / "desktop" / "src-tauri" / "icons"
WINDOWS = ROOT / "desktop" / "src-tauri" / "windows"

TEAL_TOP = (20, 133, 124)  # a touch lighter than primary for depth
TEAL = (15, 118, 110)  # --color-primary
TEAL_DARK = (17, 94, 89)  # --color-primary-hover
WHITE = (255, 255, 255)
AMBER = (251, 191, 36)
SS = 4  # supersampling for anti-aliased edges


def _gradient(size: tuple[int, int], top, bottom) -> Image.Image:
    w, h = size
    img = Image.new("RGB", size, top)
    px = ImageDraw.Draw(img)
    for y in range(h):
        t = y / max(1, h - 1)
        px.line([(0, y), (w, y)], fill=tuple(round(a + (b - a) * t) for a, b in zip(top, bottom, strict=True)))
    return img


def _star(draw: ImageDraw.ImageDraw, cx: float, cy: float, r: float, fill) -> None:
    """Four-point sparkle."""
    k = r * 0.28
    draw.polygon(
        [(cx, cy - r), (cx + k, cy - k), (cx + r, cy), (cx + k, cy + k), (cx, cy + r), (cx - k, cy + k), (cx - r, cy), (cx - k, cy - k)],
        fill=fill,
    )


def _towers(draw: ImageDraw.ImageDraw, s: float, ox: float, oy: float, detailed: bool, window_fill) -> None:
    """The three towers in a 1024-unit box scaled by s and offset by (ox, oy)."""

    def box(x0, y0, x1, y1):
        return (ox + x0 * s, oy + y0 * s, ox + x1 * s, oy + y1 * s)

    # (left, top, right), standing on y=800; small sizes get wider gaps so the three stay apart at 16 px.
    towers = [(230, 470, 410), (430, 250, 594), (614, 370, 794)] if detailed else [(170, 470, 380), (462, 250, 622), (704, 400, 884)]
    base = 800
    for x0, top, x1 in towers:
        draw.rounded_rectangle(box(x0, top, x1, base), radius=14 * s, fill=WHITE)
    # Spire on the tallest tower.
    mid = (towers[1][0] + towers[1][2]) / 2
    draw.polygon([(ox + (mid - 20) * s, oy + 252 * s), (ox + (mid + 20) * s, oy + 252 * s), (ox + mid * s, oy + 150 * s)], fill=WHITE)
    if not detailed:
        return
    # Ground line.
    draw.rounded_rectangle(box(190, 816, 834, 850), radius=17 * s, fill=WHITE)
    for x0, top, x1 in towers:
        cols = 3 if x1 - x0 > 170 else 2
        cw, gap = 30, (x1 - x0 - 30 * cols) / (cols + 1)
        y = top + 50
        while y + 34 < base - 30:
            for c in range(cols):
                wx = x0 + gap + c * (cw + gap)
                draw.rectangle(box(wx, y, wx + cw, y + 34), fill=window_fill)
            y += 70


def icon(size: int) -> Image.Image:
    big = size * SS
    detailed = size >= 64
    bg = _gradient((big, big), TEAL_TOP, TEAL_DARK).convert("RGBA")
    mask = Image.new("L", (big, big), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, big - 1, big - 1), radius=big * 0.22, fill=255)
    layer = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    s = big / 1024
    _towers(draw, s, 0, 0, detailed, window_fill=TEAL)
    _star(draw, (812 if detailed else 800) * s, 214 * s, (120 if detailed else 170) * s, AMBER)
    bg.alpha_composite(layer)
    out = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    out.paste(bg, (0, 0), mask)
    return out.resize((size, size), Image.LANCZOS)


def _font(size: int) -> ImageFont.FreeTypeFont:
    for name in ("segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size)


def sidebar() -> Image.Image:
    """Welcome/finish page picture, 164×314: the mark over the gradient and the Latin wordmark."""
    w, h = 164 * SS, 314 * SS
    img = _gradient((w, h), TEAL_TOP, TEAL_DARK).convert("RGBA")
    draw = ImageDraw.Draw(img)
    for x, y, r in ((22, 28, 3), (58, 62, 2), (120, 20, 3), (140, 84, 2), (30, 110, 2), (92, 40, 2)):  # faint stars
        _star(draw, x * SS, y * SS, r * SS, (255, 255, 255, 90))
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    s = w / 1024 * 0.86
    _towers(ld, s, w * 0.07, h * 0.30, True, window_fill=TEAL)
    _star(ld, w * 0.07 + 812 * s, h * 0.30 + 214 * s, 110 * s, AMBER)
    img.alpha_composite(layer)
    font = _font(20 * SS)
    text = "Sky Towers"
    tw = draw.textlength(text, font=font)
    draw.text(((w - tw) / 2, h * 0.84), text, font=font, fill=WHITE)
    return img.convert("RGB").resize((164, 314), Image.LANCZOS)


def header() -> Image.Image:
    """Top-right picture on the inner pages, 150×57: white background, the small mark and the wordmark."""
    w, h = 150 * SS, 57 * SS
    img = Image.new("RGB", (w, h), WHITE)
    mark = icon(44 * SS // 2).resize((44 * SS, 44 * SS), Image.LANCZOS)
    img.paste(mark, (w - mark.width - 6 * SS, (h - mark.height) // 2), mark)
    draw = ImageDraw.Draw(img)
    font = _font(15 * SS)
    text = "Sky Towers"
    tw = draw.textlength(text, font=font)
    draw.text((w - mark.width - 12 * SS - tw, h / 2 - 11 * SS), text, font=font, fill=TEAL_DARK)
    return img.resize((150, 57), Image.LANCZOS)


def main() -> None:
    ICONS.mkdir(parents=True, exist_ok=True)
    icon(512).save(ICONS / "icon.png")
    icon(32).save(ICONS / "32x32.png")
    icon(128).save(ICONS / "128x128.png")
    icon(256).save(ICONS / "128x128@2x.png")
    sizes = [16, 24, 32, 48, 64, 128, 256]
    frames = [icon(n) for n in sizes]
    frames[-1].save(ICONS / "icon.ico", sizes=[(n, n) for n in sizes], append_images=frames[:-1])
    icon(128).save(ROOT / "desktop" / "fallback" / "icon.png")  # the start page shown while the service starts
    sidebar().save(WINDOWS / "installer-sidebar.bmp")
    header().save(WINDOWS / "installer-header.bmp")
    print("icons and installer images written")


if __name__ == "__main__":
    main()
