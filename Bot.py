import os
import requests
from datetime import datetime, timezone

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

TELEGRAM_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"
COINGECKO_URL = "https://api.coingecko.com/api/v3"


def send_message(chat_id, text):
    requests.post(
        f"{TELEGRAM_URL}/sendMessage",
        json={
            "chat_id": chat_id,
            "text": text
        },
        timeout=15
    )


def get_btc_market_data():
    response = requests.get(
        f"{COINGECKO_URL}/coins/bitcoin/market_chart",
        params={
            "vs_currency": "usd",
            "days": "7",
            "interval": "hourly"
        },
        timeout=20
    )

    response.raise_for_status()

    return response.json()


def main():
    try:
        data = get_btc_market_data()

        prices = data.get("prices", [])

        if len(prices) < 10:
            raise Exception("Недостаточно исторических данных")

        last_price = prices[-1][1]
        first_price = prices[0][1]

        change = (
            (last_price - first_price)
            / first_price
        ) * 100

        last_timestamp = prices[-1][0] / 1000

        last_time = datetime.fromtimestamp(
            last_timestamp,
            timezone.utc
        )

        message = (
            "🟢 INVEST ZONE\n\n"
            "BTC исторические данные получены.\n\n"
            f"Текущая цена: {last_price:,.2f} USD\n"
            f"Цена 7 дней назад: {first_price:,.2f} USD\n"
            f"Изменение: {change:+.2f}%\n\n"
            f"Последняя точка:\n"
            f"{last_time.strftime('%Y-%m-%d %H:%M UTC')}\n\n"
            f"Количество точек: {len(prices)}"
        )

        send_message(
            CHAT_ID,
            message
        )

    except Exception as e:

        send_message(
            CHAT_ID,
            f"🔴 CoinGecko ошибка:\n{e}"
        )


if __name__ == "__main__":
    main()
