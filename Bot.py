import os
import requests
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec

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
            f"Kraken error: {data['error']}"
        )

    result = data["result"]

    pair = next(
        key for key in result
        if key != "last"
    )

    candles = []

    for row in result[pair]:
        candles.append({
            "time": float(row[0]),
            "open": float(row[1]),
            "high": float(row[2]),
            "low": float(row[3]),
            "close": float(row[4]),
            "volume": float(row[6])
        })

    return candles


def avg(values):
    if values:
        return sum(values) / len(values)

    return 0.0


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

    resistance = find_resistance(c1h)

    higher_lows, low_indexes = check_higher_lows(
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

    context = context_4h(c4h)

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
        "resistance": resistance,
        "distance": distance,
        "context": context,
        "higher_lows": higher_lows,
        "compression": compression,
        "approach": approach,
        "breakout": breakout,
        "confirmation": confirmation,
        "formation": formation,
        "signal": signal,
        "low_indexes": low_indexes
    }


def rsi_values(candles, period=14):
    closes = [
        candle["close"]
        for candle in candles
    ]

    if len(closes) <= period:
        return [50.0] * len(closes)

    gains = []
    losses = []

    for i in range(1, len(closes)):
        change = (
            closes[i]
            - closes[i - 1]
        )

        gains.append(
            max(change, 0)
        )

        losses.append(
            max(-change, 0)
        )

    result = [50.0] * period

    for i in range(period, len(closes)):
        avg_gain = avg(
            gains[i - period:i]
        )

        avg_loss = avg(
            losses[i - period:i]
        )

        if avg_loss == 0:
            value = 100.0
        else:
            rs = avg_gain / avg_loss

            value = (
                100
                - 100 / (1 + rs)
            )

        result.append(value)

    return result


def draw_candles(ax, candles):
    for i, candle in enumerate(candles):
        ax.vlines(
            i,
            candle["low"],
            candle["high"],
            linewidth=1
        )

        ax.vlines(
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


def make_chart(candles, result):
    visible = candles[-60:]

    x = list(
        range(len(visible))
    )

    fig = plt.figure(
        figsize=(15, 9)
    )

    grid = GridSpec(
        3,
        2,
        figure=fig,
        width_ratios=[3.8, 1.5],
        height_ratios=[5, 1.4, 1.2],
        wspace=0.08,
        hspace=0.08
    )

    ax_price = fig.add_subplot(
        grid[0, 0]
    )

    ax_volume = fig.add_subplot(
        grid[1, 0],
        sharex=ax_price
    )

    ax_rsi = fig.add_subplot(
        grid[2, 0],
        sharex=ax_price
    )

    ax_info = fig.add_subplot(
        grid[:, 1]
    )

    draw_candles(
        ax_price,
        visible
    )

    start_index = (
        len(candles)
        - len(visible)
    )

    for index in result["low_indexes"]:
        visible_index = (
            index
            - start_index
        )

        if (
            0
            <= visible_index
            < len(visible)
        ):
            price = visible[
                visible_index
            ]["low"]

            ax_price.scatter(
                visible_index,
                price,
                s=55
            )

            ax_price.annotate(
                "HL",
                (
                    visible_index,
                    price
                ),
                xytext=(4, -14),
                textcoords="offset points",
                fontsize=9
            )

    resistance = result["resistance"]
    current = result["price"]

    ax_price.axhline(
        resistance,
        linestyle="--",
        linewidth=1.5
    )

    ax_price.axhline(
        current,
        linestyle=":",
        linewidth=1
    )

    ax_price.text(
        len(visible) - 1,
        resistance,
        f" Resistance ${resistance:,.0f}",
        va="bottom",
        ha="right",
        fontsize=9
    )

    ax_price.text(
        len(visible) - 1,
        current,
        f" BTC ${current:,.0f}",
        va="top",
        ha="right",
        fontsize=9
    )

    volumes = [
        candle["volume"]
        for candle in visible
    ]

    ax_volume.bar(
        x,
        volumes,
        width=0.7,
        alpha=0.7
    )

    rsi = rsi_values(
        visible
    )

    ax_rsi.plot(
        x,
        rsi,
        linewidth=1.5
    )

    ax_rsi.axhline(
        70,
        linestyle="--",
        linewidth=0.8,
        alpha=0.5
    )

    ax_rsi.axhline(
        30,
        linestyle="--",
        linewidth=0.8,
        alpha=0.5
    )

    ax_rsi.set_ylim(
        0,
        100
    )

    if result["signal"]:
        status = "SIGNAL"

    elif result["formation"]:
        status = "ПОДЖАТИЕ"

    else:
        status = "НАБЛЮДЕНИЕ"

    ax_price.set_title(
        "INVEST ZONE  |  BTC/USD  |  "
        f"1H  |  {status}",
        fontsize=16,
        loc="left"
    )

    ax_price.set_ylabel(
        "BTC / USD"
    )

    ax_volume.set_ylabel(
        "Volume"
    )

    ax_rsi.set_ylabel(
        "RSI"
    )

    ax_rsi.set_xlabel(
        "Последние 60 свечей"
    )

    for axis in [
        ax_price,
        ax_volume,
        ax_rsi
    ]:
        axis.grid(
            alpha=0.18
        )

    plt.setp(
        ax_price.get_xticklabels(),
        visible=False
    )

    plt.setp(
        ax_volume.get_xticklabels(),
        visible=False
    )

    ax_info.axis("off")

    ax_info.text(
        0.03,
        0.96,
        "INVEST ZONE",
        fontsize=22,
        fontweight="bold",
        va="top"
    )

    ax_info.text(
        0.03,
        0.88,
        status,
        fontsize=18,
        fontweight="bold",
        va="top"
    )

    lines = [
        f"BTC: ${current:,.2f}",
        f"Resistance: ${resistance:,.2f}",
        f"Distance: {result['distance']:.2f}%",
        "",
        f"4H Context: {result['context']}",
        f"1H Higher Lows: "
        f"{'YES' if result['higher_lows'] else 'NO'}",
        f"1H Compression: "
        f"{'YES' if result['compression'] else 'NO'}",
        f"1H Approach: "
        f"{'YES' if result['approach'] else 'NO'}",
        f"Breakout: "
        f"{'YES' if result['breakout'] else 'NO'}",
        f"30M Confirmation: "
        f"{'YES' if result['confirmation'] else 'NO'}"
    ]

    ax_info.text(
        0.03,
        0.78,
        "\n".join(lines),
        fontsize=12,
        linespacing=1.8,
        va="top"
    )

    ax_info.text(
        0.03,
        0.25,
        "ЛОГИКА INVEST ZONE\n\n"
        "4H → контекст\n"
        "1H → формация\n"
        "30M → подтверждение\n\n"
        "Не покупаем вертикальный памп.\n"
        "Ждём изменение баланса сил.",
        fontsize=11,
        va="top"
    )

    filename = (
        "invest_zone_real_chart.png"
    )

    fig.savefig(
        filename,
        dpi=160,
        bbox_inches="tight"
    )

    plt.close(fig)

    return filename


def send_photo(filename, caption):
    url = (
        f"https://api.telegram.org/"
        f"bot{BOT_TOKEN}/sendPhoto"
    )

    with open(
        filename,
        "rb"
    ) as photo:

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

    caption = (
        "INVEST ZONE\n\n"
        f"{status}\n\n"
        f"BTC: ${result['price']:,.2f}\n"
        f"Resistance: "
        f"${result['resistance']:,.2f}\n"
        f"Distance: "
        f"{result['distance']:.2f}%\n\n"
        f"4H Context: "
        f"{result['context']}\n"
        f"1H Higher Lows: "
        f"{'YES' if result['higher_lows'] else 'NO'}\n"
        f"1H Compression: "
        f"{'YES' if result['compression'] else 'NO'}\n"
        f"1H Approach: "
        f"{'YES' if result['approach'] else 'NO'}\n"
        f"Breakout: "
        f"{'YES' if result['breakout'] else 'NO'}\n"
        f"30M Confirmation: "
       
