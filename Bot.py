import os
import io
import requests

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle


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


def create_chart(candles, resistance):
    """
    Создаёт свечной график BTC/USD.

    Зелёная свеча:
    close >= open

    Красная свеча:
    close < open

    Фон:
    чёрный

    Показываются:
    последние 80 свечей 1H
    """

    candles = candles[-80:]

    if not candles:
        raise RuntimeError(
            "Нет данных для построения графика"
        )

    fig, ax = plt.subplots(
        figsize=(14, 7),
        facecolor="black"
    )

    ax.set_facecolor("black")

    for index, candle in enumerate(candles):

        open_price = candle["open"]
        close_price = candle["close"]
        high = candle["high"]
        low = candle["low"]

        # Цвет свечи.
        if close_price >= open_price:
            candle_color = "#00ff66"
        else:
            candle_color = "#ff3030"

        # Тень свечи.
        ax.vlines(
            index,
            low,
            high,
            color=candle_color,
            linewidth=1.2,
            zorder=2
        )

        # Нижняя граница тела.
        body_low = min(
            open_price,
            close_price
        )

        # Высота тела.
        body_height = abs(
            close_price - open_price
        )

        # Для doji делаем маленькое
        # видимое тело.
        if body_height == 0:
            body_height = max(
                (high - low) * 0.01,
                close_price * 0.0001
            )

        # Тело свечи.
        body = Rectangle(
            (
                index - 0.32,
                body_low
            ),
            0.64,
            body_height,
            facecolor=candle_color,
            edgecolor=candle_color,
            linewidth=0.8,
            zorder=3
        )

        ax.add_patch(body)

    # -----------------------------------------
    # Уровень сопротивления
    # -----------------------------------------

    ax.axhline(
        resistance,
        color="white",
        linestyle="--",
        linewidth=1.2,
        alpha=0.8
    )

    ax.text(
        len(candles) - 1,
        resistance,
        f" Resistance ${resistance:,.0f}",
        color="white",
        fontsize=9,
        ha="right",
        va="bottom"
    )

    # -----------------------------------------
    # Оформление
    # -----------------------------------------

    ax.set_title(
        "BTC/USD — 1H",
        color="white",
        fontsize=16,
        fontweight="bold",
        pad=12
    )

    ax.set_xlabel(
        "Свечи",
        color="#aaaaaa"
    )

    ax.set_ylabel(
        "Цена, USD",
        color="#aaaaaa"
    )

    ax.tick_params(
        axis="x",
        colors="white",
        labelsize=8
    )

    ax.tick_params(
        axis="y",
        colors="white",
        labelsize=9
    )

    ax.grid(
        True,
        color="#333333",
        linewidth=0.6,
        alpha=0.7
    )

    for spine in ax.spines.values():
        spine.set_color("#444444")

    ax.set_xlim(
        -1,
        len(candles)
    )

    fig.tight_layout()

    # -----------------------------------------
    # PNG в оперативной памяти
    # -----------------------------------------

    image_buffer = io.BytesIO()

    fig.savefig(
        image_buffer,
        format="png",
        dpi=150,
        facecolor="black",
        bbox_inches="tight"
    )

    plt.close(fig)

    image_buffer.seek(0)

    return image_buffer


def send_photo(photo, caption):
    """
    Отправляет ОДНО сообщение:
    график + текст анализа.
    """

    url = (
        "https://api.telegram.org/bot"
        + BOT_TOKEN
        + "/sendPhoto"
    )

    response = requests.post(
        url,
        data={
            "chat_id": CHAT_ID,
            "caption": caption
        },
        files={
            "photo": (
                "btc_chart.png",
                photo,
                "image/png"
            )
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
    # -----------------------------------------
    # Получаем данные
    # -----------------------------------------

    candles_4h = get_ohlc(240)

    candles_1h = get_ohlc(60)

    candles_30m = get_ohlc(30)

    # -----------------------------------------
    # Анализ
    # -----------------------------------------

    result = analyze(
        candles_4h,
        candles_1h,
        candles_30m
    )

    # -----------------------------------------
    # Статус
    # -----------------------------------------

    if result["signal"]:
        status = "🟢 СИГНАЛ"

    elif result["formation"]:
        status = "🟡 ПОДЖАТИЕ"

    elif (
        result["breakout"]
        or result["price"] > result["resistance"]
    ):
        status = "🔵 ПРОБОЙ НАБЛЮДАЕМ"

    else:
        status = "⚪ НАБЛЮДЕНИЕ"

    # -----------------------------------------
    # Текст под графиком
    # -----------------------------------------

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

    # -----------------------------------------
    # Создаём график
    # -----------------------------------------

    chart = create_chart(
        candles_1h,
        result["resistance"]
    )

    # -----------------------------------------
    # Отправляем график + анализ
    # ОДНИМ сообщением
    # -----------------------------------------

    send_photo(
        chart,
        message
    )


if __name__ == "__main__":
    main()
