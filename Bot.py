import os
import requests

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

response = requests.post(
    url,
    data={
        "chat_id": CHAT_ID,
        "text": "🟢 INVEST ZONE: Telegram работает!"
    },
    timeout=30
)

print(response.status_code)
print(response.text)

response.raise_for_status()
