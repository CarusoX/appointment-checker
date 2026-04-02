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

    # ── User management ──

    def get_all_users(self) -> list[dict]:
        resp = requests.get(
            f"{self.url}/users",
            params={"select": "chat_id,dni,encrypted_password,name"},
            headers=self.headers,
        )
        if not resp.ok:
            logger.error(f"Failed to fetch users: {resp.text}")
            return []
        return resp.json()

    def get_user(self, chat_id: str) -> dict | None:
        resp = requests.get(
            f"{self.url}/users",
            params={"chat_id": f"eq.{chat_id}", "select": "*"},
            headers=self.headers,
        )
        if not resp.ok:
            logger.error(f"Failed to fetch user: {resp.text}")
            return None
        rows = resp.json()
        return rows[0] if rows else None

    def upsert_user(self, chat_id: str, dni: str, encrypted_password: str,
                    name: str | None = None):
        resp = requests.post(
            f"{self.url}/users",
            json={
                "chat_id": chat_id,
                "dni": dni,
                "encrypted_password": encrypted_password,
                "name": name,
            },
            headers={
                **self.headers,
                "Prefer": "resolution=merge-duplicates,return=minimal",
            },
        )
        if not resp.ok:
            logger.error(f"Failed to upsert user: {resp.text}")

    def delete_user(self, chat_id: str) -> bool:
        resp = requests.delete(
            f"{self.url}/users",
            params={"chat_id": f"eq.{chat_id}"},
            headers=self.headers,
        )
        if not resp.ok:
            logger.error(f"Failed to delete user: {resp.text}")
            return False
        return True
