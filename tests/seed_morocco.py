"""Seed 100 lands around the Sefrou / El Menzel (Al Manzel) / Tazouta area
in Morocco. Clears existing lands by default.

    python tests/seed_morocco.py            # 100 Moroccan lands
    python tests/seed_morocco.py --count 100
    python tests/seed_morocco.py --keep     # append instead of clearing
"""

import argparse
import os
import random
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from app import config  # noqa: E402
from app import db  # noqa: E402
from seed_data import make_png, make_placeholder_video  # noqa: E402

DEFAULT_COUNT = 100

# Area + nearby communes around Sefrou (Fès-Meknès, Morocco).
LOCATIONS = [
    "Sefrou", "El Menzel", "Tazouta", "Ain Cheggag", "Imouzzer Kandar",
    "Ribat El Kheir", "Bhalil", "Aghbalou", "Sidi El Makhfi", "Ras El Ma",
    "Sefrou - Oulad Mbarek", "El Menzel - Ait Youssi", "Tazouta - Ait Slimane",
]
LOCATIONS_AR = [
    "صفرو", "المنزل", "تازوطة", "عين الشقاق", "إيموزار كندر",
    "رباط الخير", "بوحللب", "أغبالو", "سيدي المخفي", "رأس الماء",
]

# Land titles (French + Arabic mix, as commonly used in Morocco).
TITLES_FR = [
    "Terrain agricole", "Ferme", "Parcelle de construction", "Verger",
    "Oliveraie", "Terrain bord de route", "Exploitation agricole", "Bas de colonia",
]
TITLES_AR = [
    "أرض فلاحية", "ضيعة فلاحية", "بقعة أرضية للبناء", "بستان", "حقل زيتون",
    "ضيعة", "أرض غابوية", "حقل حبوب",
]

OWNERS = [
    "Mohamed Amrani", "Fatima Zahra Bennis", "Youssef El Fassi", "Aicha Tazi",
    "Omar Sebti", "Nadia Loudiyi", "Hassan Aherdan", "Khadija Msguid",
    "Rachid Qessi", "Salma Bahija", "Abdellah Fassi", "Zineb Ameziane",
    "Mehdi Berrada", "Saida Ouahabi", "Karim Sebti", "Latifa Amahrok",
]

DESCRIPTIONS = [
    "Terrain plat, sol fertile, proche de la route principale.",
    "Parcelle avec puits et accès facile, idéale pour l'agriculture.",
    "Situé en bordure de la route, raccordement électricité possible.",
    "Zone calme, vue sur le Moyen Atlas, terrain clôturé.",
    "Convient pour oliviers et arboriculture, eau d'irrigation disponible.",
    "Proche du centre de Sefrou, toutes commodités à proximité.",
    "",
]


def generate_media(upload_dir: str, idx: int, rng: random.Random) -> dict:
    media = {"photos": [], "videos": [], "audios": [], "documents": []}
    for _ in range(rng.randint(0, 3)):
        name = f"ma_p_{idx}_{rng.randint(0, 999999)}.png"
        color = (rng.randint(20, 120), rng.randint(100, 180), rng.randint(40, 120))
        make_png(os.path.join(upload_dir, name), size=64, color=color)
        media["photos"].append("uploads/" + name)
    for _ in range(rng.randint(0, 2)):
        name = f"ma_v_{idx}_{rng.randint(0, 999999)}.mp4"
        make_placeholder_video(os.path.join(upload_dir, name))
        media["videos"].append("uploads/" + name)
    for _ in range(rng.randint(0, 2)):
        name = f"ma_a_{idx}_{rng.randint(0, 999999)}.mp3"
        make_placeholder_video(os.path.join(upload_dir, name))
        media["audios"].append("uploads/" + name)
    for _ in range(rng.randint(0, 2)):
        name = f"ma_d_{idx}_{rng.randint(0, 999999)}.pdf"
        with open(os.path.join(upload_dir, name), "wb") as fh:
            fh.write(b"%PDF-1.4 placeholder document")
        media["documents"].append("uploads/" + name)
    return media


def generate(count: int, keep: bool) -> None:
    db.init_db()
    os.makedirs(config.UPLOAD_DIR, exist_ok=True)

    if not keep:
        db.clear_lands()
        for fname in os.listdir(config.UPLOAD_DIR):
            if fname.startswith("ma_"):
                try:
                    os.remove(os.path.join(config.UPLOAD_DIR, fname))
                except OSError:
                    pass

    rng = random.Random(2026)
    for i in range(count):
        use_ar = rng.random() < 0.5
        title = rng.choice(TITLES_AR if use_ar else TITLES_FR)
        location = rng.choice(LOCATIONS_AR if use_ar else LOCATIONS)
        data = {
            "title": title,
            "location": location,
            "area": round(rng.uniform(200, 50000), 2),
            "price": round(rng.uniform(50000, 5_000_000), 2),  # MAD
            "owner_name": rng.choice(OWNERS),
            "description": rng.choice(DESCRIPTIONS),
        }
        media = generate_media(config.UPLOAD_DIR, i, rng)
        db.create_land(data, media)

    lands = db.get_all_lands()
    print(f"Generated {len(lands)} Moroccan lands "
          f"({sum(len(l['photos']) for l in lands)} photos, "
          f"{sum(len(l['videos']) for l in lands)} videos, "
          f"{sum(len(l['audios']) for l in lands)} audios, "
          f"{sum(len(l['documents']) for l in lands)} documents).")


def main():
    parser = argparse.ArgumentParser(description="Seed Moroccan lands near Sefrou.")
    parser.add_argument("--count", type=int, default=DEFAULT_COUNT,
                        help="number of lands to generate (default 100)")
    parser.add_argument("--keep", action="store_true",
                        help="append to existing data instead of clearing")
    args = parser.parse_args()
    generate(args.count, args.keep)


if __name__ == "__main__":
    main()
