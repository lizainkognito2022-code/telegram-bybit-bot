import os
import requests
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

KRAKEN_URL = "https://api.kraken.com/0/public/OHLC"


# =========================================================
# TELEGRAM
# =========================================================

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

    print("Telegram:", response.status_code)
    print(response.text)

    response.raise_for_status()


# =========================================================
# KRAKEN
# =========================================================

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
        raise Exception(data["error"])

    result = data["result"]

    pair = [x for x in result if x != "last"][0]

    candles = result[pair]

    if len(candles) > 1:
        candles = candles[:-1]

    return candles


# =========================================================
# CANDLE DATA
# =========================================================

def candle_values(candles):
    opens = [float(x[1]) for x in candles]
    highs = [float(x[2]) for x in candles]
    lows = [float(x[3]) for x in candles]
    closes = [float(x[4]) for x in candles]
    volumes = [float(x[6]) for x in candles]

    return opens, highs, lows, closes, volumes


# =========================================================
# 4H CONTEXT
# =========================================================

def analyze_4h(candles):
    _, highs, lows, closes, _ = candle_values(candles)

    if len(closes) < 12:
        return "⚪ НЕДОСТАТОЧНО ДАННЫХ"

    recent_high = max(highs[-6:])
    previous_high = max(highs[-12:-6])

    recent_low = min(lows[-6:])
    previous_low = min(lows[-12:-6])

    if recent_high > previous_high and recent_low > previous_low:
        return "🟢 4H ВОСХОДЯЩИЙ"

    if recent_high < previous_high and recent_low < previous_low:
        return "🔴 4H НИСХОДЯЩИЙ"

    return "🟡 4H БОКОВОЙ"


# =========================================================
# RESISTANCE
# =========================================================

def find_resistance(candles):
    _, highs, _, _, _ = candle_values(candles)

    if len(highs) < 10:
        return max(highs)

    lookback = min(20, len(highs) - 3)

    return max(highs[-lookback:-3])


# =========================================================
# HIGHER LOWS
# =========================================================

def find_swing_lows(candles):
    _, _, lows, _, _ = candle_values(candles)

    swings = []

    for i in range(1, len(lows) - 1):
        if lows[i] < lows[i - 1] and lows[i] <= lows[i + 1]:
            swings.append(i)

    return swings


def analyze_higher_lows(candles):
    _, _, lows, _, _ = candle_values(candles)

    swings = find_swing_lows(candles)

    recent = [
        i for i in swings
        if i >= len(lows) - 14
    ]

    if len(recent) < 2:
        return False, []

    recent = recent[-3:]

    values = [lows[i] for i in recent]

    higher_count = 0

    for i in range(1, len(values)):
        if values[i] > values[i - 1]:
            higher_count += 1

    return higher_count >= 1, list(zip(recent, values))


# =========================================================
# COMPRESSION
# =========================================================

def analyze_compression(candles):
    _, highs, lows, _, _ = candle_values(candles)

    if len(highs) < 12:
        return False

    old_ranges = [
        highs[i] - lows[i]
        for i in range(-12, -6)
    ]

    new_ranges = [
        highs[i] - lows[i]
        for i in range(-6, 0)
    ]

    old_avg = sum(old_ranges) / len(old_ranges)
    new_avg = sum(new_ranges) / len(new_ranges)

    if old_avg == 0:
        return False

    return new_avg < old_avg * 0.85


# =========================================================
# APPROACH TO RESISTANCE
# =========================================================

def analyze_approach(candles, resistance):
    _, _, _, closes, _ = candle_values(candles)

    current = closes[-1]

    distance = ((resistance - current) / resistance) * 100

    approach = (
        distance >= 0
        and
        distance <= 1.5
    )

    return approach, distance


# =========================================================
# BREAKOUT
# =========================================================

def analyze_breakout(candles, resistance):
    _, _, _, closes, volumes = candle_values(candles)

    current = closes[-1]

    breakout = current > resistance * 1.002

    if len(volumes) >= 11:
        average_volume = sum(volumes[-11:-1]) / 10
        current_volume = volumes[-1]

        volume_expansion = (
            current_volume > average_volume * 1.3
        )
    else:
        volume_expansion = False

    return breakout, volume_expansion


# =========================================================
# 30M CONFIRMATION
# =========================================================

def analyze_30m(candles):
    _, highs, lows, closes, volumes = candle_values(candles)

    if len(closes) < 10:
        return "⚪ 30M НЕДОСТАТОЧНО ДАННЫХ"

    current = closes[-1]
    previous = closes[-4]

    higher_low = (
        min(lows[-3:]) >
        min(lows[-7:-3])
    )

    price_up = current > previous

    average_volume = sum(volumes[-8:-1]) / 7

    volume_ok = volumes[-1] > average_volume * 1.1

    if higher_low and price_up and volume_ok:
        return "🟢 30M CONFIRMATION"

    if higher_low and price_up:
        return "🟡 30M ПОЗИТИВНО"

    return "⚪ 30M БЕЗ ПОДТВЕРЖДЕНИЯ"


# =========================================================
# 1H SETUP
# =========================================================

def analyze_setup(candles):
    _, _, _, closes, _ = candle_values(candles)

    current = closes[-1]

    resistance = find_resistance(candles)

    higher_lows, swing_lows = analyze_higher_lows(candles)

    compression = analyze_compression(candles)

    approach, distance = analyze_approach(
        candles,
        resistance
    )

    breakout, volume_expansion = analyze_breakout(
        candles,
        resistance
    )

    compression_setup = (
        higher_lows
        and
        compression
        and
        approach
    )

    confirmed_breakout = (
        breakout
        and
        volume_expansion
    )

    if confirmed_breakout:
        status = "🟢 ПОДЖАТИЕ → ПРОБОЙ"
    elif compression_setup:
        status = "🟡 ФОРМИРУЕТСЯ ПОДЖАТИЕ"
    elif higher_lows and approach:
        status = "🟠 ПОДХОД К СОПРОТИВЛЕНИЮ"
    else:
        status = "⚪ НЕТ ПОДЖАТИЯ"

    return {
        "status": status,
        "resistance": resistance,
        "current": current,
        "higher_lows": higher_lows,
        "swing_lows": swing_lows,
        "compression": compression,
        "approach": approach,
        "distance": distance,
        "breakout": breakout,
        "volume_expansion": volume_expansion
    }


# =========================================================
# CHART
# =========================================================

def create_chart(candles, analysis, context_4h, confirmation_30m):
