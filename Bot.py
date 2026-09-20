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
