import os
import time
import requests
import statistics

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

TELEGRAM_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"
BINANCE_URL = "https://fapi.binance.com"


# ============================================================
# TELEGRAM
# ============================================================

def send_message(chat_id, text, keyboard=None):
    data = {
        "chat_id": chat_id,
        "text": text
    }

    if keyboard:
        data["reply_markup"] = keyboard

    try:
        requests.post(
            f"{TELEGRAM_URL}/sendMessage",
            json=data,
            timeout=15
        )
    except Exception as e:
        print("Telegram error:", e)


def keyboard():
    return {
        "keyboard": [
            [{"text": "🛒 ЧТО КУПИТЬ?"}]
        ],
        "resize_keyboard": True,
        "is_persistent": True
    }


# ============================================================
# BINANCE PUBLIC MARKET DATA
# ============================================================

def binance_get(endpoint, params=None):
    try:
        response = requests.get(
            f"{BINANCE_URL}{endpoint}",
            params=params,
            timeout=15
        )

        if response.status_code != 200:
            print("Binance HTTP:", response.status_code)
            return None

        return response.json()

    except Exception as e:
        print("Binance error:", e)
        return None


def get_symbols():
    data = binance_get("/fapi/v1/exchangeInfo")

    if not data:
        return []

    symbols = []

    for item in data.get("symbols", []):

        if item.get("status") != "TRADING":
            continue

        if item.get("quoteAsset") != "USDT":
            continue

        if item.get("contractType") != "PERPETUAL":
            continue

        symbol = item.get("symbol")

        if symbol:
            symbols.append(symbol)

    return symbols


def get_klines(symbol, interval, limit=120):
    data = binance_get(
        "/fapi/v1/klines",
        {
            "symbol": symbol,
            "interval": interval,
            "limit": limit
        }
    )

    if not data:
        return []

    candles = []

    for item in data:
        candles.append({
            "open": float(item[1]),
            "high": float(item[2]),
            "low": float(item[3]),
            "close": float(item[4]),
            "volume": float(item[5])
        })

    return candles


def get_open_interest(symbol):
    data = binance_get(
        "/fapi/v1/openInterest",
        {
            "symbol": symbol
        }
    )

    if not data:
        return None

    try:
        return float(data["openInterest"])
    except Exception:
        return None


def get_funding(symbol):
    data = binance_get(
        "/fapi/v1/fundingRate",
        {
            "symbol": symbol,
            "limit": 1
        }
    )

    if not data:
        return None

    try:
        return float(data[0]["fundingRate"])
    except Exception:
        return None


# ============================================================
# BASIC MARKET CALCULATIONS
# ============================================================

def average(values):

    if not values:
        return 0

    return sum(values) / len(values)


def percentage(a, b):

    if b == 0:
        return 0

    return ((a - b) / b) * 100


def atr(candles, period=14):

    if len(candles) < period + 1:
        return 0

    ranges = []

    for i in range(1, len(candles)):

        high = candles[i]["high"]
        low = candles[i]["low"]
        previous_close = candles[i - 1]["close"]

        true_range = max(
            high - low,
            abs(high - previous_close),
            abs(low - previous_close)
        )

        ranges.append(true_range)

    return average(ranges[-period:])


def recent_high(candles, count=20):

    if len(candles) < count:
        count = len(candles)

    return max(
        candle["high"]
        for candle in candles[-count:]
    )


def recent_low(candles, count=20):

    if len(candles) < count:
        count = len(candles)

    return min(
        candle["low"]
        for candle in candles[-count:]
    )


# ============================================================
# BTC CONTEXT
# ============================================================

def btc_context():

    candles = get_klines(
        "BTCUSDT",
        "1h",
        60
    )

    if len(candles) < 30:
        return {
            "state": "UNKNOWN",
            "text": "BTC Context: недостаточно данных"
        }

    close = candles[-1]["close"]

    ma20 = average(
        candle["close"]
        for candle in candles[-20:]
    )

    high = recent_high(candles, 24)
    low = recent_low(candles, 24)

    if close > ma20 and close > low:

        state = "BULLISH"
        text = "BTC Context: 🟢 конструктивный"

    elif close < ma20 and close < high:

        state = "BEARISH"
        text = "BTC Context: 🔴 слабый"

    else:

        state = "NEUTRAL"
        text = "BTC Context: 🟡 нейтральный"

    return {
        "state": state,
        "text": text
    }


# ============================================================
# 4H STRUCTURE
# ============================================================

def structure_4h(candles):

    if len(candles) < 30:
        return "UNKNOWN"

    recent = candles[-20:]

    highs = [
        candle["high"]
        for candle in recent
    ]

    lows = [
        candle["low"]
        for candle in recent
    ]

    first_half_high = max(highs[:10])
    second_half_high = max(highs[10:])

    first_half_low = min(lows[:10])
    second_half_low = min(lows[10:])

    if (
        second_half_high > first_half_high
        and second_half_low >= first_half_low
    ):
        return "UP"

    if (
        second_half_high <= first_half_high
        and second_half_low < first_half_low
    ):
        return "DOWN"

    return "RANGE"


# ============================================================
# SETUP A
# COMPRESSION -> BREAKOUT
# ============================================================

def detect_setup_a(candles):

    if len(candles) < 50:
        return None

    last = candles[-1]

    resistance = recent_high(candles[-25:-2], 23)

    previous = candles[-25:-2]

    lows = [
        candle["low"]
        for candle in previous
    ]

    if len(lows) < 15:
        return None

    early_low = min(lows[:8])
    late_low = min(lows[-8:])

    higher_lows = late_low > early_low

    ranges = []

    for candle in previous[-12:]:
        ranges.append(
            candle["high"] - candle["low"]
        )

    if len(ranges) < 10:
        return None

    early_range = average(ranges[:5])
    late_range = average(ranges[-5:])

    compression = (
        late_range < early_range * 0.85
    )

    near_resistance = (
        last["close"] >= resistance * 0.985
    )

    volume_average = average(
        candle["volume"]
        for candle in candles[-21:-1]
    )

    volume_expansion = (
        last["volume"] > volume_average * 1.4
    )

    breakout = (
        last["close"] > resistance
    )

    if (
        higher_lows
        and compression
        and near_resistance
        and breakout
        and volume_expansion
    ):

        return {
            "type": "A",
            "name": "ПОДЖАТИЕ → ПРОБОЙ",
            "level": resistance,
            "price": last["close"],
            "reason": (
                "Higher Lows + Compression + "
                "пробой сопротивления + расширение объёма"
            )
        }

    return None


# ============================================================
# SETUP B
# BREAKOUT -> RETEST -> CONTINUATION
# ============================================================

def detect_setup_b(candles):

    if len(candles) < 60:
        return None

    resistance = recent_high(
        candles[-40:-8],
        32
    )

    breakout_candle = candles[-8]

    breakout = (
        breakout_candle["close"] > resistance
    )

    if not breakout:
        return None

    retest_zone_low = resistance * 0.985
    retest_zone_high = resistance * 1.015

    retest = False

    for candle in candles[-7:-2]:

        if (
            candle["low"] <= retest_zone_high
            and candle["low"] >= retest_zone_low
        ):
            retest = True
            break

    last = candles[-1]

    hold = (
        last["close"] > resistance
    )

    volume_average = average(
        candle["volume"]
        for candle in candles[-21:-1]
    )

    continuation_volume = (
        last["volume"] > volume_average * 1.1
    )

    if (
        breakout
        and retest
        and hold
        and continuation_volume
    ):

        return {
            "type": "B",
            "name": "ПРОБОЙ → РЕТЕСТ → ПРОДОЛЖЕНИЕ",
            "level": resistance,
            "price": last["close"],
            "reason": (
                "Пробой сопротивления + подтверждённый "
                "ретест + удержание уровня"
            )
        }

    return None


# ============================================================
# SETUP C
# LIQUIDITY SWEEP -> RECLAIM -> STRUCTURE SHIFT
# ============================================================

def detect_setup_c(candles):

    if len(candles) < 50:
        return None

    obvious_low = recent_low(
        candles[-30:-3],
        27
    )

    sweep_candle = candles[-2]
    last = candles[-1]

    swept = (
        sweep_candle["low"] < obvious_low
    )

    reclaim = (
        sweep_candle["close"] > obvious_low
    )

    higher_low = (
        last["low"] > sweep_candle["low"]
    )

    structure_shift = (
        last["close"] > sweep_candle["high"]
    )

    if (
        swept
        and reclaim
        and higher_low
        and structure_shift
    ):

        return {
            "type": "C",
            "name": "СНЯТИЕ ЛИКВИДНОСТИ → РАЗВОРОТ",
            "level": obvious_low,
            "price": last["close"],
            "reason": (
                "Снятие локальной ликвидности + "
                "reclaim + Structure Shift"
            )
        }

    return None


# ============================================================
# RISK / TARGET FILTER
# ============================================================

def calculate_trade_levels(candles, setup):

    price = setup["price"]

    volatility = atr(candles, 14)

    if volatility <= 0:
        return None

    structural_level = setup["level"]

    stop = structural_level - volatility * 0.7

    if stop >= price:
        return None

    risk = price - stop

    target_1 = price + risk * 2
    target_2 = price + risk * 3

    room_percent = (
        (target_1 - price) / price
    ) * 100

    if room_percent < 1.0:
        return None

    return {
        "entry": price,
        "stop": stop,
        "target_1": target_1,
        "target_2": target_2,
        "room": room_percent
    }


# ============================================================
# SCORING
# ============================================================

def score_setup(
    setup,
    candles,
    btc,
    structure,
    open_interest,
    funding
):

    score = 0
    reasons = []

    # Setup itself
    if setup["type"] == "A":
        score += 4
        reasons.append("A-поджатие")

    elif setup["type"] == "B":
        score += 3
        reasons.append("B-ретест")

    elif setup["type"] == "C":
        score += 3
        reasons.append("C-sweep")

    # BTC context
    if btc["state"] == "BULLISH":
        score += 2
        reasons.append("BTC bullish")

    elif btc["state"] == "NEUTRAL":
        score += 1
        reasons.append("BTC neutral")

    # 4H structure
    if structure == "UP":
        score += 2
        reasons.append("4H up")

    elif structure == "RANGE":
        score += 1
        reasons.append("4H range")

    # Volume
    recent_volume = candles[-1]["volume"]

    average_volume = average(
        candle["volume"]
        for candle in candles[-21:-1]
    )

    if average_volume > 0:

        volume_ratio = (
            recent_volume / average_volume
        )

        if volume_ratio >= 1.5:
            score += 2
            reasons.append("volume expansion")

        elif volume_ratio >= 1.15:
            score += 1
            reasons.append("volume")

    # Funding
    if funding is not None:

        if funding < 0.0005:
            score += 1
            reasons.append("funding normal")

        if funding < -0.0001:
            score += 1
            reasons.append("negative funding")

    # Open Interest existence
    if open_interest is not None and open_interest > 0:
        score += 1
        reasons.append("OI available")

    return score, reasons


# ============================================================
# ANALYZE SYMBOL
# ============================================================

def analyze_symbol(symbol, btc):

    candles_1h = get_klines(
        symbol,
        "1h",
        100
    )

    candles_4h = get_klines(
        symbol,
        "4h",
        60
    )

    if (
        len(candles_1h) < 60
        or len(candles_4h) < 30
    ):
        return None

    structure = structure_4h(candles_4h)

    setup = (
        detect_setup_a(candles_1h)
        or detect_setup_b(candles_1h)
        or detect_setup_c(candles_1h)
    )

    if not setup:
        return None

    levels = calculate_trade_levels(
        candles_1h,
        setup
    )

    if not levels:
        return None

    open_interest = get_open_interest(symbol)
    funding = get_funding(symbol)

    score, reasons = score_setup(
        setup,
        candles_1h,
        btc,
        structure,
        open_interest,
        funding
    )

    if score < 7:
        return None

    return {
        "symbol": symbol,
        "setup": setup,
        "levels": levels,
        "score": score,
        "reasons": reasons,
        "structure": structure,
        "funding": funding
    }


# ============================================================
# MARKET SCANNER
# ============================================================

def scan_market():

    btc = btc_context()

    symbols = get_symbols()

    if not symbols:
        return {
            "btc": btc,
            "signals": [],
            "error": "Не удалось получить список инструментов."
        }

    # Чтобы не делать сотни запросов подряд.
    # Сначала берём основные ликвидные пары.
    priority_symbols = [
        "BTCUSDT",
        "ETHUSDT",
        "SOLUSDT",
        "BNBUSDT",
        "XRPUSDT",
        "DOGEUSDT",
        "ADAUSDT",
        "AVAXUSDT",
        "LINKUSDT",
        "SUIUSDT",
        "TONUSDT",
        "LTCUSDT",
        "DOTUSDT",
        "NEARUSDT",
        "APTUSDT"
    ]

    selected = [
        symbol
        for symbol in priority_symbols
        if symbol in symbols
    ]

    signals = []

    for symbol in selected:

        try:

            result = analyze_symbol(
                symbol,
                btc
            )

            if result:
                signals.append(result)

        except Exception as e:

            print(
                f"Ошибка анализа {symbol}: {e}"
            )

        time.sleep(0.2)

    signals.sort(
        key=lambda x: x["score"],
        reverse=True
    )

    return {
        "btc": btc,
        "signals": signals[:5],
        "error": None
    }


# ============================================================
# FORMAT SIGNAL
# ============================================================

def format_price(value):

    if value >= 1000:
        return f"{value:,.2f}"

    if value >= 1:
        return f"{value:.4f}"

    return f"{value:.6f}"


def format_signal(signal):

    setup = signal["setup"]
    levels = signal["levels"]

    funding = signal["funding"]

    if funding is None:
        funding_text = "нет данных"
    else:
        funding_text = f"{funding * 100:.4f}%"

    text = (
        f"🟢 {signal['symbol']}\n\n"
        f"Сетап: {setup['name']}\n"
        f"Score: {signal['score']}/12\n"
        f"4H Structure: {signal['structure']}\n\n"
        f"💰 Цена: {format_price(levels['entry'])}\n"
        f"🛑 Structural SL: {format_price(levels['stop'])}\n"
        f"🎯 TP1: {format_price(levels['target_1'])}\n"
        f"🎯 TP2: {format_price(levels['target_2'])}\n"
        f"📐 Room: {levels['room']:.2f}%\n\n"
        f"Funding: {funding_text}\n\n"
        f"Подтверждения:\n"
    )

    for reason in signal["reasons"]:
        text += f"• {reason}\n"

    text += (
        f"\nЛогика:\n"
        f"{setup['reason']}\n\n"
        f"⚠️ Это структурный сигнал, а не гарантия движения."
    )

    return text


# ============================================================
# TELEGRAM COMMANDS
# ============================================================

def handle_message(chat_id, text):

    if text == "/start":

        send_message(
            chat_id,
            (
                "🤖 INVEST ZONE\n\n"
                "Сканер ищет изменение баланса сил "
                "до основного импульса.\n\n"
                "Приоритет:\n"
                "A — Поджатие → Пробой\n"
                "B — Пробой → Ретест → Продолжение\n"
                "C — Снятие ликвидности → Разворот\n\n"
                "Нажми кнопку ниже."
            ),
            keyboard()
        )

    elif text == "🛒 ЧТО КУПИТЬ?":

        send_message(
            chat_id,
            (
                "🔎 INVEST ZONE\n\n"
                "Сканирую рынок...\n\n"
                "Проверяю:\n"
                "• BTC Context\n"
                "• 4H Structure\n"
                "• 1H Setup\n"
                "• Volume\n"
                "• Open Interest\n"
                "• Funding\n"
                "• Room to Target\n"
                "• Structural Stop Loss\n\n"
                "⏳ Это может занять немного времени."
            )
        )

        result = scan_market()

        if result["error"]:

            send_message(
                chat_id,
                f"❌ Ошибка сканирования:\n{result['error']}"
            )

            return

        btc = result["btc"]
        signals = result["signals"]

        header = (
            "📊 INVEST ZONE\n\n"
            f"{btc['text']}\n\n"
        )

        if not signals:

            send_message(
                chat_id,
                header +
                "❌ Качественного сетапа сейчас нет.\n\n"
                "Это нормально.\n"
                "По методологии INVEST ZONE:\n"
                "нет качественного сетапа = нет сигнала."
            )

            return

        send_message(
            chat_id,
            header +
            f"Найдено сетапов: {len(signals)}\n\n"
            "Приоритет отдаётся структуре ДО импульса."
        )

        for signal in signals:

            send_message(
                chat_id,
                format_signal(signal)
            )

    elif text == "/help":

        send_message(
            chat_id,
            (
                "ℹ️ INVEST ZONE\n\n"
                "🛒 ЧТО КУПИТЬ? — сканирование рынка.\n\n"
                "A — Поджатие → Пробой\n"
                "B — Пробой → Ретест → Продолжение\n"
                "C — Снятие ликвидности → Разворот\n\n"
                "Бот не выдаёт сигнал, если "
                "сетап не проходит фильтры."
            )
        )

    else:

        send_message(
            chat_id,
            "Используй кнопку 🛒 ЧТО КУПИТЬ?"
        )


# ============================================================
# MAIN LOOP
# ============================================================

def main():

    offset = 0

    send_message(
        CHAT_ID,
        (
            "🟢 INVEST ZONE запущен.\n\n"
            "Рыночный сканер готов.\n"
            "Нажми 🛒 ЧТО КУПИТЬ?"
        ),
        keyboard()
    )

    while True:

        try:

      
