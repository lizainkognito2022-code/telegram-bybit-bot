import os
import requests
import matplotlib.pyplot as plt

BOT_TOKEN = os.environ["BOT_TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]

KRAKEN_URL = "https://api.kraken.com/0/public/OHLC"


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
            f"Kraken error: {data['error']}"
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


def avg(values):
    if not values:
        return 0.0

    return sum(values) / len(values)


def context_4h(candles):
    if len(candles) < 10:
        return "NEUTRAL"

    closes = [
        candle["close"]
        for candle in candles
    ]

    old = avg(closes[-10:-5])
    new = avg(closes[-5:])

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

    if len(highs) < 20:
        return max(highs)

    return max(highs[-20:-3])


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
        return False, []

    recent = indexes[-3:]

    lows = [
        candles[i]["low"]
        for i in recent
    ]

    ok = (
        lows[0] < lows[1]
        and lows[1] < lows[2]
    )

    return ok, recent


def check_compression(candles):
    if len(candles) < 20:
        return False

    ranges = [
        candle["high"] - candle["low"]
        for candle in candles
    ]

    old_range = avg(ranges[-20:-10])
    new_range = avg(ranges[-10:])

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

    old_volume = avg(volumes[-20:-5])

    if old_volume <= 0:
        return False

    return volumes[-1] >= old_volume * 1.30


def check_30m_confirmation(candles):
    if len(candles) < 10:
        return False

    closes = [
        candle["close"]
        for candle in candles
    ]

    previous_high = max(closes[-6:-1])

    return closes[-1] >= previous_high


def analyze(c4h, c1h, c30):
    price = c1h[-1]["close"]

    context = context_4h(c4h)

    resistance = find_resistance(c1h)

    higher_lows, low_indexes = check_higher_lows(c1h)

    compression = check_compression(c1h)

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
        "signal": signal,
        "low_indexes": low_indexes
    }


def make_chart(candles, result):
    visible = candles[-40:]

    closes = [
        candle["close"]
        for candle in visible
    ]

    highs = [
        candle["high"]
        for candle in visible
    ]

    lows = [
        candle["low"]
        for candle in visible
    ]

    x = list(range(len(visible)))

    fig, ax = plt.subplots(
        figsize=(12, 7)
    )

    ax.plot(
        x,
        closes,
        linewidth=2,
        label="Close"
    )

    ax.plot(
        x,
        highs,
        alpha=0.25,
        linewidth=1
    )

    ax.plot(
        x,
        lows,
        alpha=0.25,
        linewidth=1
    )

    resistance = result["resistance"]

    ax.axhline(
        resistance,
        linestyle="--",
        linewidth=2,
        label="Resistance"
    )

    start_index = (
        len(candles)
        - len(visible)
    )

    for index in result["low_indexes"]:
        visible_index = (
            index - start_index
        )

        if 0 <= visible_index < len(visible):
            low_price = visible[
                visible_index
            ]["low"]

            ax.scatter(
                visible_index,
                low_price,
                s=70
            )

            ax.annotate(
                "HL",
                (
                    visible_index,
                    low_price
                ),
                xytext=(4, -12),
                textcoords="offset points"
            )

    if result["signal"]:
        title = "INVEST ZONE — SIGNAL"

    elif result["formation"]:
        title = "INVEST ZONE — ПОДЖАТИЕ"

    else:
        title = "INVEST ZONE — НАБЛЮДЕНИЕ"

    ax.set_title(
        title,
        fontsize=16
    )

    ax.set_xlabel(
        "1H candles"
    )

    ax.set_ylabel(
        "BTC / USD"
    )

    ax.grid(alpha=0.2)

    ax.legend()

    fig.tight_layout()

    filename = "invest_zone.png"

    fig.savefig(
        filename,
        dpi=150
    )

    plt.close(fig)

    return filename


def main():
    c4h = get_ohlc(240)

    c1h = get_ohlc(60)

    c30 = get_ohlc(30)

    result = analyze(
        c4h,
        c1h,
        c30
    )

    if result["signal"]:
        status = "🟢 SIGNAL"

    elif result["formation"]:
        status = "🟡 ПОДЖАТИЕ"

    else:
        status = "⚪ НАБЛЮДЕНИЕ"

    message = (
        "INVEST ZONE\n\n"
        f"{status}\n\n"
        f"BTC: ${result['price']:,.2f}\n"
        f"Resistance: ${result['resistance']:,.2f}\n"
        f"Distance: {result['distance']:.2f}%\n\n"
        f"4H Context: {result['context']}\n"
        f"1H Higher Lows: "
        f"{'YES' if result['higher_lows'] else 'NO'}\n"
        f"1H Compression: "
        f"{'YES' if result['compression'] else 'NO'}\n"
        f"1H Approach: "
        f"{'YES' if result['approach'] else 'NO'}\n"
        f"Breakout: "
        f"{'YES' if result['breakout'] else 'NO'}\n"
        f"30M Confirmation: "
        f"{'YES' if result['confirmation'] else 'NO'}"
    )

    filename = make_chart(
        c1h,
        result
    )

    send_photo(
        filename,
        message
    )


if __name__ == "__main__":
    main()
