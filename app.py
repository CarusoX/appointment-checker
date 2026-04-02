"""
Flask app for Render free tier.
/check — triggers the appointment checker
/telegram-webhook — handles Telegram bot commands and registration
/setup-webhook — one-time setup for Telegram webhook
"""

import logging
import os
import secrets

import requests as http_requests
from flask import Flask, jsonify, request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

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

limiter = Limiter(get_remote_address, app=app, default_limits=["60 per minute"])


@app.after_request
def set_security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Content-Security-Policy"] = "default-src 'none'"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


def _check_cron_secret() -> bool:
    """Verify the request carries the correct CRON_SECRET."""
    cron_secret = os.getenv("CRON_SECRET")
    if not cron_secret:
        return False
    provided = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    if not provided:
        provided = request.args.get("secret", "")
    return secrets.compare_digest(provided, cron_secret)


def get_storage() -> Storage | None:
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_KEY")
    if url and key:
        return Storage(url, key)
    return None


@app.route("/")
def health():
    return jsonify({"status": "ok"})


@app.route("/check")
@limiter.limit("6 per hour")
def check():
    if not _check_cron_secret():
        return jsonify({"error": "Unauthorized"}), 401

    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    encryption_key = os.getenv("ENCRYPTION_KEY")
    dry = request.args.get("dry") == "true"
    storage = get_storage()

    if not storage or not encryption_key:
        return jsonify({"error": "Not configured"}), 500

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
            results.append({"user": name, "checked": True, "count": len(findings)})
        except Exception:
            logger.exception(f"Error checking for {name}")
            results.append({"user": name, "checked": False})

    return jsonify(results)


@app.route("/telegram-webhook", methods=["POST"])
@limiter.limit("30 per minute")
def telegram_webhook():
    # Verify Telegram secret token
    webhook_secret = os.getenv("TELEGRAM_WEBHOOK_SECRET")
    if webhook_secret:
        provided = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if not secrets.compare_digest(provided, webhook_secret):
            return jsonify({"ok": False}), 403

    update = request.get_json(silent=True)
    if not update:
        return jsonify({"ok": True})

    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    encryption_key = os.getenv("ENCRYPTION_KEY")
    storage = get_storage()

    # Log update type without message content (avoids logging passwords)
    update_type = "callback_query" if "callback_query" in update else "message" if "message" in update else "other"
    logger.info(f"Webhook update: type={update_type}, update_id={update.get('update_id')}")

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
    """Call once to register the Telegram webhook. Requires CRON_SECRET."""
    if not _check_cron_secret():
        return jsonify({"error": "Unauthorized"}), 401

    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        return jsonify({"error": "Not configured"}), 500

    base_url = os.getenv("WEBHOOK_BASE_URL")
    if not base_url:
        return jsonify({"error": "WEBHOOK_BASE_URL not set"}), 500

    webhook_url = base_url.rstrip("/") + "/telegram-webhook"
    webhook_secret = os.getenv("TELEGRAM_WEBHOOK_SECRET")

    payload = {"url": webhook_url}
    if webhook_secret:
        payload["secret_token"] = webhook_secret

    resp = http_requests.post(
        f"https://api.telegram.org/bot{bot_token}/setWebhook",
        json=payload,
    )
    result = resp.json()
    return jsonify({"ok": result.get("ok"), "description": result.get("description")})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
