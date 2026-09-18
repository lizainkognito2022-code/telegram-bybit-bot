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
            "approach": False,
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
    # HIGHER LOWS
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
    # ПОДЖАТИЕ
    #
    # Разбиваем последние 9 свечей на 3 блока.
    # Проверяем, что диапазон каждого блока
    # постепенно уменьшается.
    # -----------------------------------------------------

    block_1 = recent[-9:-6]
    block_2 = recent[-6:-3]
    block_3 = recent[-3:]

    range_1 = (
        max(c["high"] for c in block_1)
        -
        min(c["low"] for c in block_1)
    )

    range_2 = (
        max(c["high"] for c in block_2)
        -
        min(c["low"] for c in block_2)
    )

    range_3 = (
        max(c["high"] for c in block_3)
        -
        min(c["low"] for c in block_3)
    )

    compression = (
        range_2 < range_1
        and
        range_3 < range_2
    )

    # -----------------------------------------------------
    # ПОСТЕПЕННОЕ ПРИБЛИЖЕНИЕ К RESISTANCE
    # -----------------------------------------------------

    distance_1 = (
        resistance -
        max(c["close"] for c in block_1)
    )

    distance_2 = (
        resistance -
        max(c["close"] for c in block_2)
    )

    distance_3 = (
        resistance -
        max(c["close"] for c in block_3)
    )

    approach = (
        distance_2 < distance_1
        and
        distance_3 < distance_2
    )

    near_resistance = (
        0 <= distance <= 1.5
    )

    # -----------------------------------------------------
    # VOLUME
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

    signal = (
        higher_low_ok
        and compression
        and approach
        and near_resistance
    )

    return {
        "signal": signal,
        "resistance": resistance,
        "distance": distance,
        "higher_lows": higher_lows,
        "compression": compression,
        "approach": approach,
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


# =========================================================
# 30M CONFIRMATION
# =========================================================

def analyze_30m(candles, setup_a, setup_b, setup_c):

    if len(candles) < 12:
        return {
            "status": "UNKNOWN",
            "structure": "UNKNOWN",
            "volume_ratio": 0
        }

    recent = candles[-12:]

    structure = detect_structure(
        candles
    )

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

    # ---------------------------------------------
    # Если есть A — 30M должен показывать
    # поджатие / восходящую структуру.
    # ---------------------------------------------

    if setup_a["signal"]:

        if structure == "UP":
            status = "🟢 ПОДТВЕРЖДАЕТ A"
        else:
            status = "🟡 A ЕСТЬ, 30M НЕ ПОДТВЕРЖДАЕТ"

    # ---------------------------------------------
    # Если есть B — 30M должен удерживать уровень.
    # ---------------------------------------------

    elif setup_b["signal"]:

        if structure == "UP":
            status = "🟢 ПОДТВЕРЖДАЕТ B"
        else:
            status = "🟡 B ЕСТЬ, 30M НЕ ПОДТВЕРЖДАЕТ"

    # ---------------------------------------------
    # Если есть C — 30M должен показать
    # разворот структуры.
    # ---------------------------------------------

    elif setup_c["signal"]:

        if structure == "UP":
            status = "🟢 ПОДТВЕРЖДАЕТ C"
        else:
            status = "🟡 C ЕСТЬ, 30M НЕ ПОДТВЕРЖДАЕТ"

    else:
        status = "⚪ НЕТ SETUP ДЛЯ ПОДТВЕРЖДЕНИЯ"

    return {
        "status": status,
        "structure": structure,
        "volume_ratio": volume_ratio
    }


def yes_no(value):
    return "🟢 YES" if value else "⚪ NO"


def main():

    try:

        # =================================================
        # ТАЙМФРЕЙМЫ
        # =================================================

        hourly_raw = get_kraken_candles(60)

        thirty_raw = get_kraken_candles(30)

        four_hour_raw = get_kraken_candles(240)

        hourly = convert_candles(
            hourly_raw
        )

        thirty = convert_candles(
            thirty_raw
        )

        four_hour = convert_candles(
            four_hour_raw
        )

        if len(hourly) < 25:
            raise Exception(
                "Недостаточно 1H свечей"
            )

        if len(thirty) < 25:
            raise Exception(
                "Недостаточно 30M свечей"
            )

        if len(four_hour) < 20:
            raise Exception(
                "Недостаточно 4H свечей"
            )

        # =================================================
        # 4H
        # =================================================

        structure = detect_structure(
            four_hour
        )

        # =================================================
        # 1H
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
        # 30M
        # =================================================

        thirty_analysis = analyze_30m(
            thirty,
            setup_a,
            setup_b,
            setup_c
        )

        # =================================================
        # PRICE
        # =================================================

        last_price = hourly[-1]["close"]

        # =================================================
        # VOLUME 1H
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
        # RESULT
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
        # MESSAGE
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

            "Approach: "
            f"{yes_no(setup_a['approach'])}\n"

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

            "30M CONFIRMATION\n\n"

            f"30M Structure: "
            f"{structure_text(thirty_analysis['structure'])}\n"

            f"30M Volume: "
            f"{thirty_analysis['volume_ratio']:.2f}x\n"

            f"30M Status: "
            f"{thirty_analysis['status']}\n\n"

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

            "30M Confirmation: "
            f"{'🟢 ЕСТЬ' if 'ПОДТВЕРЖДАЕТ' in thirty_analysis['status'] else '⚪ НЕТ'}\n"

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

            "4H / 1H / 30M: РЕАЛЬНЫЕ OHLCV\n\n"

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
