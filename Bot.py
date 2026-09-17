import os
import requests

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

def send_message(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url, data={
        "chat_id": CHAT_ID,
        "text": text
    })

try:
    response = requests.get(
        "https://api.bybit.com/v5/market/time",
        timeout=10
    )

    if response.status_code == 200:
        send_message("✅ Bybit доступен. Подключение работает!")
    else:
        send_message(f"❌ Bybit вернул ошибку: {response.status_code}")

except Exception as e:
    send_message(f"❌ Ошибка подключения к Bybit: {e}")
