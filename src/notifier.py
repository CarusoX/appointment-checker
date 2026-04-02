import logging
from datetime import date

import requests

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}"

DIAS = ["Lun", "Mar", "Mie", "Jue", "Vie", "Sab", "Dom"]


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

    def send_available_slots(self, doctor: str, service: str, location: str,
                             current_date: date, current_time: str,
                             available_days: list[dict],
                             appointment_id: int):
        """Send notification with all available earlier slots grouped by day.

        available_days: list of {'date': 'YYYY-MM-DD', 'times': ['HH:MM', ...]}
        """
        lines = [
            f"*Turnos anteriores disponibles!*\n",
            f"Doctor: {doctor}",
            f"{service} @ {location}",
            f"Tu turno actual: {current_date.strftime('%d/%m/%Y')} {current_time}",
            "",
        ]

        for day in available_days:
            d = date.fromisoformat(day["date"])
            dia = DIAS[d.weekday()]
            fecha_str = d.strftime("%d/%m")
            times_str = ", ".join(day["times"])
            lines.append(f"{dia} {fecha_str} — {times_str}")

        lines.append("")
        lines.append(
            "[Reprogramar en el portal]"
            "(https://miportal.sanatorioallende.com/auth/loginPortal)"
        )

        msg = "\n".join(lines)

        # Encode all dates into callback data: "d:{appt_id}:{date1},{date2},..."
        all_dates = ",".join(day["date"] for day in available_days)
        reply_markup = {
            "inline_keyboard": [[
                {"text": "Ignorar turnos", "callback_data": f"d:{appointment_id}:{all_dates}"},
            ]]
        }
        return self.send(msg, reply_markup=reply_markup)
