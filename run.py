"""Run the Middle Atlas Real Estate app.

Locally:  python run.py
On a host: set PORT (and optionally FLASK_DEBUG=1 for development).
"""
import os

from app import app

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(host="0.0.0.0", port=port, debug=debug)
