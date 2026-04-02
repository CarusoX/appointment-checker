import logging
import requests

logger = logging.getLogger(__name__)


class Storage:
    def __init__(self, supabase_url: str, supabase_key: str):
        self.url = f"{supabase_url}/rest/v1"
        self.headers = {
            "apikey": supabase_key,
            "Authorization": f"Bearer {supabase_key}",
            "Content-Type": "application/json",
        }

    def get_dismissed_dates(self, chat_id: str, appointment_id: int) -> set[str]:
        """Get dismissed dates (YYYY-MM-DD) for a specific appointment."""
        resp = requests.get(
            f"{self.url}/dismissed_appointments",
            params={
                "chat_id": f"eq.{chat_id}",
                "appointment_id": f"eq.{appointment_id}",
                "select": "dismissed_date",
            },
            headers=self.headers,
        )
        if not resp.ok:
            logger.error(f"Failed to fetch dismissed: {resp.text}")
            return set()
        return {r["dismissed_date"] for r in resp.json() if r.get("dismissed_date")}

    def dismiss_date(self, chat_id: str, appointment_id: int, dismissed_date: str):
        """Dismiss a specific date (YYYY-MM-DD) for an appointment."""
        resp = requests.post(
            f"{self.url}/dismissed_appointments",
            json={
                "chat_id": str(chat_id),
                "appointment_id": appointment_id,
                "dismissed_date": dismissed_date,
            },
            headers={**self.headers, "Prefer": "return=minimal"},
        )
        if resp.status_code == 409:
            logger.debug("Already dismissed")
        elif not resp.ok:
            logger.error(f"Failed to dismiss: {resp.text}")
