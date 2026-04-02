"""
Flask app for Render free tier.
/check — triggers the appointment checker
/telegram-webhook — handles Telegram bot commands and registration
/setup-webhook — one-time setup for Telegram webhook
"""

import logging
import os

import requests as http_requests
from flask import Flask, jsonify, request

from src.bot_handler import handle_update
from src.checker import run_check
from src.client import SanatorioClient
from src.crypto import decrypt_password
from src.notifier import TelegramNotifier
from src.storage import Storage

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = Flask(__name__)


def get_storage() -> Storage | None:
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    if url and key:
        return Storage(url, key)
    return None


@app.route("/")
def health():
    return jsonify({"status": "ok"})


@app.route("/check")
def check():
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    encryption_key = os.getenv("ENCRYPTION_KEY")
    dry = request.args.get("dry") == "true"
    storage = get_storage()

    if not storage or not encryption_key:
        return jsonify({"error": "Storage or encryption not configured"}), 500

    users = storage.get_all_users()
    results = []

    for user in users:
        chat_id = user["chat_id"]
        dni = user["dni"]
        name = user.get("name") or dni

        try:
            raw_password = decrypt_password(user["encrypted_password"], encryption_key)
            client = SanatorioClient(dni, raw_password)

            notifier = None
            if not dry and bot_token:
                notifier = TelegramNotifier(bot_token, chat_id, storage)

            findings = run_check(client, notifier, storage)
            results.append({"user": name, "findings": findings})
        except Exception as e:
            logger.error(f"Error checking for {name}: {e}")
            results.append({"user": name, "error": str(e)})

    return jsonify(results)


@app.route("/telegram-webhook", methods=["POST"])
def telegram_webhook():
    update = request.get_json(silent=True)
    if not update:
        return jsonify({"ok": True})

    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    encryption_key = os.getenv("ENCRYPTION_KEY")
    storage = get_storage()

    logger.info(f"Webhook update: {update}")

    if not bot_token or not encryption_key or not storage:
        logger.error(f"Missing config: bot_token={bool(bot_token)}, encryption_key={bool(encryption_key)}, storage={bool(storage)}")
        return jsonify({"ok": True})

    try:
        handle_update(update, storage, bot_token, encryption_key)
    except Exception:
        logger.exception("Webhook error")

    return jsonify({"ok": True})


@app.route("/setup-webhook")
def setup_webhook():
    """Call once to register the Telegram webhook."""
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        return jsonify({"error": "TELEGRAM_BOT_TOKEN not set"}), 500

    # Derive the public URL from the request
    webhook_url = request.url_root.rstrip("/") + "/telegram-webhook"

    resp = http_requests.post(
        f"https://api.telegram.org/bot{bot_token}/setWebhook",
        json={"url": webhook_url},
    )
    return jsonify(resp.json())


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
