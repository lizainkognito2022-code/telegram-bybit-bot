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

    # Последняя свеча может быть незакрытой
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

    # Берём предыдущие свечи,
    # чтобы текущая цена не была сама сопротивлением
    lookback = min(20, len(highs) - 3)

    resistance = max(
        highs[-lookback:-3]
    )

    return resistance


# =========================================================
# HIGHER LOWS
# =========================================================

def find_swing_lows(candles):

    _, _, lows, _, _ = candle_values(candles)

    swings = []

    for i in range(1, len(lows) - 1):

        if (
            lows[i] < lows[i - 1]
            and
            lows[i] <= lows[i + 1]
        ):
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

    # Берём последние 3 swing low
    recent = recent[-3:]

    values = [
        lows[i]
        for i in recent
    ]

    higher_count = 0

    for i in range(1, len(values)):

        if values[i] > values[i - 1]:
            higher_count += 1

    return higher_count >= 1, list(
        zip(recent, values)
    )


# =========================================================
# COMPRESSION
# =========================================================

def analyze_compression(candles):

    _, highs, lows, _, _ = candle_values(candles)

    if len(highs) < 12:
        return False

    old_ranges = []

    new_ranges = []

    for i in range(-12, -6):

        old_ranges.append(
            highs[i] - lows[i]
        )

    for i in range(-6, 0):

        new_ranges.append(
            highs[i] - lows[i]
        )

    old_avg = sum(old_ranges) / len(old_ranges)
    new_avg = sum(new_ranges) / len(new_ranges)

    if old_avg == 0:
        return False

    # Диапазон последних свечей
    # должен стать заметно меньше
    return new_avg < old_avg * 0.85


# =========================================================
# APPROACH
# =========================================================

def analyze_approach(candles, resistance):

    _, _, _, closes, _ = candle_values(candles)

    current = closes[-1]

    distance = (
        (resistance - current)
        /
        resistance
    ) * 100

    # Цена должна находиться
    # максимум в 1.5% от сопротивления
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

    # Пробой должен быть закрытием
    breakout = current > resistance * 1.002

    # Объём сравниваем со средним
    if len(volumes) >= 11:

        average_volume = sum(
            volumes[-11:-1]
        ) / 10

        current_volume = volumes[-1]

        volume_expansion = (
            current_volume >
            average_volume * 1.3
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

    average_volume = sum(
        volumes[-8:-1]
    ) / 7

    volume_ok = (
        volumes[-1] >
        average_volume * 1.1
    )

    if higher_low and price_up and volume_ok:
        return "🟢 30M CONFIRMATION"

    if higher_low and price_up:
        return "🟡 30M ПОЗИТИВНО"

    return "⚪ 30M БЕЗ ПОДТВЕРЖДЕНИЯ"


# =========================================================
# MAIN 1H SETUP
# =========================================================

def analyze_setup(candles):

    _, highs, lows, closes, _ = candle_values(candles)

    current = closes[-1]

    resistance = find_resistance(candles)

    higher_lows, swing_lows = analyze_higher_lows(
        candles
    )

    compression = analyze_compression(
        candles
    )

    approach, distance = analyze_approach(
        candles,
        resistance
    )

    breakout, volume_expansion = analyze_breakout(
        candles,
        resistance
    )

    # -----------------------------------------
    # ПОЛНОЕ ПОДЖАТИЕ
    # -----------------------------------------

    compression_setup = (
        higher_lows
        and
        compression
        and
        approach
    )

    # -----------------------------------------
    # ПРОБОЙ
    # -----------------------------------------

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
        "volume_expansion": volume_expansion,
        "compression_setup": compression_setup,
        "confirmed_breakout": confirmed_breakout
    }


# =========================================================
# DRAW INVEST ZONE CHART
# =========================================================

def create_chart(
    candles,
    analysis,
    context_4h,
    confirmation_30m
):

    visible = candles[-30:]

    opens, highs, lows, closes, volumes = candle_values(
        visible
    )

    fig, ax = plt.subplots(
        figsize=(13, 7)
    )

    # -----------------------------------------
    # CANDLESTICKS
    # -----------------------------------------

    for i in range(len(visible)):

        open_price = opens[i]
        close_price = closes[i]
        high = highs[i]
        low = lows[i]

        if close_price >= open_price:
            bottom = open_price
            height = close_price - open_price
        else:
            bottom = close_price
            height = open_price - close_price

        ax.plot(
            [i, i],
            [low, high],
            linewidth=1
        )

        rectangle = Rectangle(
            (
                i - 0.30,
                bottom
            ),
            0.60,
            max(height, 0.01),
            fill=True,
            alpha=0.65
        )

        ax.add_patch(rectangle)

    # -----------------------------------------
    # RESISTANCE
    # -----------------------------------------

    resistance = analysis["resistance"]

    ax.axhline(
        resistance,
        linestyle="--",
        linewidth=2,
        label=f"RESISTANCE {resistance:,.0f}"
    )

    # Resistance zone

    ax.axhspan(
        resistance * 0.998,
        resistance * 1.002,
        alpha=0.12
    )

    # -----------------------------------------
    # HIGHER LOWS
    # -----------------------------------------

    for index, value in analysis["swing_lows"]:

        visible_index = index - (
            len(candles) - len(visible)
        )

        if 0 <= visible_index < len(visible):

            ax.scatter(
                visible_index,
                value,
                marker="^",
                s=90
            )

            ax.annotate(
                "HL",
                (
                    visible_index,
                    value
                ),
                xytext=(
                    0,
                    -20
                ),
                textcoords="offset points",
                ha="center",
                fontsize=9
            )

    # -----------------------------------------
    # COMPRESSION ZONE
    # -----------------------------------------

    if analysis["compression"]:

        start = max(
            0,
            len(visible) - 8
        )

        compression_high = max(
            highs[start:]
        )

        compression_low = min(
            lows[start:]
        )

        ax.fill_between(
            range(
                start,
                len(visible)
            ),
            compression_low,
            compression_high,
            alpha=0.10
        )

        ax.text(
            start + 1,
            compression_low,
            "COMPRESSION",
            fontsize=10
        )

    # -----------------------------------------
    # CURRENT PRICE
    # -----------------------------------------

    current = analysis["current"]

    ax.axhline(
        current,
        linestyle=":",
        linewidth=1
    )

    # -----------------------------------------
    # INFO PANEL
    # -----------------------------------------

    info = (
        f"{analysis['status']}\n\n"
        f"4H: {context_4h}\n"
        f"30M: {confirmation_30m}\n\n"
        f"Higher Lows: "
        f"{'YES' if analysis['higher_lows'] else 'NO'}\n"
        f"Compression: "
        f"{'YES' if analysis['compression'] else 'NO'}\n"
        f"Approach: "
        f"{'YES' if analysis['approach'] else 'NO'}\n"
        f"Breakout: "
        f"{'YES' if analysis['breakout'] else 'NO'}\n"
        f"Volume expansion: "
        f"{'YES' if analysis['volume_expansion'] else 'NO'}"
    )

    ax.text(
        0.02,
        0.97,
        info,
        transform=ax.transAxes,
        verticalalignment="top",
        fontsize=10,
        bbox=dict(
            boxstyle="round",
            alpha=0.15
        )
    )

    # -----------------------------------------
    # TITLE
    # -----------------------------------------

    ax.set_title(
        "INVEST ZONE — BTC/USD",
        fontsize=17,
        fontweight="bold"
    )

    ax.set_xlabel(
        "1H candles"
    )

    ax.set_ylabel(
        "Price"
    )

    ax.grid(
        True,
        alpha=0.20
    )

    ax.legend(
        loc="lower right"
    )

    plt.tight_layout()

    filename = "invest_zone.png"

    plt.savefig(
        filename,
        dpi=150
    )

    plt.close()

    return filename


# =========================================================
# RUN
# =========================================================

def main():

    print("INVEST ZONE START")

    # 4H
    raw_4h = get_ohlc(240)

    # 1H
    raw_1h = get_ohlc(60)

    # 30M
    raw_30m = get_ohlc(30)

    print(
        "Candles:",
        len(raw_4h),
        len(raw_1h),
        len(raw_30m)
    )

    context_4h = analyze_4h(
        raw_4h
    )

    analysis = analyze_setup(
        raw_1h
    )

    confirmation_30m = analyze_30m(
        raw_30m
    )

    chart = create_chart(
        raw_1h,
        analysis,
        context_4h,
        confirmation_30m
    )

    # -----------------------------------------
    # TELEGRAM TEXT
    # -----------------------------------------

    message = (
        "INVEST ZONE\n\n"
        f"{analysis['status']}\n\n"
        f"BTC: ${analysis['current']:,.2f}\n"
        f"Resistance: "
        f"${analysis['resistance']:,.2f}\n"
        f"Distance: "
        f"{analysis['distance']:.2f}%\n\n"
        f"4H: {context_4h}\n"
        f"30M: {confirmation_30m}\n\n"
        "1H STRUCTURE\n"
        f"Higher Lows: "
        f"{'YES' if analysis['higher_lows'] else 'NO'}\n"
        f
