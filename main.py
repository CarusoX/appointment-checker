"""
Appointment checker — finds earlier slots for your existing appointments.

Usage:
    python main.py          # run a check for all users
    python main.py --dry    # check without sending Telegram notifications
"""

import json
import logging
import os
import sys

from dotenv import load_dotenv

from src.checker import run_check
from src.client import SanatorioClient
from src.crypto import decrypt_password
from src.notifier import TelegramNotifier
from src.storage import Storage

load_dotenv()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def load_users(storage: Storage | None) -> list[dict]:
    """Load users from USERS env var (legacy) or Supabase."""
    users_json = os.getenv("USERS")
    if users_json:
        return json.loads(users_json)

    encryption_key = os.getenv("ENCRYPTION_KEY")
    if storage and encryption_key:
        db_users = storage.get_all_users()
        return [
            {
                "name": u.get("name") or u["dni"],
                "dni": u["dni"],
                "password": decrypt_password(u["encrypted_password"], encryption_key),
                "chat_id": u["chat_id"],
            }
            for u in db_users
        ]

    print("Set USERS in .env or configure SUPABASE + ENCRYPTION_KEY")
    sys.exit(1)


def main():
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    dry = "--dry" in sys.argv

    storage = None
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_KEY")
    if supabase_url and supabase_key:
        storage = Storage(supabase_url, supabase_key)

    users = load_users(storage)

    for user in users:
        name = user.get("name", user["dni"])
        logger.info(f"{'='*40}")
        logger.info(f"Checking for: {name}")
        logger.info(f"{'='*40}")

        try:
            client = SanatorioClient(user["dni"], user["password"])

            notifier = None
            if not dry and bot_token and user.get("chat_id"):
                notifier = TelegramNotifier(bot_token, user["chat_id"], storage)

            findings = run_check(client, notifier, storage)

            if findings:
                print(f"\n{name}: Found {len(findings)} earlier slot(s):")
                for f in findings:
                    days = f["available_days"]
                    days_str = ", ".join(f"{d['date']} ({', '.join(d['times'])})" for d in days)
                    print(f"  {f['doctor']}: current {f['current_date']} -> {days_str}")
            else:
                print(f"{name}: No earlier appointments available right now.")

        except Exception as e:
            logger.error(f"Error checking for {name}: {e}")


if __name__ == "__main__":
    main()
