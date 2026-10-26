#!/usr/bin/env python3
"""Safely create/reset a Guild-Glory dashboard admin password locally."""
import getpass
import hashlib
import json
import os
import re
import secrets
import sys
import time

USERS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "users.json")

def normalize(value):
    return str(value).strip().lower().replace(" ", "_")

def password_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100_000)
    return f"{salt}${digest.hex()}"

def main():
    username = normalize(input("Admin username [admin]: ") or "admin")
    if len(username) < 3 or len(username) > 20 or not re.fullmatch(r"[a-z0-9_]+", username):
        print("Invalid username: use 3-20 letters, digits, or underscores.", file=sys.stderr)
        return 2
    password = getpass.getpass("New admin password (minimum 8 characters): ")
    confirm = getpass.getpass("Confirm new password: ")
    if len(password) < 8:
        print("Password must be at least 8 characters.", file=sys.stderr)
        return 2
    if password != confirm:
        print("Passwords do not match.", file=sys.stderr)
        return 2
    try:
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            users = json.load(f)
        if not isinstance(users, dict):
            users = {}
    except FileNotFoundError:
        users = {}
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Cannot read users.json: {exc}", file=sys.stderr)
        return 1

    old = users.get(username, {})
    old.update({
        "username": username,
        "display_name": str(old.get("display_name") or username.replace("_", " ").upper()),
        "password_hash": password_hash(password),
        "role": "admin",
        "basic_credits": int(old.get("basic_credits", 0) or 0),
        "premium_credits": int(old.get("premium_credits", 0) or 0),
        "created_at": old.get("created_at", time.time()),
        "password_reset_at": time.time(),
    })
    users[username] = old
    temp = USERS_FILE + ".tmp"
    with open(temp, "w", encoding="utf-8") as f:
        json.dump(users, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(temp, USERS_FILE)
    print(f"Admin password updated for '{username}'. Restart the server and log in at /login.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
