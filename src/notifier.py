import logging
import requests

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}"


class TelegramNotifier:
    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.api = TELEGRAM_API.format(token=bot_token)

    def send(self, message: str):
        resp = requests.post(
            f"{self.api}/sendMessage",
            json={
                "chat_id": self.chat_id,
                "text": message,
                "parse_mode": "Markdown",
            },
        )
        if not resp.ok:
            logger.error(f"Telegram send failed: {resp.text}")
        return resp.ok

    def send_appointment_found(self, doctor: str, current_date: str, new_date: str, new_time: str = ""):
        time_str = f" at {new_time}" if new_time else ""
        msg = (
            f"*Earlier appointment found!*\n\n"
            f"Doctor: {doctor}\n"
            f"Your current date: {current_date}\n"
            f"Available date: {new_date}{time_str}\n\n"
            f"Log in to reschedule: https://miportal.sanatorioallende.com/auth/loginPortal"
        )
        return self.send(msg)
