import os
import time
import requests
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

KRAKEN_URL = "https://api.kraken.com/0/public/OHLC"


# =========================
# TELEGRAM
# =========================

def send_message(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    response = requests.post(
        url,
        data={
            "chat_id": CHAT_ID,
            "text": text
        },
        timeout=30
    )

    response.raise_for_status()


def send_photo(filename, caption):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"

    with open(filename, "rb") as photo:
        response = requests.post(
            url,
            data={
                "chat_id": CHAT_ID,
                "caption": caption
            },
            files={
                "photo": photo
            },
            timeout=60
        )

    response.raise_for_status()


# =========================
# KRAKEN
# =========================

def get_ohlc(pair="XBTUSD", interval=60):
    response = requests.get(
        KRAKEN_URL,
        params={
            "pair": pair,
            "interval": interval
        },
        timeout=30
    )

    response.raise_for_status()

    data = response.json()

    if data.get("error"):
        raise Exception(data["error"])

    result = data["result"]

    pair_key = [key for key in result.keys() if key != "last"][0]

    candles = result[pair_key]

    return candles


# =========================
# CONVERT CANDLES
# =========================

def prepare_candles(raw):
    candles = []

    for row in raw:
        candles.append({
            "time": float(row[0]),
            "open": float(row[1]),
            "high": float(row[2]),
            "low": float(row[3]),
            "close": float(row[4]),
            "volume": float(row[6])
        })

    # Последнюю свечу Kraken не используем,
    # потому что она может быть ещё незакрыта.
    if len(candles) > 1:
        candles = candles[:-1]

    return candles


# =========================
# VOLUME
# =========================

def volume_ratio(candles, period=10):
    if len(candles) < period + 1:
        return 0

    recent = candles[-1]["volume"]

    previous = [
        candle["volume"]
        for candle in candles[-period-1:-1]
    ]

    avg = sum(previous) / len(previous)

    if avg == 0:
        return 0

    return recent / avg


# =========================
# RESISTANCE
# =========================

def find_resistance(candles, lookback=18):
    if len(candles) < lookback:
        lookback = len(candles)

    highs = [
        candle["high"]
        for candle in candles[-lookback:]
    ]

    return max(highs)


# =========================
# HIGHER LOWS
# =========================

def count_higher_lows(candles, lookback=12):
    if len(candles) < lookback:
        return 0

    lows = [
        candle["low"]
        for candle in candles[-lookback:]
    ]

    # Делим участок на 3 части.
    third = max(2, len(lows) // 3)

    first = min(lows[:third])
    second = min(lows[third:third * 2])
    third_low = min(lows[third * 2:])

    count = 0

    if second > first:
        count += 1

    if third_low > second:
        count += 1

    return count


# =========================
# COMPRESSION
# =========================

def check_compression(candles, lookback=12):
    if len(candles) < lookback:
        return False, 0, 0

    ranges = [
        candle["high"] - candle["low"]
        for candle in candles[-lookback:]
    ]

    first_half = ranges[:lookback // 2]
    second_half = ranges[lookback // 2:]

    first_avg = sum(first_half) / len(first_half)
    second_avg = sum(second_half) / len(second_half)

    if first_avg == 0:
        return False, first_avg, second_avg

    compression = second_avg < first_avg * 0.85

    return compression, first_avg, second_avg


# =========================
# APPROACH TO RESISTANCE
# =========================

def check_approach(candles, resistance):
    current = candles[-1]["close"]

    distance = ((resistance - current) / resistance) * 100

    return distance <= 1.5, distance


# =========================
# SETUP A
# =========================

def analyze_setup(candles):
    resistance = find_resistance(candles)

    higher_lows = count_higher_lows(candles)

    compression, first_range, second_range = check_compression(candles)

    approach, distance = check_approach(
        candles,
        resistance
    )

    current = candles[-1]["close"]

    breakout = current > resistance * 1.002

    conditions = [
        higher_lows >= 1,
        compression,
        approach
    ]

    score = sum(conditions)

    if breakout:
        status = "🟢 ПОДЖАТИЕ + ПРОБОЙ"
    elif score >= 2:
        status = "🟡 ФОРМИРУЕТСЯ ПОДЖАТИЕ"
    else:
        status = "⚪ НЕТ ПОДЖАТИЯ"

    return {
        "status": status,
        "resistance": resistance,
        "higher_lows": higher_lows,
        "compression": compression,
        "approach": approach,
        "distance": distance,
        "breakout": breakout,
        "score": score
    }


# =========================
# 30M CONFIRMATION
# =========================

def analyze_30m():
    raw = get_ohlc(
        pair="XBTUSD",
        interval=30
    )

    candles = prepare_candles(raw)

    if len(candles) < 10:
        return "⚪ НЕДОСТАТОЧНО ДАННЫХ"

    current = candles[-1]["close"]

    previous = candles[-5]["close"]

    volume = volume_ratio(candles)
