import os
import io
import json
import time
import signal
from datetime import datetime, timezone

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

SCAN_INTERVAL = int(
    os.environ.get(
        "SCAN_INTERVAL",
        "600"
    )
)

STATE_FILE = os.environ.get(
    "STATE_FILE",
    "scanner_state.json"
)

STATE_TTL = int(
    os.environ.get(
        "STATE_TTL",
        str(7 * 24 * 60 * 60)
    )
)

SEND_EARLY = os.environ.get(
    "SEND_EARLY",
    "1"
) == "1"

DRY_RUN = os.environ.get(
    "DRY_RUN",
    "0"
) == "1"

LOOKBACK_1H = 120
LOOKBACK_30M = 120
LOOKBACK_4H = 100

CHART_CANDLES = 80

RUNNING = True


# ============================================================
# HTTP
# ============================================================

session = requests.Session()

session.headers.update({
    "User-Agent": "Kraken-Technical-Scanner/2.0"
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

    if DRY_RUN:
        print(
            f"[DRY RUN] Telegram: {method}"
        )
        return {
            "ok": True
        }

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
# STATE
# ============================================================

def load_state():

    if not os.path.exists(
        STATE_FILE
    ):
        return {}

    try:

        with open(
            STATE_FILE,
            "r",
            encoding="utf-8"
        ) as file:

            state = json.load(file)

        if not isinstance(
            state,
            dict
        ):
            return {}

        return state

    except Exception as exc:

        print(
            f"State load error: {exc}"
        )

        return {}


def save_state(state):

    temp_file = (
        f"{STATE_FILE}.tmp"
    )

    with open(
        temp_file,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            state,
            file,
            ensure_ascii=False,
            indent=2
        )

    os.replace(
        temp_file,
        STATE_FILE
    )


def cleanup_state(state):

    now = time.time()

    cleaned = {}

    for key, timestamp in state.items():

        try:
            timestamp = float(timestamp)
        except Exception:
            continue

        if (
            now - timestamp
            <= STATE_TTL
        ):
            cleaned[key] = timestamp

    return cleaned


def make_signal_key(result):

    resistance = result.get(
        "resistance"
    )

    if resistance is None:
        resistance_key = "none"
    else:
        # Небольшое округление предотвращает
        # создание нового ключа из-за float noise.
        resistance_key = f"{resistance:.8g}"

    return "|".join([
        result["pair"],
        result["setup"],
        resistance_key
    ])


def is_new_signal(
    result,
    state
):

    key = make_signal_key(
        result
    )

    return key not in state


def mark_signal_sent(
    result,
    state
):

    key = make_signal_key(
        result
    )

    state[key] = time.time()


# ============================================================
# PAIRS
# ============================================================

def get_kraken_pairs():

    result = kraken_get(
        "AssetPairs"
    )

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

        if normalized_base.endswith(
            "USD"
        ):
            continue

        pairs.append({
            "pair": pair_name,
            "altname": altname,
            "wsname": wsname,
            "base": normalized_base
        })

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
            f"OHLC data not found: {pair}"
        )

    pair_key = pair_keys[0]

    candles = []

    for row in result[pair_key]:

        if len(row) < 7:
            continue

        candles.append({
            "time": float(row[0]),
            "open": float(row[1]),
            "high": float(row[2]),
            "low": float(row[3]),
            "close": float(row[4]),
            "volume": float(row[6])
        })

    return candles


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
# BTC CONTEXT
# ============================================================

def get_btc_pair():

    result = kraken_get(
        "AssetPairs"
    )

    for pair_name, info in result.items():

        altname = (
            info.get(
                "altname",
                ""
            )
            .upper()
        )

        wsname = (
            info.get(
                "wsname",
                ""
            )
            .upper()
        )

        base = (
            info.get(
                "base",
                ""
            )
            .upper()
        )

        quote = (
            info.get(
                "quote",
                ""
            )
            .upper()
        )

        if quote not in (
            "ZUSD",
            "USD"
        ):
            continue

        if (
            "XBT/USD" in wsname
            or altname == "XBTUSD"
            or base == "XXBT"
        ):
            return pair_name

    if "XXBTZUSD" in result:
        return "XXBTZUSD"

    raise RuntimeError(
        "BTC/USD pair not found"
    )


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


def get_btc_context():

    pair = get_btc_pair()

    candles = get_ohlc(
        pair,
        240
    )

    candles = remove_open_candle(
        candles
    )

    return (
        context_4h(candles),
        candles
    )


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


def check_time_near_resistance(
    candles,
    resistance
):

    if len(candles) < 15:
        return False

    if resistance is None:
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

    if candle["close"] <= (
        resistance * 1.002
    ):
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


# ============================================================
# 30M
# ============================================================

def check_30m_confirmation(candles):

    if len(candles) < 10:
        return False

    closes = [
        x["close"]
        for x in candles
    ]

    current = closes[-
