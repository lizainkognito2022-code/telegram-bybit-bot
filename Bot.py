import os
import io
import time
import requests

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle


# ============================================================
# CONFIG
# ============================================================

BOT_TOKEN = os.environ["BOT_TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]

KRAKEN_URL = "https://api.kraken.com/0/public"
TELEGRAM_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

MAX_ASSETS = 60
REQUEST_DELAY = 0.25

LOOKBACK_1H = 120
LOOKBACK_30M = 120
LOOKBACK_4H = 100

CHART_CANDLES = 80

# Не отправлять ранние/слабые сигналы слишком часто
SEND_EARLY = True

# Минимальное пространство до следующего сопротивления.
# Если None — не фильтровать.
MIN_ROOM_PERCENT = None


# ============================================================
# HTTP
# ============================================================

session = requests.Session()

session.headers.update({
    "User-Agent": "Kraken-Technical-Scanner/1.0"
})


def kraken_get(endpoint, params=None):

    url = f"{KRAKEN_URL}/{endpoint}"

    response = session.get(
        url,
        params=params or {},
        timeout=30
    )

    response.raise_for_status()

    data = response.json()

    if data.get("error"):
        raise RuntimeError(
            f"Kraken error: {data['error']}"
        )

    return data["result"]


# ============================================================
# TELEGRAM
# ============================================================

def telegram_request(
    method,
    data=None,
    files=None
):

    url = f"{TELEGRAM_URL}/{method}"

    response = session.post(
        url,
        data=data or {},
        files=files,
        timeout=30
    )

    response.raise_for_status()

    result = response.json()

    if not result.get("ok"):
        raise RuntimeError(
            f"Telegram error: {result}"
        )

    return result


def send_message(text):

    return telegram_request(
        "sendMessage",
        data={
            "chat_id": CHAT_ID,
            "text": text
        }
    )


def send_photo(
    image_bytes,
    caption
):

    files = {
        "photo": (
            "chart.png",
            image_bytes,
            "image/png"
        )
    }

    return telegram_request(
        "sendPhoto",
        data={
            "chat_id": CHAT_ID,
            "caption": caption
        },
        files=files
    )


# ============================================================
# PAIRS
# ============================================================

def get_kraken_pairs():

    result = kraken_get("AssetPairs")

    pairs = []

    excluded = {
        "BTC",
        "XBT",
        "USD",
        "USDT",
        "USDC",
        "DAI",
        "EUR",
        "GBP",
        "CAD",
        "AUD",
        "CHF",
        "JPY",
    }

    for pair_name, info in result.items():

        altname = info.get(
            "altname",
            pair_name
        )

        base = (
            info.get("base")
            or ""
        )

        quote = (
            info.get("quote")
            or ""
        )

        wsname = (
            info.get("wsname")
            or ""
        )

        if quote not in (
            "ZUSD",
            "USD"
        ):
            continue

        if info.get("status") not in (
            None,
            "online"
        ):
            continue

        normalized_base = (
            base
            .replace("X", "")
            .replace("Z", "")
            .upper()
        )

        if normalized_base in excluded:
            continue

        if normalized_base.endswith("USD"):
            continue

        pairs.append(
            {
                "pair": pair_name,
                "altname": altname,
                "wsname": wsname,
                "base": normalized_base,
            }
        )

    pairs.sort(
        key=lambda x: x["base"]
    )

    return pairs[:MAX_ASSETS]


# ============================================================
# OHLC
# ============================================================

def get_ohlc(
    pair,
    interval
):

    result = kraken_get(
        "OHLC",
        {
            "pair": pair,
            "interval": interval
        }
    )

    pair_keys = [
        key
        for key in result
        if key != "last"
    ]

    if not pair_keys:
        raise RuntimeError(
            f"OHLC data not found for {pair}"
        )

    pair_key = pair_keys[0]

    candles = []

    for row in result[pair_key]:

        if len(row) < 7:
            continue

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


# ============================================================
# CLOSED CANDLES
# ============================================================

def remove_open_candle(candles):

    if len(candles) <= 1:
        return candles

    return candles[:-1]


# ============================================================
# BASIC
# ============================================================

def average(values):

    if not values:
        return 0.0

    return sum(values) / len(values)


def price_change_percent(
    old,
    new
):

    if old == 0:
        return 0.0

    return (
        (new - old)
        / old
        * 100
    )


# ============================================================
# BTC 4H CONTEXT
# ============================================================

def context_4h(candles):

    candles = candles[
        -LOOKBACK_4H:
    ]

    if len(candles) < 20:
        return "NEUTRAL"

    closes = [
        x["close"]
        for x in candles
    ]

    old = average(
        closes[-20:-10]
    )

    new = average(
        closes[-10:]
    )

    change = price_change_percent(
        old,
        new
    )

    if change >= 1.0:
        return "UP"

    if change <= -1.0:
        return "DOWN"

    return "RANGE"


# ============================================================
# STRUCTURE
# ============================================================

def find_swing_lows(candles):

    if len(candles) < 5:
        return []

    lows = [
        x["low"]
        for x in candles
    ]

    indexes = []

    for i in range(
        2,
        len(lows) - 2
    ):

        if (
            lows[i] < lows[i - 1]
            and lows[i] < lows[i - 2]
            and lows[i] < lows[i + 1]
            and lows[i] < lows[i + 2]
        ):
            indexes.append(i)

    return indexes


def find_swing_highs(candles):

    if len(candles) < 5:
        return []

    highs = [
        x["high"]
        for x in candles
    ]

    indexes = []

    for i in range(
        2,
        len(highs) - 2
    ):

        if (
            highs[i] > highs[i - 1]
            and highs[i] > highs[i - 2]
            and highs[i] > highs[i + 1]
            and highs[i] > highs[i + 2]
        ):
            indexes.append(i)

    return indexes


def check_higher_lows(candles):

    indexes = find_swing_lows(
        candles
    )

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


# ============================================================
# RESISTANCE
# ============================================================

def find_resistance(candles):

    if not candles:
        return None

    if len(candles) < 20:
        return max(
            x["high"]
            for x in candles
        )

    highs = [
        x["high"]
        for x in candles
    ]

    window = highs[-30:-3]

    if not window:
        return max(highs)

    return max(window)


# ============================================================
# COMPRESSION
# ============================================================

def check_compression(candles):

    if len(candles) < 30:
        return False

    ranges = [
        x["high"] - x["low"]
        for x in candles
    ]

    old_range = average(
        ranges[-30:-15]
    )

    new_range = average(
        ranges[-15:]
    )

    if old_range <= 0:
        return False

    return (
        new_range
        <= old_range * 0.85
    )


# ============================================================
# APPROACH
# ============================================================

def check_approach(
    candles,
    resistance
):

    if not candles:
        return False

    if resistance is None:
        return False

    price = candles[-1]["close"]

    if price <= 0:
        return False

    distance = (
        resistance - price
    ) / price * 100

    return (
        0 <= distance <= 2.0
    )


# ============================================================
# TIME NEAR RESISTANCE
# ============================================================

def check_time_near_resistance(
    candles,
    resistance
):

    if len(candles) < 15:
        return False

    if resistance is None:
        return False

    if resistance <= 0:
        return False

    recent = candles[-15:]

    near_count = 0

    for candle in recent:

        distance = abs(
            resistance
            - candle["close"]
        ) / resistance

        if distance <= 0.015:
            near_count += 1

    return near_count >= 5


# ============================================================
# BREAKOUT
# ============================================================

def check_breakout(
    candles,
    resistance
):

    if len(candles) < 25:
        return False

    if resistance is None:
        return False

    candle = candles[-1]

    close = candle["close"]

    if close <= resistance * 1.002:
        return False

    volumes = [
        x["volume"]
        for x in candles
    ]

    previous_volume = average(
        volumes[-20:-1]
    )

    if previous_volume <= 0:
        return False

    return (
        candle["volume"]
        >= previous_volume * 1.30
    )


def check_breakout_price(
    candles,
    resistance
):

    if not candles:
        return False

    if resistance is None:
        return False

    return (
        candles[-1]["close"]
        > resistance * 1.002
    )


# ============================================================
# 30M CONFIRMATION
# ============================================================

def check_30m_confirmation(candles):

    if len(candles) < 10:
        return False

    closes = [
        x["close"]
        for x in candles
    ]

    current = closes[-1]

    previous_high = max(
        closes[-6:-1]
    )

    return (
        current >= previous_high
    )


def check_30m_structure(candles):

    if len(candles) < 20:
        return False

    if len(candles) >= 40:
        sample = candles[-40:]
    else:
        sample = candles

    return check_higher_lows(
        sample
    )


# ============================================================
# SETUP A
# ПОДЖАТИЕ → ПРОБОЙ
# ============================================================

def setup_a(
    candles_1h,
    candles_30m,
    resistance
):

    higher_lows = check_higher_lows(
        candles_1h
    )

    compression = check_compression(
        candles_1h
    )

    approach = check_approach(
        candles_1h,
        resistance
    )

    time_near = check_time_near_resistance(
        candles_1h,
        resistance
    )

    price = candles_1h[-1]["close"]

    early_watch = (
        higher_lows
        and compression
        and approach
        and time_near
        and price <= resistance
    )

    breakout = check_breakout(
        candles_1h,
        resistance
    )

    confirmation_30m = (
        check_30m_confirmation(
            candles_30m
        )
        and check_30m_structure(
            candles_30m
        )
    )

    confirmed = (
        breakout
        and confirmation_30m
    )

    return {
        "early_watch": early_watch,
        "breakout": breakout,
        "confirmation_30m": confirmation_30m,
        "confirmed": confirmed,
        "higher_lows": higher_lows,
        "compression": compression,
        "approach": approach,
        "time_near": time_near
    }


# ============================================================
# SETUP B
# ПРОБОЙ → РЕТЕСТ → ПРОДОЛЖЕНИЕ
# ============================================================

def setup_b(
    candles_1h,
    candles_30m,
    resistance
):

    if (
        len(candles_1h) < 15
        or resistance is None
    ):
        return {
            "breakout": False,
            "retest": False,
            "hold": False,
            "continuation": False,
            "confirmed": False
        }

    closes = [
        x["close"]
        for x in candles_1h
    ]

    highs = [
        x["high"]
        for x in candles_1h
    ]

    breakout_index = None

    start = max(
        5,
        len(candles_1h) - 15
    )

    for i in range(
        start,
        len(candles_1h) - 2
    ):

        if (
            closes[i]
            > resistance * 1.002
        ):
            breakout_index = i

    if breakout_index is None:
        return {
            "breakout": False,
            "retest": False,
            "hold": False,
            "continuation": False,
            "confirmed": False
        }

    after = candles_1h[
        breakout_index + 1:
    ]

    if len(after) < 2:
        return {
            "breakout": True,
            "retest": False,
            "hold": False,
            "continuation": False,
            "confirmed": False
        }

    retest = any(
        candle["low"]
        <= resistance * 1.005
        for candle in after
    )

    hold = False

    if retest:

        latest = candles_1h[-1]

        hold = (
            latest["close"]
            > resistance
        )

    continuation = False

    if hold:

        post_breakout_highs = highs[
            breakout_index:-1
        ]

        if post_breakout_highs:

            recent_high = max(
                post_breakout_highs
            )

            continuation = (
                candles_1h[-1]["close"]
                >= recent_high * 0.995
            )

    confirmation_30m = (
        check_30m_confirmation(
            candles_30m
        )
    )

    confirmed = (
        retest
        and hold
        and continuation
        and confirmation_30m
    )

    return {
        "breakout": True,
        "retest": retest,
        "hold": hold,
        "continuation": continuation,
        "confirmed": confirmed
    }


# ============================================================
# SETUP C
# СНЯТИЕ ЛИКВИДНОСТИ → РАЗВОРОТ
# ============================================================

def setup_c(
    candles_1h,
    candles_30m
):

    if len(candles_1h) < 30:
        return {
            "obvious_low": False,
            "sweep": False,
            "reclaim": False,
            "structure_shift": False,
            "confirmed": False
        }

    swing_indexes = find_swing_lows(
        candles_1h[:-5]
    )

    if not swing_indexes:
        return {
            "obvious_low": False,
            "sweep": False,
            "reclaim": False,
            "structure_shift": False,
            "confirmed": False
        }

    low_index = swing_indexes[-1]

    obvious_low = candles_1h[
        low_index
    ]["low"]

    recent = candles_1h[
        low_index + 1:
    ]

    if len(recent) < 3:
        return {
            "obvious_low": True,
            "sweep": False,
            "reclaim": False,
            "structure_shift": False,
            "confirmed": False
        }

    sweep_index = None

    for i, candle in enumerate(
        recent
    ):

        if (
            candle["low"]
            < obvious_low
        ):
            sweep_index = i

    if sweep_index is None:
        return {
            "obvious_low": True,
            "sweep": False,
            "reclaim": False,
            "structure_shift": False,
            "confirmed": False
        }

    after_sweep = recent[
        sweep_index:
    ]

    reclaim = any(
        candle["close"]
        > obvious_low
        for candle in after_sweep
    )

    if not reclaim:
        return {
            "obvious_low": True,
            "sweep": True,
            "reclaim": False,
            "structure_shift": False,
            "confirmed": False
        }

    structure_shift = check_higher_lows(
        candles_1h[-40:]
    )

    confirmation_30m = (
        check_30m_confirmation(
            candles_30m
        )
    )

    confirmed = (
        reclaim
        and structure_shift
        and confirmation_30m
    )

    return {
        "obvious_low": True,
        "sweep": True,
        "reclaim": reclaim,
        "structure_shift": structure_shift,
        "confirmed": confirmed
    }


# ============================================================
# ROOM TO TARGET
# ============================================================

def find_next_resistance(
    candles,
    current_price
):

    if not candles:
        return None

    if current_price <= 0:
        return None

    highs = [
        x["high"]
        for x in candles
    ]

    future_levels = [
        high
        for high in highs[:-10]
        if high > current_price
    ]

    if not future_levels:
        return None

    return min(
        future_levels
    )


def room_to_target(
    candles,
    price
):

    target = find_next_resistance(
        candles,
        price
    )

    if target is None:
        return None

    if price <= 0:
        return None

    return (
        target - price
    ) / price * 100


# ============================================================
# STRUCTURAL STOP
# ============================================================

def structural_stop(candles):

    indexes = find_swing_lows(
        candles
    )

    if not indexes:
        return None

    return candles[
        indexes[-1]
    ]["low"]


# ============================================================
# FULL ANALYSIS
# ============================================================

def analyze_asset(
    pair,
    name,
    btc_context,
    candles_1h,
    candles_30m
):

    candles_1h = remove_open_candle(
        candles_1h
    )

    candles_30m = remove_open_candle(
        candles_30m
    )

    if len(candles_1h) < 40:
        return None

    if len(candles_30m) < 20:
        return None

    price = candles_1h[-1]["close"]

    resistance = find_resistance(
        candles_1h
    )

    if resistance is None:
        return None

    a = setup_a(
        candles_1h,
        candles_30m,
        resistance
    )

    b = setup_b(
        candles_1h,
        candles_30m,
        resistance
    )

    c = setup_c(
        candles_1h,
        candles_30m
    )

    room = room_to_target(
        candles_1h,
        price
    )

    stop = structural_stop(
        candles_1h
    )

    # BTC DOWN = no long setups
    if btc_context == "DOWN":
        return None

    setup_type = None
    priority = 0

    if a["confirmed"]:

        setup_type = "A"
        priority = 3

    elif b["confirmed"]:

        setup_type = "B"
        priority = 2

    elif c["confirmed"]:

        setup_type = "C"
        priority = 1

    elif (
        a["early_watch"]
        and SEND_EARLY
    ):

        setup_type = "A — EARLY"
        priority = 0

    else:
        return None

    if (
        MIN_ROOM_PERCENT is not None
        and room is not None
        and room < MIN_ROOM_PERCENT
    ):
        return None

   
