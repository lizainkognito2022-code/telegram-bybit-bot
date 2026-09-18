import os
import requests

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


def get_btc_data():
    response = requests.get(
        f"{COINGECKO_URL}/coins/bitcoin/market_chart",
        params={
            "vs_currency": "usd",
            "days": "14",
            "interval": "hourly"
        },
        timeout=20
    )

    response.raise_for_status()

    return response.json()


def make_hourly_candles(data):
    prices = data.get("prices", [])

    if len(prices) < 50:
        raise Exception("Недостаточно данных")

    candles = []

    for i in range(1, len(prices)):
        previous_price = float(prices[i - 1][1])
        current_price = float(prices[i][1])

        candles.append({
            "open": previous_price,
            "high": max(
                previous_price,
                current_price
            ),
            "low": min(
                previous_price,
                current_price
            ),
            "close": current_price
        })

    return candles


def make_4h_candles(hourly):
    candles = []

    block = []

    for candle in hourly:
        block.append(candle)

        if len(block) == 4:
            candles.append({
                "open": block[0]["open"],
                "high": max(
                    x["high"]
                    for x in block
                ),
                "low": min(
                    x["low"]
                    for x in block
                ),
                "close": block[-1]["close"]
            })

            block = []

    return candles


def detect_structure(candles):
    if len(candles) < 20:
        return "UNKNOWN"

    recent = candles[-20:]

    first_half = recent[:10]
    second_half = recent[10:]

    first_high = max(
        candle["high"]
        for candle in first_half
    )

    second_high = max(
        candle["high"]
        for candle in second_half
    )

    first_low = min(
        candle["low"]
        for candle in first_half
    )

    second_low = min(
        candle["low"]
        for candle in second_half
    )

    if (
        second_high > first_high
        and second_low > first_low
    ):
        return "UP"

    if (
        second_high < first_high
        and second_low < first_low
    ):
        return "DOWN"

    return "RANGE"


def structure_text(structure):
    if structure == "UP":
        return "🟢 ВОСХОДЯЩАЯ"

    if structure == "DOWN":
        return "🔴 НИСХОДЯЩАЯ"

    if structure == "RANGE":
        return "🟡 RANGE"

    return "⚪ НЕДОСТАТОЧНО ДАННЫХ"


def main():
    try:
        data = get_btc_data()

        hourly = make_hourly_candles(data)
        four_hour = make_4h_candles(hourly)

        structure = detect_structure(
            four_hour
        )

        last = four_hour[-1]

        message = (
            "📊 INVEST ZONE\n\n"
            "BTC 4H STRUCTURE\n\n"
            f"Структура: {structure_text(structure)}\n\n"
            f"4H Open: {last['open']:,.2f}\n"
            f"4H High: {last['high']:,.2f}\n"
            f"4H Low: {last['low']:,.2f}\n"
            f"4H Close: {last['close']:,.2f}\n\n"
            f"4H свечей: {len(four_hour)}\n\n"
            "Следующий этап:\n"
            "1H Setup A / B / C"
        )

        send_message(
            CHAT_ID,
            message
        )

    except Exception as e:

        send_message(
            CHAT_ID,
            f"🔴 Ошибка 4H Structure:\n{e}"
        )


if __name__ == "__main__":
    main()
