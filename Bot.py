import os
import requests

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

TELEGRAM_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"
BINANCE_URL = "https://fapi.binance.com"


def send_message(chat_id, text):
    requests.post(
        f"{TELEGRAM_URL}/sendMessage",
        json={
            "chat_id": chat_id,
            "text": text
        },
        timeout=15
    )


def get_btc_price():
    response = requests.get(
        f"{BINANCE_URL}/fapi/v1/ticker/price",
        params={
            "symbol": "BTCUSDT"
        },
        timeout=15
    )

    response.raise_for_status()

    data = response.json()

    return float(data["price"])


def main():
    try:
        price = get_btc_price()

        send_message(
            CHAT_ID,
            f"🟢 INVEST ZONE\n\nBTC: {price:,.2f} USDT"
        )

    except Exception as e:
        send_message(
            CHAT_ID,
            f"🔴 Binance ошибка:\n{e}"
        )


if __name__ == "__main__":
    main()
