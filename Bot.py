import os
import requests

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

def send_message(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(
        url,
        data={"chat_id": CHAT_ID, "text": text},
        timeout=10
    )

try:
    ip = requests.get("https://api.ipify.org", timeout=10).text
    send_message(f"🌍 IP GitHub Actions:\n{ip}")
except Exception as e:
    send_message(f"❌ Ошибка:\n{e}")
