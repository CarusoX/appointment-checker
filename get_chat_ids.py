import os
from dotenv import load_dotenv
import requests

load_dotenv()
token = os.getenv("TELEGRAM_BOT_TOKEN")
r = requests.get(f"https://api.telegram.org/bot{token}/getUpdates")
results = r.json().get("result", [])

if not results:
    print("No messages found. Make sure both of you sent a message to the bot first.")
else:
    seen = set()
    for u in results:
        chat = u.get("message", {}).get("chat", {})
        cid = chat.get("id")
        if cid and cid not in seen:
            seen.add(cid)
            print(f"{chat.get('first_name', '?')} {chat.get('last_name', '')}: chat_id = {cid}")
