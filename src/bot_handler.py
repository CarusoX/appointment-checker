import logging
import threading
import time

import requests

from src.client import SanatorioClient
from src.crypto import encrypt_password
from src.storage import Storage

logger = logging.getLogger(__name__)

# In-memory conversation state: {chat_id: {"step": ..., "dni": ..., "timestamp": ...}}
_conversations: dict[str, dict] = {}

STATE_TIMEOUT = 300  # 5 minutes


def _send_message(bot_token: str, chat_id: str, text: str):
    resp = requests.post(
        f"https://api.telegram.org/bot{bot_token}/sendMessage",
        json={"chat_id": chat_id, "text": text},
    )
    if not resp.ok:
        logger.error(f"Failed to send message: {resp.text}")


def _delete_message(bot_token: str, chat_id: str, message_id: int):
    resp = requests.post(
        f"https://api.telegram.org/bot{bot_token}/deleteMessage",
        json={"chat_id": chat_id, "message_id": message_id},
    )
    if not resp.ok:
        logger.debug(f"Failed to delete message: {resp.text}")


def handle_update(update: dict, storage: Storage, bot_token: str,
                  encryption_key: str):
    message = update.get("message")
    if not message or "text" not in message:
        return

    chat_id = str(message["chat"]["id"])
    text = message["text"].strip()
    message_id = message["message_id"]
    first_name = message["chat"].get("first_name", "")

    # Check for stale conversation state
    if chat_id in _conversations:
        if time.time() - _conversations[chat_id]["timestamp"] > STATE_TIMEOUT:
            del _conversations[chat_id]

    # Command dispatch
    if text.startswith("/agregar"):
        _conversations[chat_id] = {"step": "awaiting_dni", "timestamp": time.time()}
        _send_message(bot_token, chat_id, "Ingresa tu DNI (solo numeros):")
        return

    if text.startswith("/eliminar"):
        users = storage.get_users_by_chat(chat_id)
        if not users:
            _send_message(bot_token, chat_id,
                          "No hay cuentas registradas. Usa /agregar para registrarte.")
            return
        # /eliminar <DNI> — delete specific account
        parts = text.split()
        if len(parts) >= 2:
            dni = parts[1].replace(".", "").replace(" ", "")
            if any(u["dni"] == dni for u in users):
                storage.delete_user(chat_id, dni)
                _send_message(bot_token, chat_id,
                              f"Cuenta con DNI {dni} eliminada.")
            else:
                _send_message(bot_token, chat_id,
                              f"No tenes una cuenta con DNI {dni}.")
            return
        # /eliminar without args
        if len(users) == 1:
            storage.delete_user(chat_id, users[0]["dni"])
            _send_message(bot_token, chat_id,
                          "Tu cuenta fue eliminada. Podes volver a registrarte con /agregar.")
        else:
            lines = ["Tenes varias cuentas. Indica cual eliminar:"]
            for u in users:
                dni = u["dni"]
                masked = dni[:2] + "*" * (len(dni) - 4) + dni[-2:]
                lines.append(f"  /eliminar {dni}  ({masked})")
            _send_message(bot_token, chat_id, "\n".join(lines))
        return

    if text.startswith("/estado"):
        users = storage.get_users_by_chat(chat_id)
        if not users:
            _send_message(bot_token, chat_id,
                          "No hay cuentas registradas. Usa /agregar para registrarte.")
        elif len(users) == 1:
            dni = users[0]["dni"]
            masked = dni[:2] + "*" * (len(dni) - 4) + dni[-2:]
            _send_message(bot_token, chat_id, f"Registrado con DNI: {masked}")
        else:
            lines = ["Cuentas registradas:"]
            for u in users:
                dni = u["dni"]
                masked = dni[:2] + "*" * (len(dni) - 4) + dni[-2:]
                name = u.get("name") or ""
                lines.append(f"  {masked}" + (f" ({name})" if name else ""))
            _send_message(bot_token, chat_id, "\n".join(lines))
        return

    if text.startswith("/ayuda") or text.startswith("/start") or text.startswith("/help"):
        _send_message(bot_token, chat_id,
                      "Comandos disponibles:\n"
                      "/agregar — Registrar tu cuenta del portal\n"
                      "/eliminar — Eliminar tu cuenta\n"
                      "/estado — Ver tu estado de registro")
        return

    # Handle conversation steps
    state = _conversations.get(chat_id)
    if not state:
        return

    if state["step"] == "awaiting_dni":
        dni = text.replace(".", "").replace(" ", "")
        if not dni.isdigit():
            _send_message(bot_token, chat_id, "El DNI debe ser solo numeros. Intenta de nuevo:")
            return
        _delete_message(bot_token, chat_id, message_id)
        state["dni"] = dni
        state["step"] = "awaiting_password"
        state["timestamp"] = time.time()
        _send_message(bot_token, chat_id, "Ingresa tu contrasena del portal:")
        return

    if state["step"] == "awaiting_password":
        raw_password = text
        dni = state["dni"]
        del _conversations[chat_id]

        # Delete the password message from chat
        _delete_message(bot_token, chat_id, message_id)

        # Validate and store in background so the webhook responds fast
        threading.Thread(
            target=_validate_and_store,
            args=(bot_token, chat_id, dni, raw_password, encryption_key,
                  storage, first_name),
            daemon=True,
        ).start()


def _validate_and_store(bot_token: str, chat_id: str, dni: str,
                        raw_password: str, encryption_key: str,
                        storage: Storage, name: str):
    _send_message(bot_token, chat_id, "Verificando credenciales...")
    try:
        client = SanatorioClient(dni, raw_password)
        client.login()
    except Exception:
        _send_message(bot_token, chat_id,
                      "Credenciales invalidas. Verifica tu DNI y contrasena "
                      "e intenta de nuevo con /agregar")
        return

    encrypted = encrypt_password(raw_password, encryption_key)
    storage.upsert_user(chat_id, dni, encrypted, name=name or None)

    _send_message(bot_token, chat_id,
                  "Registrado! Voy a revisar tus turnos periodicamente "
                  "y te aviso si hay turnos mas tempranos.")
