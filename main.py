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
from src.notifier import TelegramNotifier
from src.storage import Storage

load_dotenv()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def main():
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    users_json = os.getenv("USERS")
    dry = "--dry" in sys.argv

    if not users_json:
        print("Set USERS in .env (JSON array). See .env.example")
        sys.exit(1)

    users = json.loads(users_json)

    storage = None
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_KEY")
    if supabase_url and supabase_key:
        storage = Storage(supabase_url, supabase_key)

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
