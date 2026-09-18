import os
import time
import requests


# =========================
# НАСТРОЙКИ
# =========================

BOT_TOKEN = os.environ["BOT_TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]

TELEGRAM_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

KRAKEN_SPOT_URL = "https://api.kraken.com/0/public"
KRAKEN_FUTURES_URL = "https://futures.kraken.com/api/charts/v1"

PAIR = "XBTUSD"
FUTURES_SYMBOL = "PI_XBTUSD"


# =========================
# TELEGRAM
# =========================

def send_message(text):
    response = requests.post(
        TELEGRAM_URL,
        json={
            "chat_id": CHAT_ID,
            "text": text
        },
        timeout=30
    )

    response.raise_for_status()


# =========================
# KRAKEN SPOT OHLC
# =========================

def get_kraken_candles(interval):
    response = requests.get(
        f"{KRAKEN_SPOT_URL}/OHLC",
        params={
            "pair": PAIR,
            "interval": interval
        },
        timeout=30
    )

    response.raise_for_status()

    data = response.json()

    if data.get("error"):
        raise Exception(str(data["error"]))

    result = data["result"]

    pair_key = [key for key in result.keys() if key != "last"][0]

    candles = result[pair_key]

    return candles


def convert_candles(raw):
    candles = []

    for candle in raw:
        candles.append({
            "time": int(candle[0]),
            "open": float(candle[1]),
            "high": float(candle[2]),
            "low": float(candle[3]),
            "close": float(candle[4]),
            "vwap": float(candle[5]),
            "volume": float(candle[6]),
            "count": int(candle[7])
        })

    return candles


# =========================
# VOLUME
# =========================

def get_volume_ratio(candles, lookback=20):
    if len(candles) < lookback + 1:
        return 0

    recent = candles[-1]["volume"]

    previous = [
        candle["volume"]
        for candle in candles[-lookback - 1:-1]
    ]

    average = sum(previous) / len(previous)

    if average == 0:
        return 0

    return recent / average


# =========================
# 4H STRUCTURE
# =========================

def detect_4h_structure(candles):
    if len(candles) < 10:
        return "UNKNOWN"

    recent = candles[-10:]

    highs = [c["high"] for c in recent]
    lows = [c["low"] for c in recent]

    first_half_high = max(highs[:5])
    second_half_high = max(highs[5:])

    first_half_low = min(lows[:5])
    second_half_low = min(lows[5:])

    if second_half_high > first_half_high and second_half_low > first_half_low:
        return "UP"

    if second_half_high < first_half_high and second_half_low < first_half_low:
        return "DOWN"

    return "RANGE"


# =========================
# SETUP A
# ПОДЖАТИЕ → ПРОБОЙ
# =========================

def setup_a(candles):
    if len(candles) < 20:
        return {
            "signal": False,
            "resistance": 0,
            "distance": 0,
            "higher_lows": 0,
            "compression": False,
            "approach": False,
            "volume_ratio": 0
        }

    recent = candles[-20:]

    resistance = max(c["high"] for c in recent)

    price = recent[-1]["close"]

    distance = ((resistance - price) / price) * 100

    lows = [c["low"] for c in recent[-10:]]

    higher_lows = 0

    for i in range(1, len(lows)):
        if lows[i] > lows[i - 1]:
            higher_lows += 1

    block1 = recent[-9:-6]
    block2 = recent[-6:-3]
    block3 = recent[-3:]

    range1 = max(c["high"] for c in block1) - min(
        c["low"] for c in block1
    )

    range2 = max(c["high"] for c in block2) - min(
        c["low"] for c in block2
    )

    range3 = max(c["high"] for c in block3) - min(
        c["low"] for c in block3
    )

    compression = (
        range2 < range1 and
        range3 < range2
    )

    closes1 = max(c["close"] for c in block1)
    closes2 = max(c["close"] for c in block2)
    closes3 = max(c["close"] for c in block3)

    distance1 = resistance - closes1
    distance2 = resistance - closes2
    distance3 = resistance - closes3

    approach = (
        distance2 < distance1 and
        distance3 < distance2
    )

    volume_ratio = get_volume_ratio(recent)

    near_resistance = 0 <= distance <= 1.5

    signal = (
        higher_lows >= 3 and
        compression and
        approach and
        near_resistance
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


# =========================
# SETUP B
# ПРОБОЙ → РЕТЕСТ → ПРОДОЛЖЕНИЕ
# =========================

def setup_b(candles):
    if len(candles) < 15:
        return {
            "signal": False,
            "resistance": 0,
            "breakout": False,
            "retest": False,
            "hold": False
        }

    recent = candles[-15:]

    resistance = max(
        c["high"]
        for c in recent[:-2]
    )

    previous = recent[-2]
    last = recent[-1]

    breakout = previous["close"] > resistance

    retest = last["low"] <= resistance * 1.005

    hold = last["close"] > resistance

    signal = (
        breakout and
        retest and
        hold
    )

    return {
        "signal": signal,
        "resistance": resistance,
        "breakout": breakout,
        "retest": retest,
        "hold": hold
    }


# =========================
# SETUP C
# СНЯТИЕ ЛИКВИДНОСТИ → РАЗВОРОТ
# =========================

def setup_c(candles):
    if len(candles) < 15:
        return {
            "signal": False,
            "liquidity_low": 0,
            "sweep": False,
            "reclaim": False,
            "structure_shift": False
        }

    recent = candles[-15:]

    previous_10 = recent[-12:-2]

    liquidity_low = min(
        c["low"]
        for c in previous_10
    )

    second_last = recent[-2]
    last = recent[-1]

    sweep = second_last["low"] < liquidity_low

    reclaim = last["close"] > liquidity_low

    structure_shift = (
        last["close"] > second_last["high"]
    )

    signal = (
        sweep and
        reclaim and
        structure_shift
    )

    return {
        "signal": signal,
        "liquidity_low": liquidity_low,
        "sweep": sweep,
        "reclaim": reclaim,
        "structure_shift": structure_shift
    }


# =========================
# 30M CONFIRMATION
# =========================

def analyze_30m(candles, setup_exists):
    structure = detect_4h_structure(candles)

    volume_ratio = get_volume_ratio(candles)

    if not setup_exists:
        status = "⚪ НЕТ SETUP ДЛЯ ПОДТВЕРЖДЕНИЯ"

    elif structure == "UP":
        status = "🟢 30M ПОДТВЕРЖДАЕТ"

    else:
        status = "🔴 30M НЕ ПОДТВЕРЖДАЕТ"

    return {
        "structure": structure,
        "volume_ratio": volume_ratio,
        "status": status
    }


# =========================
# KRAKEN FUTURES ANALYTICS
# =========================

def get_futures_analytics(
    symbol,
    analytics_type,
    interval=3600
):
    now = int(time.time())

    since = now - interval * 24

    url = (
        f"{KRAKEN_FUTURES_URL}/analytics/"
        f"{symbol}/{analytics_type}"
    )

    response = requests.get(
        url,
        params={
            "since": since,
            "interval": interval
        },
        timeout=30
    )

    response.raise_for_status()

    data = response.json()

    if data.get("error"):
        raise Exception(str(data["error"]))

    return data


# =========================
# OPEN INTEREST
# =========================

def get_open_interest():
    data = get_futures_analytics(
        FUTURES_SYMBOL,
        "open-interest",
        3600
    )

    result = data.get("result", {})

    values = result.get("data", {})

    open_interest = values.get("openInterest")

    timestamps = result.get("timestamp", [])

    if not open_interest:
        return None

    if isinstance(open_interest, list):
        current = float(open_interest[-1])

        previous = (
            float(open_interest[-2])
            if len(open_interest) >= 2
            else current
        )

    else:
        current = float(open_interest)
        previous = current

    if previous == 0:
        change = 0
    else:
        change = (
            (current - previous)
            / previous
        ) * 100

    return {
        "current": current,
        "previous": previous,
        "change": change,
        "timestamps": timestamps
    }


# =========================
# FUNDING
# =========================

def get_funding():
    data = get_futures_analytics(
        FUTURES_SYMBOL,
        "funding",
        3600
    )

    result = data.get("result", {})

    values = result.get("data", {})

    rate = values.get("rate")

    timestamps = result.get("timestamp", [])

    if rate is None:
        return None

    if isinstance(rate, list):
        current = float(rate[-1])

        previous = (
            float(rate[-2])
            if len(rate) >= 2
            else current
        )

    else:
        current = float(rate)
        previous = current

    return {
        "current": current,
        "previous": previous,
        "timestamps": timestamps
    }


# =========================
# OI ИНТЕРПРЕТАЦИЯ
# =========================

def interpret_oi(oi):
    if oi is None:
        return "⚪ НЕТ ДАННЫХ"

    change = oi["change"]

    if change > 2:
        return "🟢 РАСТЁТ"

    if change < -2:
        return "🔴 СНИЖАЕТСЯ"

    return "⚪ СТАБИЛЬНЫЙ"


# =========================
# FUNDING ИНТЕРПРЕТАЦИЯ
# =========================

def interpret_funding(funding):
    if funding is None:
        return "⚪ НЕТ ДАННЫХ"

    rate = funding["current"]

    rate_percent = rate * 100

    if rate_percent > 0.05:
        return "🟠 ВЫСОКИЙ POSITIVE"

    if rate_percent < -0.05:
        return "🔵 NEGATIVE"

    return "⚪ НЕЙТРАЛЬНЫЙ"


# =========================
# ОСНОВНОЙ АНАЛИЗ
# =========================

def market_analysis():
    candles_1h = convert_candles(
        get_kraken_candles(60)
    )

    candles_4h = convert_candles(
        get_kraken_candles(240)
    )

    candles_30m = convert_candles(
        get_kraken_candles(30)
    )

    price = candles_1h[-1]["close"]

    structure_4h = detect_4h_structure(
        candles_4h
    )

    a = setup_a(candles_1h)

    b = setup_b(candles_1h)

    c = setup_c(candles_1h)

    setup_exists = (
        a["signal"] or
        b["signal"] or
        c["signal"]
    )

    confirmation_30m = analyze_30m(
        candles_30m,
        setup_exists
    )

    volume_ratio = get_volume_ratio(
        candles_1h
    )

    try:
        oi = get_open_interest()
        oi_status = interpret_oi(oi)
        oi_error = None

    except Exception as error:
        oi = None
        oi_status = "⚠️ ОШИБКА"
        oi_error = str(error)

    try:
        funding = get_funding()
        funding_status = interpret_funding(funding)
        funding_error = None

    except Exception as error:
        funding = None
        funding_status = "⚠️ ОШИБКА"
        funding_error = str(error)

    if a["signal"]:
        setup_name = "🟢 A — ПОДЖАТИЕ → ПРОБОЙ"

    elif b["signal"]:
        setup_name = "🟢 B — ПРОБОЙ → РЕТЕСТ → ПРОДОЛЖЕНИЕ"

    elif c["signal"]:
        setup_name = "🟢 C — СНЯТИЕ ЛИКВИДНОСТИ → РАЗВОРОТ"

    else:
        setup_name = "⚪ НЕТ КАЧЕСТВЕННОГО SETUP"

    text = (
        "📊 INVEST ZONE\n"
        "\n"
        f"BTC: {price:,.2f} USD\n"
        "\n"
        "Источник свечей: KRAKEN\n"
        "1H / 4H / 30M: РЕАЛЬНЫЕ OHLCV\n"
        "\n"
        f"4H STRUCTURE: {structure_4h}\n"
        "\n"
        "━━━━━━━━━━━━━━\n"
        "SETUP A\n"
        "━━━━━━━━━━━━━━\n"
        f"Статус: {'🟢 YES' if a['signal'] else '⚪ NO'}\n"
        f"Resistance: {a['resistance']:,.2f}\n"
        f"Distance: {a['distance']:.2f}%\n"
        f"Higher Lows: {a['higher_lows']}/9\n"
        f"Compression: {'YES' if a['compression'] else 'NO'}\n"
        f"Approach: {'YES' if a['approach'] else 'NO'}\n"
        f"Volume: {a['volume_ratio']:.2f}x\n"
        "\n"
        "━━━━━━━━━━━━━━\n"
        "SETUP B\n"
        "━━━━━━━━━━━━━━\n"
        f"Статус: {'🟢 YES' if b['signal'] else '⚪ NO'}\n"
        f"Resistance: {b['resistance']:,.2f}\n"
        f"Breakout: {'YES' if b['breakout'] else 'NO'}\n"
        f"Retest: {'YES' if b['retest'] else 'NO'}\n"
        f"Hold: {'YES' if b['hold'] else 'NO'}\n"
        "\n"
        "━━━━━━━━━━━━━━\n"
        "SETUP C\n"
        "━━━━━━━━━━━━━━\n"
        f"Статус: {'🟢 YES' if c['signal'] else '⚪ NO'}\n"
        f"Liquidity Low: {c['liquidity_low']:,.2f}\n"
        f"Sweep: {'YES' if c['sweep'] else 'NO'}\n"
        f"Reclaim: {'YES' if c['reclaim'] else 'NO'}\n"
        f"Structure Shift: {'YES' if c['structure_shift'] else 'NO'}\n"
        "\n"
        "━━━━━━━━━━━━━━\n"
        "30M CONFIRMATION\n"
        "━━━━━━━━━━━━━━\n"
        f"Structure: {confirmation_30m['structure']}\n"
        f"Volume: {confirmation_30m['volume_ratio']:.2f}x\n"
        f"{confirmation_30m['status']}\n"
        "\n"
        "━━━━━━━━━━━━━━\n"
        "MARKET FILTERS\n"
        "━━━━━━━━━━━━━━\n"
        f"Volume 1H: {volume_ratio:.2f}x\n"
        f"Open Interest: {oi_status}\n"
        f"Funding: {funding_status}\n"
        "\n"
        "━━━━━━━━━━━━━━\n"
        "ИТОГ\n"
        "━━━━━━━━━━━━━━\n"
        f"{setup_name}\n"
        "\n"
        "⚠️ Liquidity / Room to Target / "
        "Structural Stop Loss пока не подключены.\n"
        "⚠️ Входы автоматически не выдаются."
    )

    if oi_error:
        text += (
            "\n\nOI ERROR:\n"
            f"{oi_error[:500]}"
        )

    if funding_error:
        text += (
            "\n\nFUNDING ERROR:\n"
            f"{funding_error[:500]}"
        )

    return text


# =========================
# ЗАПУСК
# =========================

def main():
    try:
        message = market_analysis()
        send_message(message)

    except Exception as error:
        error_text = (
            "🔴 INVEST ZONE ERROR\n\n"
            f"{type(error).__name__}: {error}"
        )

        try:
            send_message(error_text)

        except Exception:
            pass

        raise


if __name__ == "__main__":
    main()
