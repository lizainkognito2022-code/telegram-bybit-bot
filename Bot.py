import os
import time
import requests

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

TELEGRAM_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"
BINANCE_URL = "https://fapi.binance.com"


# ============================================================
# TELEGRAM
# ============================================================

def send_message(chat_id, text, keyboard=None):
    data = {
        "chat_id": chat_id,
        "text": text
    }

    if keyboard:
        data["reply_markup"] = keyboard

    try:
        requests.post(
            f"{TELEGRAM_URL}/sendMessage",
            json=data,
            timeout=15
        )
    except Exception as e:
        print("Telegram error:", e)


def keyboard():
    return {
        "keyboard": [
            [{"text": "🛒 ЧТО КУПИТЬ?"}]
        ],
        "resize_keyboard": True,
        "is_persistent": True
    }


# ============================================================
# BINANCE PUBLIC API
# ============================================================

def binance_get(endpoint, params=None):
    try:
        response = requests.get(
            f"{BINANCE_URL}{endpoint}",
            params=params,
            timeout=15
        )

        if response.status_code != 200:
            print("Binance HTTP:", response.status_code)
            return None

        return response.json()

    except Exception as e:
        print("Binance error:", e)
        return None


def get_symbols():
    data = binance_get("/fapi/v1/exchangeInfo")

    if not data:
        return []

    symbols = []

    for item in data.get("symbols", []):
        if item.get("status") != "TRADING":
            continue

        if item.get("quoteAsset") != "US
