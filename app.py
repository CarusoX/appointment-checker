"""
Minimal Flask app for Render free tier.
Hit /check to trigger the appointment checker.
"""

import json
import logging
import os

from flask import Flask, jsonify

from src.checker import run_check
from src.client import SanatorioClient
from src.notifier import TelegramNotifier

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = Flask(__name__)


@app.route("/")
def health():
    return jsonify({"status": "ok"})


@app.route("/check")
def check():
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    users_json = os.getenv("USERS")

    if not users_json:
        return jsonify({"error": "USERS not configured"}), 500

    users = json.loads(users_json)
    results = []

    for user in users:
        name = user.get("name", user["dni"])
        try:
            client = SanatorioClient(user["dni"], user["password"])
            notifier = None
            if bot_token and user.get("chat_id"):
                notifier = TelegramNotifier(bot_token, user["chat_id"])

            findings = run_check(client, notifier)
            results.append({"user": name, "findings": findings})
        except Exception as e:
            logger.error(f"Error checking for {name}: {e}")
            results.append({"user": name, "error": str(e)})

    return jsonify(results)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
