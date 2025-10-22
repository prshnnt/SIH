import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

import json
from testdb.db_setup import get_db
from testdb import crud
from testdb.schemas import UserSchema
from sqlalchemy.orm import Session
from pydantic import ValidationError

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "fetched_users.json"

def push_data_to_db():
    if not DATA_FILE.exists():
        print("❌ No fetched data found. Run fetch/fetch_data.py first.")
        return

    with open(DATA_FILE, "r", encoding="utf-8") as f:
        users = json.load(f)

    db_gen = get_db()
    db: Session = next(db_gen)

    for user_dict in users:
        try:
            user_obj = UserSchema(
                name=user_dict.get("name"),
                email=user_dict.get("email"),
                username=user_dict.get("username")
            )
            crud.add_user(db, user_obj)
            print(f"✅ Added user: {user_obj.name}")
        except ValidationError as ve:
            print(f"⚠️ Validation failed for record: {user_dict}\n{ve}")
        except Exception as e:
            print(f"⚠️ Could not insert user: {e}")

    db_gen.close()
    print("✅ All valid users inserted into DB.")

if __name__ == "__main__":
    push_data_to_db()
