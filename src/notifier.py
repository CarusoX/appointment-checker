import logging
import requests

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}"


class TelegramNotifier:
    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.api = TELEGRAM_API.format(token=bot_token)

    def send(self, message: str, reply_markup: dict | None = None):
        payload = {
            "chat_id": self.chat_id,
            "text": message,
            "parse_mode": "Markdown",
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup

        resp = requests.post(f"{self.api}/sendMessage", json=payload)
        if not resp.ok:
            logger.error(f"Telegram send failed: {resp.text}")
        return resp.ok

    def send_appointment_found(self, doctor: str, current_date: str, new_date: str,
                               new_time: str = "", appointment_id: int | None = None):
        time_str = f" a las {new_time}" if new_time else ""
        msg = (
            f"*Turno anterior encontrado!*\n\n"
            f"Doctor: {doctor}\n"
            f"Tu turno actual: {current_date}\n"
            f"Disponible: {new_date}{time_str}\n\n"
            f"[Reprogramar en el portal](https://miportal.sanatorioallende.com/auth/loginPortal)"
        )

        reply_markup = None
        if appointment_id:
            reply_markup = {
                "inline_keyboard": [[
                    {"text": "Me interesa", "callback_data": f"interested:{appointment_id}"},
                    {"text": "Ignorar turno", "callback_data": f"dismiss:{appointment_id}"},
                ]]
            }

        return self.send(msg, reply_markup=reply_markup)
