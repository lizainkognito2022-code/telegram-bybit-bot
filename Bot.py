import os
import json
import time
import signal
import logging
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

MAX_ASSETS = int(os.environ.get("MAX_ASSETS", "60"))
REQUEST_DELAY = float(os.environ.get("REQUEST_DELAY", "0.25"))
SCAN_INTERVAL = int(os.environ.get("SCAN_INTERVAL", "600"))

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


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

log = logging.getLogger("kraken_scanner")


# ============================================================
# GLOBALS
# ============================================================

STOP_REQUESTED = False

SESSION = requests.Session()

SESSION.headers.update({
    "User-Agent": "KrakenTelegramScanner/1.0"
})


# ============================================================
# SIGNAL HANDLERS
# ============================================================

def handle_stop(signum, frame):
    global STOP_REQUESTED
    STOP_REQUESTED = True
    log.info("Stop signal received: %s", signum)


signal.signal(signal.SIGINT, handle_stop)
signal.signal(signal.SIGTERM, handle_stop)


# ============================================================
# HELPERS
# ============================================================

def now_ts():
    return int(
        datetime.now(timezone.utc).timestamp()
    )


def safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def average(values):
    if not values:
        return 0.0

    return sum(values) / len(values)


def fmt_price(value):
    value = safe_float(value)

    if value >= 1000:
        return f"{value:,.2f}"

    if value >= 1:
        return f"{value:,.4f}"

    if value >= 0.01:
        return f"{value:,.6f}"

    return f"{value:.8f}"


# ============================================================
# STATE
# ============================================================

def load_state():
    if not os.path.exists(STATE_FILE):
        return {}

    try:
        with open(
            STATE_FILE,
            "r",
            encoding="utf-8"
        ) as file:
            data = json.load(file)

        if isinstance(data, dict):
            return data

    except Exception as error:
        log.warning(
            "Could not load state: %s",
            error
        )

    return {}


def save_state(state):
    tmp_file = STATE_FILE + ".tmp"

    try:
        with open(
            tmp_file,
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
            tmp_file,
            STATE_FILE
        )

    except Exception as error:
        log.error(
            "Could not save state: %s",
            error
        )


def cleanup_state(state):
    current = now_ts()
    cleaned = {}

    for key, value in state.items():
        if not isinstance(value, dict):
            continue

        timestamp = int(
            value.get("timestamp", 0)
        )

        if current - timestamp <= STATE_TTL:
            cleaned[key] = value

    return cleaned


# ============================================================
# TELEGRAM
# ============================================================

def telegram_request(
    method,
    data=None,
    files=None
):
    if DRY_RUN:
        log.info(
            "DRY_RUN Telegram method=%s",
            method
        )
        return True

    url = f"{TELEGRAM_URL}/{method}"

    try:
        response = SESSION.post(
            url,
            data=data,
            files=files,
            timeout=30
        )

        response.raise_for_status()

        payload = response.json()

        if not payload.get("ok"):
            log.error(
                "Telegram API error: %s",
                payload
            )
            return False

        return True

    except Exception as error:
        log.error(
            "Telegram request failed: %s",
            error
        )
        return False


def send_message(text):
    return telegram_request(
        "sendMessage",
        data={
            "chat_id": CHAT_ID,
            "text": text,
            "disable_web_page_preview": True
        }
    )


def send_photo(
    image_path,
    caption=""
):
    if DRY_RUN:
        log.info(
            "DRY_RUN photo: %s",
            image_path
        )
        return True

    try:
        with open(
            image_path,
            "rb"
        ) as photo:
            return telegram_request(
                "sendPhoto",
                data={
                    "chat_id": CHAT_ID,
                    "caption": caption
                },
                files={
                    "photo": photo
                }
            )

    except Exception as error:
        log.error(
            "Could not send photo: %s",
            error
        )
        return False


# ============================================================
# KRAKEN API
# ============================================================

def kraken_public(
    endpoint,
    params=None
):
    url = f"{KRAKEN_URL}/{endpoint}"

    try:
        response = SESSION.get(
            url,
            params=params or {},
            timeout=30
        )

        response.raise_for_status()

        payload = response.json()

        if payload.get("error"):
            log.warning(
                "Kraken API error: %s",
                payload["error"]
            )
            return None

        return payload.get("result")

    except Exception as error:
        log.warning(
            "Kraken request failed: %s",
            error
        )
        return None


# ============================================================
# KRAKEN PAIRS
# ============================================================

def get_usd_pairs():
    result = kraken_public("AssetPairs")

    if not result:
        return []

    pairs = []

    for pair_name, info in result.items():
        if not isinstance(info, dict):
            continue

        wsname = str(
            info.get("wsname", "")
        )

        quote = str(
            info.get("quote", "")
        )

        status = str(
            info.get("status", "")
        )

        if status not in ("", "online"):
            continue

        if (
            "/USD" in wsname
            or quote in ("USD", "ZUSD")
        ):
            pairs.append(pair_name)

    pairs = sorted(set(pairs))

    return pairs[:MAX_ASSETS]


# ============================================================
# OHLC
# ============================================================

def parse_ohlc(rows):
    candles = []

    if not rows:
        return candles

    for row in rows:
        if len(row) < 7:
            continue

        candle = {
            "time": int(safe_float(row[0])),
            "open": safe_float(row[1]),
            "high": safe_float(row[2]),
            "low": safe_float(row[3]),
            "close": safe_float(row[4]),
            "vwap": safe_float(row[5]),
            "volume": safe_float(row[6]),
            "count": (
                int(safe_float(row[7]))
                if len(row) > 7
                else 0
            )
        }

        candles.append(candle)

    return candles


def get_ohlc(
    pair,
    interval,
    limit
):
    result = kraken_public(
        "OHLC",
        {
            "pair": pair,
            "interval": interval
        }
    )

    if not result:
        return []

    rows = None

    for key, value in result.items():
        if key == "last":
            continue

        rows = value
        break

    candles = parse_ohlc(rows or [])

    if limit:
        return candles[-limit:]

    return candles


# ============================================================
# CANDLE HELPERS
# ============================================================

def candle_range(candle):
    return (
        candle["high"]
        - candle["low"]
    )


def candle_body(candle):
    return abs(
        candle["close"]
        - candle["open"]
    )


# ============================================================
# SWING HIGHS
# ============================================================

def find_swing_highs(
    candles,
    left=2,
    right=2
):
    result = []

    required = left + right + 1

    if len(candles) < required:
        return result

    for index in range(
        left,
        len(candles) - right
    ):
        high = candles[index]["high"]
        valid = True

        for j in range(index - left, index):
            if candles[j]["high"] >= high:
                valid = False
                break

        if not valid:
            continue

        for j in range(
            index + 1,
            index + right + 1
        ):
            if candles[j]["high"] >= high:
                valid = False
                break

        if valid:
            result.append(
                (index, high)
            )

    return result


# ============================================================
# SWING LOWS
# ============================================================

def find_swing_lows(
    candles,
    left=2,
    right=2
):
    result = []

    required = left + right + 1

    if len(candles) < required:
        return result

    for index in range(
        left,
        len(candles) - right
    ):
        low = candles[index]["low"]
        valid = True

        for j in range(index - left, index):
            if candles[j]["low"] <= low:
                valid = False
                break

        if not valid:
            continue

        for j in range(
            index + 1,
            index + right + 1
        ):
            if candles[j]["low"] <= low:
                valid = False
                break

        if valid:
            result.append(
                (index, low)
            )

    return result


# ============================================================
# STRUCTURE
# ============================================================

def check_higher_lows(candles):
    lows = find_swing_lows(candles)

    if len(lows) < 2:
        return False

    previous_low = lows[-2][1]
    current_low = lows[-1][1]

    return current_low > previous_low


def check_higher_highs(candles):
    highs = find_swing_highs(candles)

    if len(highs) < 2:
        return False

    previous_high = highs[-2][1]
    current_high = highs[-1][1]

    return current_high > previous_high


# ============================================================
# RESISTANCE
# ============================================================

def find_resistance(candles):
    if len(candles) < 10:
        return None

    highs = find_swing_highs(candles)

    if highs:
        return highs[-1][1]

    recent = candles[-20:]

    return max(
        candle["high"]
        for candle in recent
    )


def price_near_resistance(
    price,
    resistance,
    tolerance=0.015
):
    if resistance is None:
        return False

    if resistance <= 0:
        return False

    distance = (
        resistance - price
    ) / resistance

    return (
        -0.005
        <= distance
        <= tolerance
    )


# ============================================================
# COMPRESSION
# ============================================================

def check_compression(candles):
    if len(candles) < 20:
        return False

    recent = [
        candle_range(c)
        for c in candles[-10:]
    ]

    previous = [
        candle_range(c)
        for c in candles[-20:-10]
    ]

    recent_average = average(recent)
    previous_average = average(previous)

    if previous_average <= 0:
        return False

    return (
        recent_average
        <= previous_average * 0.85
    )


# ============================================================
# VOLUME
# ============================================================

def volume_expansion(candles):
    if len(candles) < 20:
        return False

    current_volume = candles[-1]["volume"]

    previous_volumes = [
        candle["volume"]
        for candle in candles[-11:-1]
    ]

    average_volume = average(previous_volumes)

    if average_volume <= 0:
        return False

    return (
        current_volume
        >= average_volume * 1.5
    )


# ============================================================
# BREAKOUT
# ============================================================

def check_breakout(
    candles,
    resistance
):
    if resistance is None:
        return False

    if len(candles) < 5:
        return False

    current = candles[-1]

    return (
        current["close"] > resistance
        and current["high"] > resistance
    )


# ============================================================
# 30M CONFIRMATION
# ============================================================

def check_30m_confirmation(candles):
    if len(candles) < 10:
        return False

    closes = [
        candle["close"]
        for candle in candles
    ]

    current = closes[-1]
    previous_high = max(closes[-6:-1])

    return current >= previous_high


def check_30m_structure(candles):
    if len(candles) < 20:
        return False

    return check_higher_lows(
        candles[-40:]
    )


# ============================================================
# BTC CONTEXT
# ============================================================

def get_btc_context():
    candles = get_ohlc(
        "XBTUSD",
        240,
        LOOKBACK_4H
    )

    if not candles:
        candles = get_ohlc(
            "XXBTZUSD",
            240,
            LOOKBACK_4H
        )

    if len(candles) < 30:
        return "UNKNOWN"

    closes = [
        candle["close"]
        for candle in candles
    ]

    short_average = average(
        closes[-10:]
    )

    long_average = average(
        closes[-30:]
    )

    if short_average > long_average:
        return "UP"

    if short_average < long_average:
        return "DOWN"

    return "NEUTRAL"


# ============================================================
# SETUP A
# ============================================================

def detect_setup_a(
    candles_1h,
    candles_30m
):
    if len(candles_1h) < 30:
        return None

    resistance = find_resistance(candles_1h)

    if resistance is None:
        return None

    price = candles_1h[-1]["close"]

    higher_lows = check_higher_lows(
        candles_1h[-60:]
    )

    compression = check_compression(
        candles_1h
    )

    near_resistance = price_near_resistance(
        price,
        resistance
    )

    breakout = check_breakout(
        candles_1h,
        resistance
    )

    volume_ok = volume_expansion(
        candles_1h
    )

    confirmation_30m = (
        check_30m_confirmation(candles_30m)
        or check_30m_structure(candles_30m)
    )

    if (
        breakout
        and volume_ok
        and confirmation_30m
    ):
        return {
            "setup": "A",
            "type": "CONFIRMED",
            "resistance": resistance,
            "price": price,
            "reason": (
                "Breakout + volume + "
                "30M confirmation"
            )
        }

    if (
        SEND_EARLY
        and higher_lows
        and compression
        and near_resistance
    ):
        return {
            "setup": "A",
            "type": "EARLY",
            "resistance": resistance,
            "price": price,
            "reason": (
                "Higher lows + compression + "
                "resistance approach"
            )
        }

    return None


# ============================================================
# SETUP B
# ============================================================

def detect_setup_b(
    candles_1h,
    candles_30m
):
    if len(candles_1h) < 40:
        return None

    resistance = find_resistance(
        candles_1h[:-3]
    )

    if resistance is None:
        return None

    recent = candles_1h[-15:]
    breakout_index = None

    for index, candle in enumerate(recent):
        if candle["close"] > resistance:
            breakout_index = index
            break

    if breakout_index is None:
        return None

    after_breakout = recent[
        breakout_index + 1:
    ]

    if not after_breakout:
        return None

    retest = False
    hold = False

    for candle in after_breakout:
        if candle["low"] <= resistance * 1.005:
            retest = True

        if candle["close"] > resistance:
            hold = True

    if not retest or not hold:
        return None

    current = candles_1h[-1]

    continuation = (
        current["close"] > resistance
    )

    confirmation_30m = (
        check_30m_confirmation(candles_30m)
        or check_30m_structure(candles_30m)
    )

    if (
        continuation
        and confirmation_30m
    ):
        return {
            "setup": "B",
            "type": "CONFIRMED",
            "resistance": resistance,
            "price": current["close"],
            "reason": (
                "Breakout + retest + hold + "
                "continuation"
            )
        }

    if SEND_EARLY and retest and hold:
        return {
            "setup": "B",
            "type": "EARLY",
            "resistance": resistance,
            "price": current["close"],
            "reason": (
                "Breakout + successful retest"
            )
        }

    return None


# ============================================================
# SETUP C
# ============================================================

def detect_setup_c(
    candles_1h,
    candles_30m
):
    if len(candles_1h) < 40:
        return None

    swing_lows = find_swing_lows(
        candles_1h[:-5]
    )

    if not swing_lows:
        return None

    swing_low = swing_lows[-1][1]

    recent = candles_1h[-10:]

    swept = False
    reclaim = False

    for candle in recent:
        if candle["low"] < swing_low:
            swept = True

        if swept and candle["close"] > swing_low:
            reclaim = True

    if not swept or not reclaim:
        return None

    structure_shift = check_higher_lows(
        candles_1h[-30:]
    )

    confirmation_30m = (
        check_30m_confirmation(candles_30m)
        or check_30m_structure(candles_30m)
    )

    current = candles_1h[-1]

    resistance = find_resistance(
        candles_1h
    )

    if (
        structure_shift
        and confirmation_30m
    ):
        return {
            "setup": "C",
            "type": "CONFIRMED",
            "resistance": resistance,
            "price": current["close"],
            "swing_low": swing_low,
            "reason": (
                "Liquidity sweep + reclaim + "
                "higher-low structure"
            )
        }

    if (
        SEND_EARLY
        and reclaim
        and structure_shift
    ):
        return {
            "setup": "C",
      
