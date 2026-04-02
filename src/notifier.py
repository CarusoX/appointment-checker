import logging
from datetime import date

import requests

from src.storage import Storage

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}"

DIAS = ["Lun", "Mar", "Mie", "Jue", "Vie", "Sab", "Dom"]


class TelegramNotifier:
    def __init__(self, bot_token: str, chat_id: str, storage: Storage | None = None):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.storage = storage
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
                             appointment_id: int,
                             patient_name: str = ""):
        """Send notification with all available earlier slots grouped by day.

        available_days: list of {'date': 'YYYY-MM-DD', 'times': ['HH:MM', ...]}
        """
        lines = [
            f"*Turnos anteriores disponibles!*\n",
        ]
        if patient_name:
            lines.append(f"Paciente: {patient_name}")
        lines.append(f"Doctor: {doctor}")
            f"{service} @ {location}",
            f"Tu turno actual: {current_date.strftime('%d/%m/%Y')} {current_time}",
            "",
        ]

        for day in available_days:
            d = date.fromisoformat(day["date"])
            dia = DIAS[d.weekday()]
            fecha_str = d.strftime("%d/%m")
            hours = sorted(set(t.split(":")[0] for t in day["times"]))
            if len(hours) == 1:
                lines.append(f"{dia} {fecha_str} — {hours[0]}hs")
            else:
                lines.append(f"{dia} {fecha_str} — {hours[0]} a {hours[-1]}hs")

        lines.append("")
        lines.append(
            "[Reprogramar en el portal]"
            "(https://miportal.sanatorioallende.com/auth/loginPortal)"
        )

        msg = "\n".join(lines)

        # Pre-dismiss all shown dates so they won't re-notify
        if self.storage:
            for day in available_days:
                self.storage.dismiss_date(self.chat_id, appointment_id, day["date"])

        return self.send(msg)
