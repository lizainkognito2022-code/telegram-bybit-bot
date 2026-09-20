import os
import requests


BOT_TOKEN = os.environ["BOT_TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]

KRAKEN_URL = "https://api.kraken.com/0/public/OHLC"


def get_ohlc(interval):
    response = requests.get(
        KRAKEN_URL,
        params={
            "pair": "XBTUSD",
            "interval": interval
        },
        timeout=30
    )

    response.raise_for_status()

    data = response.json()

    if data.get("error"):
        raise RuntimeError(
            f"Ошибка Kraken: {data['error']}"
        )

    result = data["result"]

    pair = next(
        key for key in result
        if key != "last"
    )

    candles = []

    for row in result[pair]:
        candles.append(
            {
                "time": float(row[0]),
                "open": float(row[1]),
                "high": float(row[2]),
                "low": float(row[3]),
                "close": float(row[4]),
                "volume": float(row[6])
            }
        )

    return candles


def average(values):
    if not values:
        return 0.0

    return sum(values) / len(values)


def context_4h(candles):
    closes = [
        candle["close"]
        for candle in candles
    ]

    if len(closes) < 10:
        return "NEUTRAL"

    old = average(closes[-10:-5])
    new = average(closes[-5:])

    if new > old * 1.01:
        return "UP"

    if new < old * 0.99:
        return "DOWN"

    return "RANGE"


def find_resistance(candles):
    highs = [
        candle["high"]
        for candle in candles
    ]

    if len(highs) >= 20:
        return max(highs[-20:-3])

    return max(highs)


def find_swing_lows(candles):
    lows = [
        candle["low"]
        for candle in candles
    ]

    indexes = []

    for i in range(2, len(lows) - 2):
        if (
            lows[i] < lows[i - 1]
            and lows[i] < lows[i - 2]
            and lows[i] < lows[i + 1]
            and lows[i] < lows[i + 2]
        ):
            indexes.append(i)

    return indexes


def check_higher_lows(candles):
    indexes = find_swing_lows(candles)

    if len(indexes) < 3:
        return False

    recent = indexes[-3:]

    lows = [
        candles[i]["low"]
        for i in recent
    ]

    return (
        lows[0] < lows[1]
        and lows[1] < lows[2]
    )


def check_compression(candles):
    if len(candles) < 20:
        return False

    ranges = [
        candle["high"] - candle["low"]
        for candle in candles
    ]

    old_range = average(
        ranges[-20:-10]
    )

    new_range = average(
        ranges[-10:]
    )

    if old_range <= 0:
        return False

    return new_range < old_range * 0.85


def check_approach(candles, resistance):
    price = candles[-1]["close"]

    distance = (
        abs(resistance - price)
        / price
    )

    return distance <= 0.015


def check_breakout(candles, resistance):
    if len(candles) < 20:
        return False

    price = candles[-1]["close"]

    if price <= resistance * 1.002:
        return False

    volumes = [
        candle["volume"]
        for candle in candles
    ]

    previous_volume = average(
        volumes[-20:-5]
    )

    if previous_volume <= 0:
        return False

    return (
        volumes[-1]
        >= previous_volume * 1.30
    )


def check_30m_confirmation(candles):
    if len(candles) < 10:
        return False

    closes = [
        candle["close"]
        for candle in candles
    ]

    previous_high = max(
        closes[-6:-1]
    )

    return closes[-1] >= previous_high


def analyze(c4h, c1h, c30):
    price = c1h[-1]["close"]

    context = context_4h(c4h)

    resistance = find_resistance(c1h)

    higher_lows = check_higher_lows(
        c1h
    )

    compression = check_compression(
        c1h
    )

    approach = check_approach(
        c1h,
        resistance
    )

    breakout = check_breakout(
        c1h,
        resistance
    )

    confirmation = check_30m_confirmation(
        c30
    )

    distance = (
        abs(resistance - price)
        / price
        * 100
    )

    formation = (
        context != "DOWN"
        and higher_lows
        and compression
        and approach
        and price <= resistance
    )

    signal = (
        context != "DOWN"
        and breakout
        and confirmation
    )

    return {
        "price": price,
        "context": context,
        "resistance": resistance,
        "distance": distance,
        "higher_lows": higher_lows,
        "compression": compression,
        "approach": approach,
        "breakout": breakout,
        "confirmation": confirmation,
        "formation": formation,
        "signal": signal
    }


def send_message(text):
    url = (
        "https://api.telegram.org/bot"
        + BOT_TOKEN
        + "/sendMessage"
    )

    response = requests.post(
        url,
        data={
            "chat_id": CHAT_ID,
            "text": text
        },
        timeout=30
    )

    response.raise_for_status()


def russian_context(context):
    if context == "UP":
        return "ВОСХОДЯЩИЙ"

    if context == "DOWN":
        return "НИСХОДЯЩИЙ"

    if context == "RANGE":
        return "БОКОВИК"

    return "НЕЙТРАЛЬНЫЙ"


def main():
    candles_4h = get_ohlc(240)

    candles_1h = get_ohlc(60)

    candles_30m = get_ohlc(30)

    result = analyze(
        candles_4h,
        candles_1h,
        candles_30m
    )

    if result["signal"]:
        status = "🟢 СИГНАЛ"

    elif result["formation"]:
        status = "🟡 ПОДЖАТИЕ"

    elif (
        result["breakout"]
        or (
            result["price"]
            > result["resistance"]
        )
    ):
        status = "🔵 ПРОБОЙ НАБЛЮДАЕМ"

    else:
        status = "⚪ НАБЛЮДЕНИЕ"

    message = "\n".join(
        [
            "INVEST ZONE",
            "",
            status,
            "",
            f"BTC: ${result['price']:,.2f}",
            (
                "Сопротивление: "
                f"${result['resistance']:,.2f}"
            ),
            (
                "Расстояние: "
                f"{result['distance']:.2f}%"
            ),
            "",
            (
                "4H Контекст: "
                f"{russian_context(result['context'])}"
            ),
            (
                "1H Повышающиеся минимумы: "
                + (
                    "ДА"
                    if result["higher_lows"]
                    else "НЕТ"
                )
            ),
            (
                "1H Сжатие: "
                + (
                    "ДА"
                    if result["compression"]
                    else "НЕТ"
                )
            ),
            (
                "1H Подход к сопротивлению: "
                + (
                    "ДА"
                    if result["approach"]
                    else "НЕТ"
                )
            ),
            (
                "Пробой: "
                + (
                    "ДА"
                    if result["breakout"]
                    else "НЕТ"
                )
            ),
            (
                "Подтверждение 30M: "
                + (
                    "ДА"
                    if result["confirmation"]
                    else "НЕТ"
                )
            )
        ]
    )

    send_message(message)


if __name__ == "__main__":
    main()
