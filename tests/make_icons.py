"""Generate PWA icons for the Middle Atlas Real Estate app (run once)."""
import os

from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "static", "icons")
os.makedirs(OUT, exist_ok=True)

BG = (58, 125, 68, 255)        # green
HILL_LIGHT = (140, 190, 120, 255)
HILL_DARK = (95, 155, 100, 255)
SUN = (255, 214, 107, 255)


def draw_art(d: ImageDraw.ImageDraw, s: int) -> None:
    """Paint sun + rolling hills scaled to size s."""
    d.ellipse([s * 0.62, s * 0.12, s * 0.84, s * 0.34], fill=SUN)
    d.polygon(
        [(s * -0.05, s * 1.05), (s * 0.38, s * 0.52), (s * 0.78, s * 1.05)],
        fill=HILL_DARK,
    )
    d.polygon(
        [(s * 0.30, s * 1.05), (s * 0.72, s * 0.62), (s * 1.08, s * 1.05)],
        fill=HILL_LIGHT,
    )


def rounded_icon(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    art = Image.new("RGBA", (size, size), BG)
    draw_art(ImageDraw.Draw(art), size)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, size - 1, size - 1], radius=int(size * 0.22), fill=255
    )
    img.paste(art, (0, 0), mask)
    return img


def maskable_icon(size: int) -> Image.Image:
    """Full-bleed background, artwork kept inside the 80% safe zone."""
    img = Image.new("RGBA", (size, size), BG)
    inner = int(size / 0.80)
    pad = (inner - size) // -2
    big = Image.new("RGBA", (inner, inner), (0, 0, 0, 0))
    art = Image.new("RGBA", (inner, inner), BG)
    draw_art(ImageDraw.Draw(art), inner)
    big = art
    img.alpha_composite(big.resize((size * 2 // 2,) * 2).crop(
        (int(inner * 0.10), int(inner * 0.10),
         int(inner * 0.90), int(inner * 0.90))
    ).resize((size, size)))
    return img


for name, size in [("icon-192.png", 192), ("icon-512.png", 512)]:
    rounded_icon(size).save(os.path.join(OUT, name))

maskable_icon(512).save(os.path.join(OUT, "icon-maskable-512.png"))
rounded_icon(180).save(os.path.join(OUT, "apple-touch-icon.png"))
rounded_icon(32).resize((32, 32)).save(os.path.join(OUT, "favicon-32.png"))
print("icons written to", OUT)
