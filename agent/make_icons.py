"""Generates the phone app icons (run once; the PNGs are committed in agent/static/)."""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).with_name("static")


def icon(size: int, maskable: bool = False) -> Image.Image:
    img = Image.new("RGB", (size, size), "#4f46e5")
    d = ImageDraw.Draw(img)
    for y in range(size):  # indigo -> violet diagonal-ish gradient
        t = y / size
        d.line([(0, y), (size, y)], fill=(int(79 + (124 - 79) * t), int(70 + (58 - 70) * t), int(229 + (237 - 229) * t)))
    scale = 0.42 if maskable else 0.55  # maskable icons keep content inside the safe circle
    try:
        font = ImageFont.truetype("arialbd.ttf", int(size * scale))
    except OSError:
        font = ImageFont.load_default(int(size * scale))
    d.text((size / 2, size / 2), "F", fill="white", font=font, anchor="mm")
    return img


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    icon(192).save(OUT / "icon-192.png", optimize=True)
    icon(512).save(OUT / "icon-512.png", optimize=True)
    icon(512, maskable=True).save(OUT / "icon-maskable-512.png", optimize=True)
    icon(180).save(OUT / "apple-touch-icon.png", optimize=True)
    print("icons written to", OUT)
