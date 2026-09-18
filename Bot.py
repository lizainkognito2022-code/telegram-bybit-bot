import os
import requests
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

KRAKEN_URL = "https://api.kraken.com/0/public/OHLC"


def send_photo(filename, caption):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"

    with open(filename, "rb") as photo:
        r = requests.post(
            url,
            data={
                "chat_id": CHAT_ID,
                "caption": caption
            },
            files={"photo": photo},
            timeout=60
        )

    print(r.status_code)
    print(r.text)
    r.raise_for_status()


def get_ohlc(interval):
    r = requests.get(
        KRAKEN_URL,
        params={
            "pair": "XBTUSD",
            "interval": interval
        },
        timeout=30
    )

    r.raise_for_status()

    data = r.json()

    if data.get("error"):
        raise Exception(data["error"])

    result = data["result"]

    pair = [x for x in result if x != "last"][0]

    candles = result[pair]

    if len(candles) > 1:
        candles = candles[:-1]

    return candles


def values(candles):
    opens = [float(x[1]) for x in candles]
    highs = [float(x[2]) for x in candles]
    lows = [float(x[3]) for x in candles]
    closes = [float(x[4]) for x in candles]
    volumes = [float(x[6]) for x in candles]

    return opens, highs, lows, closes, volumes


def context_4h(candles):
    _, highs, lows, closes, _ = values(candles)

    if len(closes) < 12:
        return "⚪ НЕДОСТАТОЧНО ДАННЫХ"

    rh = max(highs[-6:])
    ph = max(highs[-12:-6])

    rl = min(lows[-6:])
    pl = min(lows[-12:-6])

    if rh > ph and rl > pl:
        return "🟢 ВОСХОДЯЩИЙ"

    if rh < ph and rl < pl:
        return "🔴 НИСХОДЯЩИЙ"

    return "🟡 БОКОВОЙ"


def resistance(candles):
    _, highs, _, _, _ = values(candles)

    if len(highs) < 10:
        return max(highs)

    return max(highs[-20:-3])


def swing_lows(candles):
    _, _, lows, _, _ = values(candles)

    result = []

    for i in range(1, len(lows) - 1):
        if lows[i] < lows[i - 1] and lows[i] <= lows[i + 1]:
            result.append(i)

    return result


def higher_lows(candles):
    _, _, lows, _, _ = values(candles)

    swings = swing_lows(candles)

    swings = [
        i for i in swings
        if i >= len(lows) - 14
    ]

    if len(swings) < 2:
        return False, swings

    recent = swings[-3:]

    low_values = [lows[i] for i in recent]

    count = 0

    for i in range(1, len(low_values)):
        if low_values[i] > low_values[i - 1]:
            count += 1

    return count >= 1, recent


def compression(candles):
    _, highs, lows, _, _ = values(candles)

    if len(highs) < 12:
        return False

    old = []

    new = []

    for i in range(-12, -6):
        old.append(highs[i] - lows[i])

    for i in range(-6, 0):
        new.append(highs[i] - lows[i])

    old_avg = sum(old) / len(old)
    new_avg = sum(new) / len(new)

    if old_avg == 0:
        return False

    return new_avg < old_avg * 0.85


def approach(candles, res):
    _, _, _, closes, _ = values(candles)

    price = closes[-1]

    distance = ((res - price) / res) * 100

    return 0 <= distance <= 1.5, distance


def breakout(candles, res):
    _, _, _, closes, volumes = values(candles)

    price = closes[-1]

    broke = price > res * 1.002

    if len(volumes) < 11:
        return broke, False

    avg = sum(volumes[-11:-1]) / 10

    volume_up = volumes[-1] > avg * 1.3

    return broke, volume_up


def confirm_30m(candles):
    _, _, lows, closes, volumes = values(candles)

    if len(closes) < 10:
        return "⚪ НЕДОСТАТОЧНО ДАННЫХ"

    price_up = closes[-1] > closes[-4]

    recent_low = min(lows[-3:])
    old_low = min(lows[-7:-3])

    hl = recent_low > old_low

    avg_volume = sum(volumes[-8:-1]) / 7

    volume_up = volumes[-1] > avg_volume * 1.1

    if hl and price_up and volume_up:
        return "🟢 CONFIRMATION"

    if hl and price_up:
        return "🟡 ПОЗИТИВНО"

    return "⚪ БЕЗ ПОДТВЕРЖДЕНИЯ"


def analyze(candles):
    _, _, _, closes, _ = values(candles)

    price = closes[-1]

    res = resistance(candles)

    hl, lows_index = higher_lows(candles)

    comp = compression(candles)

    near, distance = approach(candles, res)

    broke, volume_up = breakout(candles, res)

    if broke and volume_up:
        status = "🟢 ПОДЖАТИЕ → ПРОБОЙ"
    elif hl and comp and near:
        status = "🟡 ФОРМИРУЕТСЯ ПОДЖАТИЕ"
    elif hl and near:
        status = "🟠 ПОДХОД К СОПРОТИВЛЕНИЮ"
    else:
        status = "⚪ НЕТ ПОДЖАТИЯ"

    return {
        "price": price,
        "resistance": res,
        "distance": distance,
        "higher_lows": hl,
        "lows_index": lows_index,
        "compression": comp,
        "approach": near,
        "breakout": broke,
        "volume_up": volume_up,
        "status": status
    }


def make_chart(candles, result, ctx4h, ctx30m):
    visible = candles[-30:]

    opens, highs, lows, closes, _ = values(visible)

    fig, ax = plt.subplots(figsize=(13, 7))

    for i in range(len(visible)):
        op = opens[i]
        cl = closes[i]
        hi = highs[i]
        lo = lows[i]

        bottom = min(op, cl)
        height = max(abs(cl - op), 0.01)

        ax.plot(
            [i, i],
            [lo, hi],
            linewidth=1
        )

        body = Rectangle(
            (i - 0.3, bottom),
            0.6,
            height,
            alpha=
