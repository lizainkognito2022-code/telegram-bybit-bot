import os
import requests

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

TELEGRAM_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"
KRAKEN_URL = "https://api.kraken.com/0/public"


def send_message(chat_id, text):
    requests.post(
        f"{TELEGRAM_URL}/sendMessage",
        json={
            "chat_id": chat_id,
            "text": text
        },
        timeout=15
    )


def get_kraken_candles(interval):
    response = requests.get(
        f"{KRAKEN_URL}/OHLC",
        params={
            "pair": "XBTUSD",
            "interval": interval
        },
        timeout=20
    )

    response.raise_for_status()

    data = response.json()

    if data.get("error"):
        raise Exception(
            f"Kraken API: {data['error']}"
        )

    result = data.get("result", {})

    candles = result.get("XXBTZUSD")

    if not candles:
        candles = result.get("XBTUSD")

    if not candles:
        raise Exception(
            "Kraken не вернул BTC/USD свечи"
        )

    return candles


def convert_candles(raw_candles):
    candles = []

    for item in raw_candles:

        candles.append({
            "time": int(float(item[0])),
            "open": float(item[1]),
            "high": float(item[2]),
            "low": float(item[3]),
            "close": float(item[4]),
            "vwap": float(item[5]),
            "volume": float(item[6]),
            "count": int(item[7])
        })

    return candles


def structure_text(structure):

    if structure == "UP":
        return "🟢 ВОСХОДЯЩАЯ"

    if structure == "DOWN":
        return "🔴 НИСХОДЯЩАЯ"

    if structure == "RANGE":
        return "🟡 RANGE"

    return "⚪ НЕДОСТАТОЧНО ДАННЫХ"


def detect_structure(candles):

    if len(candles) < 20:
        return "UNKNOWN"

    recent = candles[-20:]

    first_half = recent[:10]
    second_half = recent[10:]

    first_high = max(
        candle["high"]
        for candle in first_half
    )

    second_high = max(
        candle["high"]
        for candle in second_half
    )

    first_low = min(
        candle["low"]
        for candle in first_half
    )

    second_low = min(
        candle["low"]
        for candle in second_half
    )

    if (
        second_high > first_high
        and second_low > first_low
    ):
        return "UP"

    if (
        second_high < first_high
        and second_low < first_low
    ):
        return "DOWN"

    return "RANGE"


# =========================================================
# SETUP A
# ПОДЖАТИЕ → ПРОБОЙ
# =========================================================

def analyze_setup_a(candles):

    if len(candles) < 20:
        return {
            "signal": False,
            "resistance": 0,
            "distance": 999,
            "higher_lows": 0,
            "compression": False,
            "volume_ratio": 0
        }

    recent = candles[-20:]

    resistance = max(
        candle["high"]
        for candle in recent
    )

    current_price = recent[-1]["close"]

    distance = (
        (resistance - current_price)
        / resistance
        * 100
    )

    # -----------------------------------------------------
    # Ищем последовательность повышающихся минимумов
    # -----------------------------------------------------

    last_10 = recent[-10:]

    lows = [
        candle["low"]
        for candle in last_10
    ]

    higher_lows = 0

    for i in range(1, len(lows)):
        if lows[i] > lows[i - 1]:
            higher_lows += 1

    higher_low_ok = (
        higher_lows >= 3
    )

    # -----------------------------------------------------
    # Сжатие диапазона
    # -----------------------------------------------------

    first_range = (
        max(
            candle["high"]
            for candle in recent[:10]
        )
        -
        min(
            candle["low"]
            for candle in recent[:10]
        )
    )

    second_range = (
        max(
            candle["high"]
            for candle in recent[10:]
        )
        -
        min(
            candle["low"]
            for candle in recent[10:]
        )
    )

    compression = (
        second_range < first_range
    )

    # -----------------------------------------------------
    # Цена должна быть близко к сопротивлению
    # -----------------------------------------------------

    near_resistance = (
        0 <= distance <= 1.5
    )

    # -----------------------------------------------------
    # Объём
    # -----------------------------------------------------

    volumes = [
        candle["volume"]
        for candle in candles[-21:-1]
    ]

    average_volume = (
        sum(volumes) / len(volumes)
        if volumes
        else 0
    )

    current_volume = recent[-1]["volume"]

    volume_ratio = (
        current_volume / average_volume
        if average_volume > 0
        else 0
    )

    # Для самого поджатия объём не обязан быть высоким.
    # Главное — структура и сжатие.
    signal = (
        higher_low_ok
        and compression
        and near_resistance
    )

    return {
        "signal": signal,
        "resistance": resistance,
        "distance": distance,
        "higher_lows": higher_lows,
        "compression": compression,
        "volume_ratio": volume_ratio
    }


# =========================================================
# SETUP B
# ПРОБОЙ → РЕТЕСТ → ПРОДОЛЖЕНИЕ
# =========================================================

def analyze_setup_b(candles):

    if len(candles) < 12:
        return {
            "signal": False,
            "resistance": 0,
            "breakout": False,
            "retest": False,
            "hold": False
        }

    recent = candles[-12:]

    resistance = max(
        candle["high"]
        for candle in recent[:-2]
    )

    breakout = (
        recent[-2]["close"]
        > resistance
    )

    retest = (
        recent[-1]["low"]
        <= resistance * 1.005
    )

    hold = (
        recent[-1]["close"]
        > resistance
    )

    signal = (
        breakout
        and retest
        and hold
    )

    return {
        "signal": signal,
        "resistance": resistance,
        "breakout": breakout,
        "retest": retest,
        "hold": hold
    }


# =========================================================
# SETUP C
# СНЯТИЕ ЛИКВИДНОСТИ → РАЗВОРОТ
# =========================================================

def analyze_setup_c(candles):

    if len(candles) < 12:
        return {
            "signal": False,
            "liquidity_low": 0,
            "sweep": False,
            "reclaim": False,
            "structure_shift": False
        }

    recent = candles[-12:]

    previous = recent[:-2]

    liquidity_low = min(
        candle["low"]
        for candle in previous
    )

    sweep = (
        recent[-2]["low"]
        < liquidity_low
    )

    reclaim = (
        recent[-1]["close"]
        > liquidity_low
    )

    # Простая проверка локального structure shift:
    # последняя свеча закрывается выше high
    # предыдущей свечи.
    structure_shift = (
        recent[-1]["close"]
        > recent[-2]["high"]
    )

    signal = (
        sweep
        and reclaim
        and structure_shift
    )

    return {
        "signal": signal,
        "liquidity_low": liquidity_low,
        "sweep": sweep,
        "reclaim": reclaim,
        "structure_shift": structure_shift
    }


def yes_no(value):
    return "🟢 YES" if value else "⚪ NO"


def main():

    try:

        # =================================================
        # ПОЛУЧАЕМ РЕАЛЬНЫЕ OHLCV
        # =================================================

        hourly_raw = get_kraken_candles(60)

        four_hour_raw = get_kraken_candles(240)

        hourly = convert_candles(
            hourly_raw
        )

        four_hour = convert_candles(
            four_hour_raw
        )

        if len(hourly) < 25:
            raise Exception(
                "Недостаточно 1H свечей"
            )

        if len(four_hour) < 20:
            raise Exception(
                "Недостаточно 4H свечей"
            )

        # =================================================
        # BTC CONTEXT / 4H
        # =================================================

        structure = detect_structure(
            four_hour
        )

        # =================================================
        # 1H SETUPS
        # =================================================

        setup_a = analyze_setup_a(
            hourly
        )

        setup_b = analyze_setup_b(
            hourly
        )

        setup_c = analyze_setup_c(
            hourly
        )

        # =================================================
        # PRICE
        # =================================================

        last_price = hourly[-1]["close"]

        # =================================================
        # VOLUME
        # =================================================

        volumes = [
            candle["volume"]
            for candle in hourly[-21:-1]
        ]

        average_volume = (
            sum(volumes) / len(volumes)
            if volumes
            else 0
        )

        current_volume = hourly[-1]["volume"]

        volume_ratio = (
            current_volume / average_volume
            if average_volume > 0
            else 0
        )

        # =================================================
        # РЕЗУЛЬТАТ
        # =================================================

        if setup_a["signal"]:
            result = (
                "🟢 A — ПОДЖАТИЕ → ПРОБОЙ"
            )

        elif setup_b["signal"]:
            result = (
                "🟢 B — ПРОБОЙ → РЕТЕСТ → "
                "ПРОДОЛЖЕНИЕ"
            )

        elif setup_c["signal"]:
            result = (
                "🟢 C — СНЯТИЕ ЛИКВИДНОСТИ → "
                "РАЗВОРОТ"
            )

        else:
            result = (
                "⚪ НЕТ КАЧЕСТВЕННОГО SETUP"
            )

        # =================================================
        # СООБЩЕНИЕ
        # =================================================

        message = (
            "🔎 INVEST ZONE\n\n"

            "BTC MARKET ANALYSIS\n\n"

            f"Цена: "
            f"{last_price:,.2f} USD\n\n"

            "━━━━━━━━━━━━━━━━━━\n"

            "BTC CONTEXT\n"
            f"{structure_text(structure)}\n\n"

            "4H STRUCTURE\n"
            f"{structure_text(structure)}\n\n"

            "━━━━━━━━━━━━━━━━━━\n"

            "1H SETUPS\n\n"

            "A — Поджатие → Пробой\n"
            f"{yes_no(setup_a['signal'])}\n\n"

            "B — Пробой → Ретест → "
            "Продолжение\n"
            f"{yes_no(setup_b['signal'])}\n\n"

            "C — Снятие ликвидности → "
            "Разворот\n"
            f"{yes_no(setup_c['signal'])}\n\n"

            "━━━━━━━━━━━━━━━━━━\n"

            "ДИАГНОСТИКА A\n\n"

            f"Resistance: "
            f"{setup_a['resistance']:,.2f}\n"

            f"До сопротивления: "
            f"{setup_a['distance']:.2f}%\n"

            f"Higher Lows: "
            f"{setup_a['higher_lows']} / 9\n"

            "Compression: "
            f"{yes_no(setup_a['compression'])}\n"

            f"Volume: "
            f"{setup_a['volume_ratio']:.2f}x\n\n"

            "ДИАГНОСТИКА B\n\n"

            f"Resistance: "
            f"{setup_b['resistance']:,.2f}\n"

            "Breakout: "
            f"{yes_no(setup_b['breakout'])}\n"

            "Retest: "
            f"{yes_no(setup_b['retest'])}\n"

            "Hold: "
            f"{yes_no(setup_b['hold'])}\n\n"

            "ДИАГНОСТИКА C\n\n"

            f"Liquidity Low: "
            f"{setup_c['liquidity_low']:,.2f}\n"

            "Sweep: "
            f"{yes_no(setup_c['sweep'])}\n"

            "Reclaim: "
            f"{yes_no(setup_c['reclaim'])}\n"

            "Structure Shift: "
            f"{yes_no(setup_c['structure_shift'])}\n\n"

            "━━━━━━━━━━━━━━━━━━\n"

            f"РЕЗУЛЬТАТ:\n"
            f"{result}\n\n"

            "━━━━━━━━━━━━━━━━━━\n"

            "ФИЛЬТРЫ\n\n"

            "BTC Context: "
            "🟢 ПРОВЕРЕН\n"

            "4H Structure: "
            f"{'🟢 UP' if structure == 'UP' else '🟡 НЕ UP'}\n"

            "1H Setup: "
            f"{'🟢 ЕСТЬ' if (setup_a['signal'] or setup_b['signal'] or setup_c['signal']) else '⚪ НЕТ'}\n"

            "Volume: "
            f"🟢 ПОДКЛЮЧЁН ({volume_ratio:.2f}x)\n"

            "Open Interest: "
            "⚪ НЕ ПОДКЛЮЧЁН\n"

            "Funding: "
            "⚪ НЕ ПОДКЛЮЧЁН\n"

            "Liquidity: "
            "⚪ НЕ ПОДКЛЮЧЁН\n"

            "Room to Target: "
            "⚪ НЕ ПОДКЛЮЧЁН\n"

            "Structural Stop Loss: "
            "⚪ НЕ ПОДКЛЮЧЁН\n\n"

            "Источник свечей: KRAKEN\n"

            "1H / 4H: РЕАЛЬНЫЕ OHLCV\n\n"

            "⚠️ Сигнал на вход пока НЕ выдаётся."
        )

        send_message(
            CHAT_ID,
            message
        )

    except Exception as e:

        send_message(
            CHAT_ID,
            f"🔴 Ошибка INVEST ZONE:\n{e}"
        )


if __name__ == "__main__":
    main()
