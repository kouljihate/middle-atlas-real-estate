"""Clean ALL data: empties the lands, customers and sellers tables and removes
every uploaded media file. Run from the project root:

    python tests/clean_data.py
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from app import config  # noqa: E402
from app import db  # noqa: E402


def main() -> None:
    db.init_db()
    db.clear_all()

    removed = 0
    if os.path.isdir(config.UPLOAD_DIR):
        for fname in os.listdir(config.UPLOAD_DIR):
            path = os.path.join(config.UPLOAD_DIR, fname)
            try:
                if os.path.isfile(path):
                    os.remove(path)
                    removed += 1
            except OSError:
                pass

    print(f"All data cleared. Removed {removed} uploaded file(s).")


if __name__ == "__main__":
    main()
