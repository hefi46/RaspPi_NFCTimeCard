"""
First-run setup script — creates an initial admin user.

Usage:
    python scripts/seed.py --name "Admin" --email admin@local.com --password changeme

Run once on a fresh database.  Safe to re-run (skips existing emails).
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import bcrypt
from src.config import load_config
from src.database import connect, init_db, create_user, get_user_by_email


def seed(name: str, email: str, password: str) -> None:
    config = load_config()

    db_dir = os.path.dirname(config.database.path)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)

    conn = connect(config.database.path)
    init_db(conn)

    email = email.strip().lower()

    if get_user_by_email(conn, email):
        print(f"User {email} already exists — skipping.")
        return

    pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    user_id = create_user(conn, name.strip(), email, pw_hash, role="admin")
    print(f"Admin created: {name} <{email}>  (id={user_id})")
    print(f"Database: {config.database.path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed initial admin user")
    parser.add_argument("--name",     required=True, help="Full name")
    parser.add_argument("--email",    required=True, help="Login email")
    parser.add_argument("--password", required=True, help="Login password")
    args = parser.parse_args()
    seed(args.name, args.email, args.password)
