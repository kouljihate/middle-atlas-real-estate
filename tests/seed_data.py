"""Seed script: generates 120 example lands (with photos & videos).

Run from the project root:
    python tests/seed_data.py          # generate 120 lands
    python tests/seed_data.py --count 200
    python tests/seed_data.py --keep    # append instead of clearing first
"""

import argparse
import os
import random
import shutil
import struct
import sys
import zlib

# Make the project root importable when run as a script.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from app import config  # noqa: E402
from app import db  # noqa: E402

try:
    from app import mac_filter  # noqa: E402
    _ = mac_filter  # available if needed
except Exception:
    pass

DEFAULT_COUNT = 120

TITLES_EN = [
    "Olive Grove", "Wheat Field", "Vineyard Plot", "Citrus Orchard",
    "Almond Farm", "Fig Garden", "Barley Land", "Pasture Lot",
    "Date Palm Estate", "Tomato Greenhouse", "Lavender Field", "Apple Orchard",
]
TITLES_AR = [
    "بستان زيتون", "حقل قمح", "مزرعة كروم", "بستان حمضيات",
    "مزرعة لوز", "حديقة تين", "أرض شعير", "مرعى",
    "ضيعة نخيل", "صوبة طماطم", "حقل خزامى", "بستان تفاح",
]
LOCATIONS_EN = [
    "Sousse", "Tunis", "Sfax", "Kairouan", "Nabeul", "Bizerte",
    "Monastir", "Gabes", "Kasserine", "Beja",
]
LOCATIONS_AR = [
    "سوسة", "تونس", "صفاقس", "القيروان", "نابل", "بنزرت",
    "المنستير", "قابس", "القصرين", "باجة",
]
OWNERS = [
    "Ali Ben Salem", "Fatma Trabelsi", "Mohamed Amri", "Sara Ltaief",
    "Youssef Karoui", "Nadia Chelbi", "Omar Besbes", "Leila Nefzi",
    "Khaled Gharbi", "Amel Saidi", "Hichem Louati", "Rim Jaziri",
]
DESCRIPTIONS = [
    "Fertile land with easy road access and a water well.",
    "Flat plot, ideal for cultivation or livestock.",
    "Quiet rural location, fertile soil, sunny all year.",
    "Near the main road, ready for immediate farming.",
    "Includes a small storage shed and fencing.",
    "",
]


# ---------------------------------------------------------------------------
# Media generation (real PNGs, placeholder video files)
# ---------------------------------------------------------------------------
def make_png(path: str, size: int = 64, color: tuple = (34, 125, 50)) -> None:
    """Write a small, valid truecolour PNG without external dependencies."""
    w = h = size
    raw = bytearray()
    for _ in range(h):
        raw.append(0)  # filter type 0 (None)
        for _ in range(w):
            raw += bytes(color)
    compressed = zlib.compress(bytes(raw), 9)

    def chunk(tag: bytes, data: bytes) -> bytes:
        body = tag + data
        return (
            struct.pack(">I", len(data))
            + body
            + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)
        )

    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", compressed)
        + chunk(b"IEND", b"")
    )
    with open(path, "wb") as fh:
        fh.write(png)


def make_placeholder_video(path: str) -> None:
    """Create a tiny placeholder file with a video extension (not playable).

    Real playback isn't required for seed data; the app only stores the path
    and validates the extension. Drop in ffmpeg-generated clips if you want
    playable samples.
    """
    with open(path, "wb") as fh:
        fh.write(b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom\x00SEED")


def generate_media(upload_dir: str, idx: int, rng: random.Random):
    media = {"photos": [], "videos": [], "audios": [], "documents": []}
    for _ in range(rng.randint(0, 3)):
        name = f"seed_p_{idx}_{rng.randint(0, 999999)}.png"
        color = (rng.randint(20, 120), rng.randint(100, 180), rng.randint(40, 120))
        make_png(os.path.join(upload_dir, name), size=64, color=color)
        media["photos"].append("uploads/" + name)
    for _ in range(rng.randint(0, 2)):
        name = f"seed_v_{idx}_{rng.randint(0, 999999)}.mp4"
        make_placeholder_video(os.path.join(upload_dir, name))
        media["videos"].append("uploads/" + name)
    for _ in range(rng.randint(0, 2)):
        name = f"seed_a_{idx}_{rng.randint(0, 999999)}.mp3"
        make_placeholder_video(os.path.join(upload_dir, name))  # placeholder audio
        media["audios"].append("uploads/" + name)
    for _ in range(rng.randint(0, 2)):
        name = f"seed_d_{idx}_{rng.randint(0, 999999)}.pdf"
        with open(os.path.join(upload_dir, name), "wb") as fh:
            fh.write(b"%PDF-1.4 placeholder seed document")
        media["documents"].append("uploads/" + name)
    return media


# ---------------------------------------------------------------------------
# Data generation
# ---------------------------------------------------------------------------
def generate(count: int, keep: bool) -> None:
    db.init_db()
    os.makedirs(config.UPLOAD_DIR, exist_ok=True)

    if not keep:
        db.clear_lands()
        # remove previously seeded media, keep the folder
        for fname in os.listdir(config.UPLOAD_DIR):
            if fname.startswith("seed_"):
                try:
                    os.remove(os.path.join(config.UPLOAD_DIR, fname))
                except OSError:
                    pass

    rng = random.Random(42)
    titles = TITLES_EN + TITLES_AR
    locations = LOCATIONS_EN + LOCATIONS_AR

    for i in range(count):
        use_ar = rng.random() < 0.4
        title = rng.choice(TITLES_AR if use_ar else TITLES_EN)
        location = rng.choice(LOCATIONS_AR if use_ar else LOCATIONS_EN)
        data = {
            "title": title,
            "location": location,
            "area": round(rng.uniform(200, 50000), 2),
            "price": round(rng.uniform(5000, 2_000_000), 2),
            "owner_name": rng.choice(OWNERS),
            "description": rng.choice(DESCRIPTIONS),
        }
        media = generate_media(config.UPLOAD_DIR, i, rng)
        db.create_land(data, media)

    lands = db.get_all_lands()
    print(f"Generated {len(lands)} lands "
          f"({sum(len(l['photos']) for l in lands)} photos, "
          f"{sum(len(l['videos']) for l in lands)} videos, "
          f"{sum(len(l['audios']) for l in lands)} audios, "
          f"{sum(len(l['documents']) for l in lands)} documents).")


def main():
    parser = argparse.ArgumentParser(description="Seed the lands database.")
    parser.add_argument("--count", type=int, default=DEFAULT_COUNT,
                        help="number of lands to generate (default 120)")
    parser.add_argument("--keep", action="store_true",
                        help="append to existing data instead of clearing")
    args = parser.parse_args()
    generate(args.count, args.keep)


if __name__ == "__main__":
    main()
