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
TELEGRAM_URL = (
    "https://api.telegram.org/bot"
    + BOT_TOKEN
)

# Максимальное количество альтов для анализа.
# Kraken может отдавать очень много пар.
MAX_ASSETS = 60

# После каждого актива небольшая пауза.
REQUEST_DELAY = 0.25

# Сколько свечей использовать для анализа.
LOOKBACK_1H = 120
LOOKBACK_30M = 120
LOOKBACK_4H = 100

# Сколько свечей показывать на графике.
CHART_CANDLES = 80


# ============================================================
# HTTP
# ============================================================

session = requests.Session()


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
# PAIRS
# ============================================================

def get_kraken_pairs():
    """
    Получает доступные spot-пары Kraken.

    Оставляем только USD-котировки.
    BTC и стейблкоины исключаем.
    """

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

        # Kraken иногда имеет технические пары.
        altname = info.get("altname", pair_name)

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

        # Нам нужны только USD spot pairs.
        if quote not in ("ZUSD", "USD"):
            continue

        # Никаких dark / index / synthetic инструментов.
        if info.get("status") not in (None, "online"):
            continue

        # Нормализуем base.
        normalized_base = (
            base
            .replace("X", "")
            .replace("Z", "")
            .upper()
        )

        # Исключаем BTC и стейблкоины.
        if normalized_base in excluded:
            continue

        # Стараемся исключить USD-подобные токены.
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

    # Стабильный порядок.
    pairs.sort(
        key=lambda x: x["base"]
    )

    return pairs[:MAX_ASSETS]


# ============================================================
# OHLC
# ============================================================

def get_ohlc(pair, interval):
    """
    interval:
        30 = 30m
        60 = 1H
        240 = 4H
    """

    result = kraken_get(
        "OHLC",
        {
            "pair": pair,
            "interval": interval
        }
    )

    pair_key = next(
        key
        for key in result
        if key != "last"
    )

    candles = []

    for row in result[pair_key]:

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
    """
    Kraken возвращает последнюю незакрытую свечу.

    Для сигналов её не используем.
    """

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


def price_change_percent(old, new):

    if old == 0:
        return 0.0

    return (
        (new - old)
        / old
        * 100
    )


# ============================================================
# 4H BTC CONTEXT
# ============================================================

def context_4h(candles):

    candles = candles[-LOOKBACK_4H:]

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

    if len(candles) < 20:
        return max(
            x["high"]
            for x in candles
        )

    highs = [
        x["high"]
        for x in candles
    ]

    # Не используем последние 3 свечи,
    # чтобы текущая атака уровня
    # не создавала сам уровень.
    return max(
        highs[-30:-3]
    )


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

    price = candles[-1]["close"]

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

    candle = candles[-1]

    close = candle["close"]

    # Нужен реальный close выше уровня.
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

    volume_expansion = (
        candle["volume"]
        >= previous_volume * 1.30
    )

    return volume_expansion


# ============================================================
# BREAKOUT WITHOUT VOLUME
# ============================================================

def check_breakout_price(
    candles,
    resistance
):

    if not candles:
        return False

    return (
        candles[-1]["close"]
        > resistance * 1.002
    )


# ============================================================
# 30M CONFIRMATION
# ============================================================

def check_30m_confirmation(
    candles
):

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


# ============================================================
# 30M BULLISH STRUCTURE
# ============================================================

def check_30m_structure(
    candles
):

    if len(candles) < 20:
        return False

    return check_higher_lows(
        candles[-40:]
        if len(candles) >= 40
        else candles
    )


# ============================================================
# SETUP A
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

    # Ранняя зона наблюдения.
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
# ============================================================

def setup_b(
    candles_1h,
    candles_30m,
    resistance
):

    if len(candles_1h) < 15:
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

    # Ищем недавний breakout.
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
            closes[i] > resistance * 1.002
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

    # После пробоя должна быть коррекция.
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

        recent_high = max(
            highs[
                breakout_index:
                len(highs) - 1
            ]
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

    # Ищем прокол уровня.
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

    # Цена должна вернуться выше уровня.
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

    structure_shift = (
        check_higher_lows(
            candles_1h[-40:]
        )
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

    return (
        target - price
    ) / price * 100


# ============================================================
# STRUCTURAL STOP
# ============================================================

def structural_stop(
    candles
):

    indexes = find_swing_lows(
        candles
    )

    if not indexes:
        return None

    low = candles[
        indexes[-1]
    ]["low"]

    return low


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

    # BTC DOWN сильно снижает качество
    # Long-сетапов.
    if btc_context == "DOWN":
        return None

    setup_type = None
    priority = 0

    # A — приоритет №1.
    if a["confirmed"]:
        setup_type = "A"
        priority = 3

    elif b["confirmed"]:
        setup_type = "B"
        priority = 2

    elif c["confirmed"]:
        setup_type = "C"
        priority = 1

    # Ранняя зона A тоже интересна,
    # но это не подтвержденный сигнал.
    elif a["early_watch"]:
        setup_type = "A — EARLY"
        priority = 0

    else:
        return None

    return {
        "pair": pair,
        "name": name,
        "price": price,
        "resistance": resistance,
        "btc_context": btc_context,
        "setup": setup_type,
        "priority": priority,
        "a": a,
        "b": b,
        "c": c,
        "room": room,
        "stop": stop,
        "candles_1h": candles_1h,
        "candles_30m": candles_30m
    }


# ============================================================
# CHART
# ============================================================

def draw_candles(
    ax,
    candles,
    title
):

    candles = candles[
        -CHART_CANDLES:
    ]

    for index, candle in enumerate(
        candles
    ):

        open_price = candle["open"]
        close_price = candle["close"]
        high = candle["high"]
        low = candle["low"]

        if close_price >= open_price:
            color = "#00ff66"
        else:
            color = "#ff3030"

        # Wick.
        ax.vlines(
            index,
            low,
            high,
            color=color,
            linewidth=1.0
        )

        body_low = min(
            open_price,
            close_price
        )

        body_height = abs(
            close_price 
