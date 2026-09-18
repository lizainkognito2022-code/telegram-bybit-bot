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
        raise Exception("Недостаточно данных BTC")

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


def detect_setup_a(candles):

    if len(candles) < 20:
        return False

    recent = candles[-20:]

    resistance = max(
        candle["high"]
        for candle in recent
    )

    last_10 = recent[-10:]

    lows = [
        candle["low"]
        for candle in last_10
    ]

    first_half_low = min(
        lows[:5]
    )

    second_half_low = min(
        lows[5:]
    )

    higher_low_structure = (
        second_half_low > first_half_low
    )

    current_price = recent[-1]["close"]

    distance_to_resistance = (
        (resistance - current_price)
        / resistance
        * 100
    )

    near_resistance = (
        0 <= distance_to_resistance <= 1.5
    )

    first_range = (
        max(
            candle["high"]
            for candle in recent[:10]
        )
        -
        min(
            candle["low"]
            for candle in recent[:10]
        )
    )

    second_range = (
        max(
            candle["high"]
            for candle in recent[10:]
        )
        -
        min(
            candle["low"]
            for candle in recent[10:]
        )
    )

    compression = (
        second_range < first_range
    )

    return (
        higher_low_structure
        and near_resistance
        and compression
    )


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
        recent[-1]["low"]
        <= resistance * 1.005
    )

    hold = (
        recent[-1]["close"] > resistance
    )

    return (
        breakout
        and retest
        and hold
    )


def detect_setup_c(candles):

    if len(candles) < 12:
        return False

    recent = candles[-12:]

    previous_lows = [
        candle["low"]
        for candle in recent[:-2]
    ]

    obvious_low = min(
        previous_lows
    )

    sweep = (
        recent[-2]["low"]
        < obvious_low
    )

    reclaim = (
        recent[-1]["close"]
        > obvious_low
    )

    return (
        sweep
        and reclaim
    )


def setup_text(
    setup_a,
    setup_b,
    setup_c
):

    if setup_a:
        return (
            "🟢 A — ПОДЖАТИЕ → ПРОБОЙ"
        )

    if setup_b:
        return (
            "🟢 B — ПРОБОЙ → РЕТЕСТ → "
            "ПРОДОЛЖЕНИЕ"
        )

    if setup_c:
        return (
            "🟢 C — СНЯТИЕ ЛИКВИДНОСТИ → "
            "РАЗВОРОТ"
        )

    return (
        "⚪ НЕТ КАЧЕСТВЕННОГО SETUP"
    )


def main():

    try:

        data = get_btc_data()

        hourly = make_hourly_candles(
            data
        )

        four_hour = make_4h_candles(
            hourly
        )

        structure = detect_structure(
            four_hour
        )

        setup_a = detect_setup_a(
            hourly
        )

        setup_b = detect_setup_b(
            hourly
        )

        setup_c = detect_setup_c(
            hourly
        )

        last_price = hourly[-1]["close"]

        result = setup_text(
            setup_a,
            setup_b,
            setup_c
        )

        message = (
            "🔎 INVEST ZONE\n\n"

            "BTC MARKET ANALYSIS\n\n"

            f"Цена: "
            f"{last_price:,.2f} USD\n\n"

            "━━━━━━━━━━━━━━━━━━\n"

            "BTC CONTEXT\n"
            f"{structure_text(structure)}\n\n"

            "4H STRUCTURE\n"
            f"{structure_text(structure)}\n\n"

            "━━━━━━━━━━━━━━━━━━\n"

            "1H SETUPS\n\n"

            "A — Поджатие → Пробой\n"
            f"{'🟢 YES' if setup_a else '⚪ NO'}\n\n"

            "B — Пробой → Ретест → "
            "Продолжение\n"
            f"{'🟢 YES' if setup_b else '⚪ NO'}\n\n"

            "C — Снятие ликвидности → "
            "Разворот\n"
            f"{'🟢 YES' if setup_c else '⚪ NO'}\n\n"

            "━━━━━━━━━━━━━━━━━━\n"

            f"РЕЗУЛЬТАТ:\n{result}\n\n"

            "━━━━━━━━━━━━━━━━━━\n"

            "ФИЛЬТРЫ\n\n"

            "BTC Context: "
            "🟢 ПРОВЕРЕН\n"

            "4H Structure: "
            f"{'🟢 UP' if structure == 'UP' else '🟡 НЕ UP'}\n"

            "1H Setup: "
            f"{'🟢 ЕСТЬ' if (setup_a or setup_b or setup_c) else '⚪ НЕТ'}\n"

            "Volume: ⚪ НЕ ПОДКЛЮЧЁН\n"
            "Open Interest: ⚪ НЕ ПОДКЛЮЧЁН\n"
            "Funding: ⚪ НЕ ПОДКЛЮЧЁН\n"
            "Liquidity: ⚪ НЕ ПОДКЛЮЧЁН\n"
            "Room to Target: ⚪ НЕ ПОДКЛЮЧЁН\n"
            "Structural Stop Loss: ⚪ НЕ ПОДКЛЮЧЁН\n\n"

            "⚠️ Сигнал на вход пока НЕ выдаётся."
        )

        send_message(
            CHAT_ID,
            message
        )

    except Exception as e:

        send_message(
            CHAT_ID,
            f"🔴 Ошибка INVEST ZONE:\n{e}"
        )


if __name__ == "__main__":
    main()
