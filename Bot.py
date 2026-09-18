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
            "high": max(previous_price, current_price),
            "low": min(previous_price, current_price),
            "close": current_price
        })

    return candles


def detect_setup_a(candles):
    if len(candles) < 12:
        return False

    recent = candles[-12:]

    resistance = max(
        candle["high"]
        for candle in recent
    )

    last_6 = recent[-6:]

    lows = [
        candle["low"]
        for candle in last_6
    ]

    higher_lows = (
        lows[1] >= lows[0]
        and lows[2] >= lows[1]
        and lows[3] >= lows[2]
        and lows[4] >= lows[3]
        and lows[5] >= lows[4]
    )

    current_price = recent[-1]["close"]

    distance_to_resistance = (
        (resistance - current_price)
        / resistance
        * 100
    )

    near_resistance = distance_to_resistance <= 1.0

    return higher_lows and near_resistance


def detect_setup_b(candles):
    if len(candles) < 12:
        return False

    recent = candles[-12:]

    resistance = max(
        candle["high"]
        for candle in recent[:-2]
    )

    breakout = (
        recent[-2]["close"] > resistance
    )

    retest = (
        recent[-1]["low"] <= resistance * 1.005
    )

    hold = (
        recent[-1]["close"] > resistance
    )

    return breakout and retest and hold


def detect_setup_c(candles):
    if len(candles) < 12:
        return False

    recent = candles[-12:]

    previous_lows = [
        candle["low"]
        for candle in recent[:-2]
    ]

    obvious_low = min(previous_lows)

    sweep = (
        recent[-2]["low"] < obvious_low
    )

    reclaim = (
        recent[-1]["close"] > obvious_low
    )

    return sweep and reclaim


def main():
    try:
        data = get_btc_data()

        candles = make_hourly_candles(data)

        setup_a = detect_setup_a(candles)
        setup_b = detect_setup_b(candles)
        setup_c = detect_setup_c(candles)

        if setup_a:
            setup = "A — ПОДЖАТИЕ → ПРОБОЙ"

        elif setup_b:
            setup = "B — ПРОБОЙ → РЕТЕСТ → ПРОДОЛЖЕНИЕ"

        elif setup_c:
            setup = "C — СНЯТИЕ ЛИКВИДНОСТИ → РАЗВОРОТ"

        else:
            setup = "НЕТ КАЧЕСТВЕННОГО SETUP"

        last = candles[-1]

        message = (
            "📊 INVEST ZONE\n\n"
            "BTC 1H SETUP\n\n"
            f"Текущая цена: {last['close']:,.2f} USD\n\n"
            f"Setup: {setup}\n\n"
            "A — Поджатие → пробой: "
            f"{'🟢 YES' if setup_a else '⚪ NO'}\n"
            "B — Пробой → ретест: "
            f"{'🟢 YES' if setup_b else '⚪ NO'}\n"
            "C — Снятие ликвидности: "
            f"{'🟢 YES' if setup_c else '⚪ NO'}\n\n"
            "4H CONTEXT: 🟢 ВОСХОДЯЩАЯ"
        )

        send_message(
            CHAT_ID,
            message
        )

    except Exception as e:
        send_message(
            CHAT_ID,
            f"🔴 Ошибка 1H Setup:\n{e}"
        )


if __name__ == "__main__":
    main()
