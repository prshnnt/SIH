import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

import requests
import json

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)
DATA_FILE = DATA_DIR / "fetched_users.json"

def fetch_external_data():
    """Fetch users from placeholder API and save as JSON."""
    res = requests.get("https://jsonplaceholder.typicode.com/users")
    res.raise_for_status()
    users = res.json()

    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, indent=4)
    print(f"✅ Saved {len(users)} users to {DATA_FILE}")

if __name__ == "__main__":
    fetch_external_data()
