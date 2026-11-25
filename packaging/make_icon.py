"""Draws the Jarvis icon (the notch with its two eyes) and saves a multi-size .ico. Made by Nur Al Mahtab."""
from pathlib import Path
from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent / "jarvis.ico"


def draw(size: int) -> Image.Image:
    s = size * 4
    im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((s * 0.04, s * 0.20, s * 0.96, s * 0.80), radius=s * 0.26, fill=(11, 11, 14, 255))
    d.rounded_rectangle((s * 0.04, s * 0.20, s * 0.96, s * 0.80), radius=s * 0.26, outline=(92, 225, 255, 255), width=max(2, s // 32))
    for cx in (0.34, 0.66):
        d.rounded_rectangle((s * (cx - 0.11), s * 0.43, s * (cx + 0.11), s * 0.57), radius=s * 0.07, fill=(228, 247, 255, 255))
    return im.resize((size, size), Image.LANCZOS)


if __name__ == "__main__":
    sizes = [16, 24, 32, 48, 64, 128, 256]
    draw(256).save(OUT, format="ICO", sizes=[(n, n) for n in sizes])
    print("wrote", OUT)
