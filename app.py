"""
Flask app for Render free tier.
/check — triggers the appointment checker
/telegram-webhook — handles Telegram button callbacks
/setup-webhook — one-time setup for Telegram webhook
"""

import json
import logging
import os

import requests as http_requests
from flask import Flask, jsonify, request

from src.checker import run_check
from src.client import SanatorioClient
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
    users_json = os.getenv("USERS")
    dry = request.args.get("dry") == "true"

    if not users_json:
        return jsonify({"error": "USERS not configured"}), 500

    users = json.loads(users_json)
    storage = get_storage()
    results = []

    for user in users:
        name = user.get("name", user["dni"])
        try:
            client = SanatorioClient(user["dni"], user["password"])

            notifier = None
            if not dry and bot_token and user.get("chat_id"):
                notifier = TelegramNotifier(bot_token, user["chat_id"])

            findings = run_check(client, notifier, storage)
            results.append({"user": name, "findings": findings})
        except Exception as e:
            logger.error(f"Error checking for {name}: {e}")
            results.append({"user": name, "error": str(e)})

    return jsonify(results)


@app.route("/telegram-webhook", methods=["POST"])
def telegram_webhook():
    data = request.json
    callback = data.get("callback_query")
    if not callback:
        return jsonify({"ok": True})

    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    api = f"https://api.telegram.org/bot{bot_token}"

    callback_id = callback["id"]
    chat_id = str(callback["message"]["chat"]["id"])
    message_id = callback["message"]["message_id"]
    callback_data = callback.get("data", "")

    # Format: "d:{appt_id}:{date1},{date2},..."
    parts = callback_data.split(":", 2)
    if len(parts) < 3 or parts[0] != "d":
        return jsonify({"ok": True})

    appt_id = int(parts[1])
    dates = parts[2].split(",")

    storage = get_storage()
    if storage:
        for dismissed_date in dates:
            storage.dismiss_date(chat_id, appt_id, dismissed_date)

    http_requests.post(f"{api}/answerCallbackQuery", json={
        "callback_query_id": callback_id,
        "text": "Ignorado. No se notificara mas sobre estas fechas.",
    })

    # Update message to show it was dismissed, remove buttons
    original_text = callback["message"].get("text", "")
    http_requests.post(f"{api}/editMessageText", json={
        "chat_id": chat_id,
        "message_id": message_id,
        "text": original_text + "\n\n~Ignorado~",
        "parse_mode": "Markdown",
    })

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
