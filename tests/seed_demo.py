"""Seed a full demo dataset for the Middle Atlas area:

    python tests/seed_demo.py          # 100 sellers, 100 buyers,
                                       # 150 lands (some sellers own 2-3),
                                       # 15 affairs
    python tests/seed_demo.py --keep   # append instead of clearing
"""

import argparse
import os
import random
import sys
from datetime import date, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from app import config  # noqa: E402
from app import db  # noqa: E402
from seed_data import make_png, make_placeholder_video  # noqa: E402
from seed_morocco import (  # noqa: E402
    DESCRIPTIONS, LOCATIONS, LOCATIONS_AR, TITLES_AR, TITLES_FR, generate_media,
)

FIRST_M = [
    "Mohamed", "Youssef", "Hassan", "Rachid", "Karim", "Abdellah", "Mehdi",
    "Omar", "Hamza", "Yassine", "Bilal", "Anas", "Ayoub", "Khalid", "Said",
    "Mustapha", "Driss", "Jamal", "Nabil", "Tarik",
]
FIRST_F = [
    "Fatima Zahra", "Aicha", "Khadija", "Nadia", "Salma", "Zineb", "Saida",
    "Latifa", "Meryem", "Hind", "Imane", "Souad", "Amal", "Rajae", "Hanane",
    "Samira",
]
LAST = [
    "Amrani", "Bennis", "El Fassi", "Tazi", "Sebti", "Loudiyi", "Aherdan",
    "Msguid", "Qessi", "Bahija", "Ameziane", "Berrada", "Ouahabi", "Amahrok",
    "Chraibi", "Benjelloun", "Alaoui", "Idrissi", "Sekkat", "Tahiri",
    "Zerouali", "Ghazali", "Mansouri", "Bouzidi",
]

STATUS_LAND_POOL = (
    ["Open"] * 25 + ["In Discussion"] * 20 + ["Option"] * 15
    + ["In Progress"] * 20 + ["Completed"] * 15 + ["Cancelled"] * 5
)
STATUS_AFFAIR_POOL = (
    ["Open"] * 18 + ["In Discussion"] * 18 + ["Option"] * 12
    + ["In Progress"] * 22 + ["Completed"] * 22 + ["Cancelled"] * 8
)

AFFAIR_NOTES = [
    "Visite technique effectuée, dossier en cours.",
    "Négociation du prix en cours avec le propriétaire.",
    "Accord verbal, attente du compromis signé.",
    "Dossier administratif complet chez le notaire.",
    "Vente finalisée, acte signé et payé.",
    "",
]


def make_names(rng: random.Random, used: set, n: int) -> list:
    names = []
    while len(names) < n:
        gender_f = rng.random() < 0.45
        first = rng.choice(FIRST_F if gender_f else FIRST_M)
        full = f"{first} {rng.choice(LAST)}"
        if full in used:
            full = f"{full} {rng.choice(['El', 'Bin', 'Ou'])} {rng.choice(LAST)}"
        if full in used:
            continue
        used.add(full)
        names.append(full)
    return names


def party_data(name: str, idx: int, rng: random.Random, towns) -> dict:
    email = None
    if rng.random() < 0.55:
        slug = name.lower().replace(" ", ".").replace("'", "")
        email = f"{slug}{idx}@example.ma"
    return {
        "full_name": name,
        "email": email,
        "phone": "+2126" + f"{rng.randint(0, 99999999):08d}",
        "address": rng.choice(towns),
        "notes": rng.choice(["Client sérieux.", None, None, None]),
    }


def generate(keep: bool) -> None:
    db.init_db()
    os.makedirs(config.UPLOAD_DIR, exist_ok=True)
    if not keep:
        db.clear_all()
        for fname in os.listdir(config.UPLOAD_DIR):
            if fname.startswith(("ma_", "dm_")):
                try:
                    os.remove(os.path.join(config.UPLOAD_DIR, fname))
                except OSError:
                    pass

    rng = random.Random(2026)
    towns = LOCATIONS + LOCATIONS_AR

    # --- parties ------------------------------------------------------------
    used = set()
    seller_ids = []
    for i, name in enumerate(make_names(rng, used, 100)):
        seller_ids.append(db.create_party("seller", party_data(name, i, rng, towns)))
    customer_ids = []
    for i, name in enumerate(make_names(rng, used, 100)):
        customer_ids.append(db.create_party("customer", party_data(name, i, rng, towns)))

    # --- lands: 60x1 + 30x2 + 10x3 = 150 over all 100 sellers ---------------
    plan = [1] * 60 + [2] * 30 + [3] * 10
    owners = seller_ids[:]
    rng.shuffle(owners)
    for sid, n in zip(owners, plan):
        seller = db.get_party("seller", sid)
        for _ in range(n):
            use_ar = rng.random() < 0.5
            data = {
                "title": rng.choice(TITLES_AR if use_ar else TITLES_FR),
                "location": rng.choice(LOCATIONS_AR if use_ar else LOCATIONS),
                "area": round(rng.uniform(200, 50000), 2),
                "price": round(rng.uniform(50_000, 5_000_000), 2),
                "owner_name": seller["full_name"],
                "description": rng.choice(DESCRIPTIONS),
                "status": rng.choice(STATUS_LAND_POOL),
                "seller_id": sid,
            }
            db.create_land(data, generate_media(config.UPLOAD_DIR, sid * 100 + len(owners), rng))

    # --- affairs -------------------------------------------------------------
    lands = [l for l in db.get_all_lands() if l["seller_id"]]
    for land in rng.sample(lands, 15):
        status = rng.choice(STATUS_AFFAIR_POOL)
        agreed = round(land["price"] * rng.uniform(0.9, 1.06), 2)
        closing = None
        if status in ("Open", "In Discussion", "Option", "In Progress"):
            closing = (date.today() + timedelta(days=rng.randint(15, 180))).isoformat()
        elif status == "Completed":
            closing = (date.today() - timedelta(days=rng.randint(10, 90))).isoformat()
        db.create_affair({
            "ref": None,
            "seller_id": land["seller_id"],
            "land_id": land["id"],
            "buyer_id": rng.choice(customer_ids),
            "status": status,
            "agreed_price": agreed,
            "deposit": round(agreed * rng.uniform(0.05, 0.10), 2) if status != "Cancelled" else None,
            "commission": round(agreed * 0.025, 2),
            "closing_date": closing,
            "notes": rng.choice(AFFAIR_NOTES),
        })

    print(f"Sellers: {len(db.get_all_parties('seller'))}, "
          f"Buyers: {len(db.get_all_parties('customer'))}, "
          f"Lands: {len(db.get_all_lands())}, "
          f"Affairs: {len(db.get_all_affairs())}")


def main():
    parser = argparse.ArgumentParser(description="Seed full demo dataset.")
    parser.add_argument("--keep", action="store_true",
                        help="append to existing data instead of clearing")
    args = parser.parse_args()
    generate(args.keep)


if __name__ == "__main__":
    main()
