import os
import requests
import matplotlib.pyplot as plt

BOT_TOKEN = os.environ["BOT_TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]
KRAKEN_URL = "https://api.kraken.com/0/public/OHLC"


def get_ohlc(interval):
    r = requests.get(
        KRAKEN_URL,
        params={"pair": "XBTUSD", "interval": interval},
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()

    if data.get("error"):
        raise RuntimeError(str(data["error"]))

    result = data["result"]
    pair = next(k for k in result if k != "last")

    return [
        {
            "time": float(x[0]),
            "open": float(x[1]),
            "high": float(x[2]),
            "low": float(x[3]),
            "close": float(x[4]),
            "volume": float(x[6]),
        }
        for x in result[pair]
    ]


def average(values):
    return sum(values) / len(values) if values else 0.0


def context_4h(candles):
    closes = [x["close"] for x in candles]

    if len(closes) < 10:
        return "NEUTRAL"

    old = average(closes[-10:-5])
    new = average(closes[-5:])

    if new > old * 1.01:
        return "UP"

    if new < old * 0.99:
        return "DOWN"

    return "RANGE"


def resistance(candles):
    highs = [x["high"] for x in candles]

    if len(highs) >= 20:
        return max(highs[-20:-3])

    return max(highs)


def swing_lows(candles):
    lows = [x["low"] for x in candles]
    result = []

    for i in range(2, len(lows) - 2):
        if (
            lows[i] < lows[i - 1]
            and lows[i] < lows[i - 2]
            and lows[i] < lows[i + 1]
            and lows[i] < lows[i + 2]
        ):
            result.append(i)

    return result


def higher_lows(candles):
    indexes = swing_lows(candles)

    if len(indexes) < 3:
        return False, indexes[-3:]

    last = indexes[-3:]

    values = [
        candles[i]["low"]
        for i in last
    ]

    return values[0] < values[1] < values[2], last


def compression(candles):
    if len(candles) < 20:
        return False

    ranges = [
        x["high"] - x["low"]
        for x in candles
    ]

    old = average(ranges[-20:-10])
    new = average(ranges[-10:])

    return old > 0 and new < old * 0.85


def approach(candles, level):
    price = candles[-1]["close"]

    distance = abs(level - price) / price

    return distance <= 0.015


def breakout(candles, level):
    if len(candles) < 20:
        return False

    price = candles[-1]["close"]

    if price <= level * 1.002:
        return False

    volumes = [
        x["volume"]
        for x in candles
    ]

    base = average(volumes[-20:-5])

    return (
        base > 0
        and volumes[-1] >= base * 1.30
    )


def confirm_30m(candles):
    if len(candles) < 10:
        return False

    closes = [
        x["close"]
        for x in candles
    ]

    return closes[-1] >= max(closes[-6:-1])


def analyze(c4, c1, c30):
    price = c1[-1]["close"]
    level = resistance(c1)

    hl, hl_indexes = higher_lows(c1)
    comp = compression(c1)
    near = approach(c1, level)
    bo = breakout(c1, level)
    conf = confirm_30m(c30)
    ctx = context_4h(c4)

    distance = (
        abs(level - price)
        / price
        * 100
    )

    formation = (
        ctx != "DOWN"
        and hl
        and comp
        and near
    )

    signal = (
        ctx != "DOWN"
        and bo
        and conf
    )

    return {
        "price": price,
        "resistance": level,
        "distance": distance,
        "context": ctx,
        "higher_lows": hl,
        "compression": comp,
        "approach": near,
        "breakout": bo,
        "confirmation": conf,
        "formation": formation,
        "signal": signal,
        "hl_indexes": hl_indexes,
    }


def rsi(candles, period=14):
    closes = [
        x["close"]
        for x in candles
    ]

    if len(closes) < period + 1:
        return [50.0] * len(closes)

    values = [50.0] * period

    for i in range(period, len(closes)):
        changes = [
            closes[j] - closes[j - 1]
            for j in range(
                i - period + 1,
                i + 1
            )
        ]

        gains = [
            max(v, 0)
            for v in changes
        ]

        losses = [
            max(-v, 0)
            for v in changes
        ]

        avg_gain = average(gains)
        avg_loss = average(losses)

        if avg_loss == 0:
            value = 100.0
        else:
            rs = avg_gain / avg_loss
            value = 100.0 - (
                100.0 / (1.0 + rs)
            )

        values.append(value)

    return values


def make_chart(candles, result):
    data = candles[-60:]

    fig, axes = plt.subplots(
        3,
        1,
        figsize=(12, 9),
        gridspec_kw={
            "height_ratios": [5, 1.5, 1.5]
        },
        sharex=True
    )

    ax_price = axes[0]
    ax_volume = axes[1]
    ax_rsi = axes[2]

    for i, candle in enumerate(data):
        ax_price.vlines(
            i,
            candle["low"],
            candle["high"],
            linewidth=1
        )

        ax_price.vlines(
            i,
            min(
                candle["open"],
                candle["close"]
            ),
            max(
                candle["open"],
                candle["close"]
            ),
            linewidth=5
        )

    start = len(candles) - len(data)

    for index in result["hl_indexes"]:
        visible_index = index - start

        if 0 <= visible_index < len(data):
            low = data[visible_index]["low"]

            ax_price.scatter(
                visible_index,
                low,
                s=60
            )

            ax_price.annotate(
                "HL",
                (visible_index, low),
                xytext=(3, -14),
                textcoords="offset points"
            )

    ax_price.axhline(
        result["resistance"],
        linestyle="--",
        linewidth=1.5
    )

    ax_price.axhline(
        result["price"],
        linestyle=":",
        linewidth=1
    )

    ax_price.set_ylabel("BTC/USD")
    ax_price.grid(alpha=0.2)

    volumes = [
        x["volume"]
        for x in data
    ]

    ax_volume.bar(
        range(len(data)),
        volumes,
        width=0.7
    )

    ax_volume.set_ylabel("Volume")
    ax_volume.grid(alpha=0.2)

    rsi_values = rsi(data)

    ax_rsi.plot(
        range(len(data)),
        rsi_values,
        linewidth=1.5
    )

    ax_rsi.axhline(
        70,
        linestyle="--",
        linewidth=0.8
    )

    ax_rsi.axhline(
        30,
        linestyle="--",
        linewidth=0.8
    )

    ax_rsi.set_ylim(0, 100)
    ax_rsi.set_ylabel("RSI")
    ax_rsi.grid(alpha=0.2)

    if result["signal"]:
        title = "INVEST ZONE — SIGNAL"
    elif result["formation"]:
        title = "INVEST ZONE — ПОДЖАТИЕ"
    else:
        title = "INVEST ZONE — НАБЛЮДЕНИЕ"

    ax_price.set_title(
        title,
        loc="left",
        fontsize=16
    )

    fig.tight_layout()

    filename = "invest_zone.png"

    fig.savefig(
        filename,
        dpi=150
    )

    plt.close(fig)

    return filename


def send_photo(filename, caption):
    url = (
        "https://api.telegram.org/bot"
        + BOT_TOKEN
        + "/sendPhoto"
    )

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


def main():
    c4 = get_ohlc(240)
    c1 = get_ohlc(60)
    c30 = get_ohlc(30)

    result = analyze(
        c4,
        c1,
        c30
    )

    if result["signal"]:
        status = "🟢 SIGNAL"
    elif result["formation"]:
        status = "🟡 ПОДЖАТИЕ"
    else:
        status = "⚪ НАБЛЮДЕНИЕ"

    caption = "\n".join([
        "INVEST ZONE",
        "",
        status,
        "",
        f"BTC: ${result['price']:,.2f}",
        f"Resistance: ${result['resistance']:,.2f}",
        f"Distance: {result['distance']:.2f}%",
        "",
        f"4H Context: {result['context']}",
        (
            "1H Higher Lows: "
            + ("YES" if result["higher_lows"] else "NO")
        ),
        (
            "1H Compression: "
            + ("YES" if result["compression"] else "NO")
        ),
        (
            "1H Approach: "
            + ("YES" if result["approach"] else "NO")
        ),
        (
            "Breakout: "
            + ("YES" if result["breakout"] else "NO")
        ),
        (
            "30M Confirmation: "
            + (
                "YES"
                if result["confirmation"]
                else "NO"
            )
        ),
    ])

    filename = make_chart(
        c1,
        result
    )

    send_photo(
        filename,
        caption
    )


if __name__ == "__main__":
    main()
