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


BOT_TOKEN = os.environ["BOT_TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]

KRAKEN_URL = "https://api.kraken.com/0/public"
TELEGRAM_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

MAX_ASSETS = int(os.environ.get("MAX_ASSETS", "30"))
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


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

log = logging.getLogger("kraken_scanner")

STOP_REQUESTED = False

SESSION = requests.Session()

SESSION.headers.update({
    "User-Agent": "KrakenTelegramScanner/1.0"
})


def handle_stop(signum, frame):
    global STOP_REQUESTED

    STOP_REQUESTED = True

    log.info(
        "Stop signal received: %s",
        signum
    )


signal.signal(
    signal.SIGINT,
    handle_stop
)

signal.signal(
    signal.SIGTERM,
    handle_stop
)


def now_ts():
    return int(
        datetime.now(
            timezone.utc
        ).timestamp()
    )


def safe_float(
    value,
    default=0.0
):
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
            data = json.load(file)

        if isinstance(data, dict):
            return data

    except Exception as error:
        log.warning(
            "State load failed: %s",
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
            "State save failed: %s",
            error
        )


def cleanup_state(state):
    current = now_ts()
    result = {}

    for key, value in state.items():
        if not isinstance(
            value,
            dict
        ):
            continue

        timestamp = int(
            value.get(
                "timestamp",
                0
            )
        )

        if (
            current - timestamp
            <= STATE_TTL
        ):
            result[key] = value

    return result


def telegram_request(
    method,
    data=None,
    files=None
):
    if DRY_RUN:
        log.info(
            "DRY_RUN Telegram: %s",
            method
        )
        return True

    try:
        response = SESSION.post(
            f"{TELEGRAM_URL}/{method}",
            data=data,
            files=files,
            timeout=30
        )

        response.raise_for_status()

        payload = response.json()

        if not payload.get("ok"):
            log.error(
                "Telegram error: %s",
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
    path,
    caption
):
    if DRY_RUN:
        log.info(
            "DRY_RUN photo: %s",
            path
        )
        return True

    try:
        with open(
            path,
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
            "Photo send failed: %s",
            error
        )
        return False


def kraken_public(
    endpoint,
    params=None
):
    try:
        response = SESSION.get(
            f"{KRAKEN_URL}/{endpoint}",
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

        return payload.get(
            "result"
        )

    except Exception as error:
        log.warning(
            "Kraken request failed: %s",
            error
        )
        return None


def get_usd_pairs():
    result = kraken_public(
        "AssetPairs"
    )

    if not result:
        return []

    pairs = []

    for name, info in result.items():
        if not isinstance(
            info,
            dict
        ):
            continue

        status = str(
            info.get(
                "status",
                ""
            )
        )

        wsname = str(
            info.get(
                "wsname",
                ""
            )
        )

        quote = str(
            info.get(
                "quote",
                ""
            )
        )

        if status not in (
            "",
            "online"
        ):
            continue

        if (
            "/USD" in wsname
            or quote in (
                "USD",
                "ZUSD"
            )
        ):
            pairs.append(name)

    return sorted(
        set(pairs)
    )[:MAX_ASSETS]


def parse_ohlc(rows):
    candles = []

    if not rows:
        return candles

    for row in rows:
        if len(row) < 7:
            continue

        candles.append({
            "time": int(
                safe_float(row[0])
            ),
            "open": safe_float(row[1]),
            "high": safe_float(row[2]),
            "low": safe_float(row[3]),
            "close": safe_float(row[4]),
            "vwap": safe_float(row[5]),
            "volume": safe_float(row[6]),
            "count": (
                int(
                    safe_float(row[7])
                )
                if len(row) > 7
                else 0
            )
        })

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
        if key != "last":
            rows = value
            break

    candles = parse_ohlc(
        rows or []
    )

    if limit:
        return candles[-limit:]

    return candles


def candle_range(candle):
    return (
        candle["high"]
        - candle["low"]
    )


def find_swing_highs(
    candles,
    left=2,
    right=2
):
    result = []

    if len(candles) < (
        left + right + 1
    ):
        return result

    for index in range(
        left,
        len(candles) - right
    ):
        high = candles[
            index
        ]["high"]

        left_ok = all(
            candles[j]["high"] < high
            for j in range(
                index - left,
                index
            )
        )

        right_ok = all(
            candles[j]["high"] < high
            for j in range(
                index + 1,
                index + right + 1
            )
        )

        if left_ok and right_ok:
            result.append(
                (
                    index,
                    high
                )
            )

    return result


def find_swing_lows(
    candles,
    left=2,
    right=2
):
    result = []

    if len(candles) < (
        left + right + 1
    ):
        return result

    for index in range(
        left,
        len(candles) - right
    ):
        low = candles[
            index
        ]["low"]

        left_ok = all(
            candles[j]["low"] > low
            for j in range(
                index - left,
                index
            )
        )

        right_ok = all(
            candles[j]["low"] > low
            for j in range(
                index + 1,
                index + right + 1
            )
        )

        if left_ok and right_ok:
            result.append(
                (
                    index,
                    low
                )
            )

    return result


def check_higher_lows(candles):
    lows = find_swing_lows(
        candles
    )

    return (
        len(lows) >= 2
        and lows[-1][1] > lows[-2][1]
    )


def check_higher_highs(candles):
    highs = find_swing_highs(
        candles
    )

    return (
        len(highs) >= 2
        and highs[-1][1] > highs[-2][1]
    )


def find_resistance(candles):
    if len(candles) < 10:
        return None

    highs = find_swing_highs(
        candles
    )

    if highs:
        return highs[-1][1]

    return max(
        candle["high"]
        for candle in candles[-20:]
    )


def price_near_resistance(
    price,
    resistance,
    tolerance=0.015
):
    if not resistance:
        return False

    distance = (
        resistance - price
    ) / resistance

    return (
        -0.005
        <= distance
        <= tolerance
    )


def check_compression(candles):
    if len(candles) < 20:
        return False

    recent = average([
        candle_range(c)
        for c in candles[-10:]
    ])

    previous = average([
        candle_range(c)
        for c in candles[-20:-10]
    ])

    return (
        previous > 0
        and recent <= previous * 0.85
    )


def volume_expansion(candles):
    if len(candles) < 20:
        return False

    current = candles[
        -1
    ]["volume"]

    previous = average([
        candle["volume"]
        for candle in candles[-11:-1]
    ])

    return (
        previous > 0
        and current >= previous * 1.5
    )


def check_breakout(
    candles,
    resistance
):
    if (
        resistance is None
        or len(candles) < 5
    ):
        return False

    current = candles[-1]

    return (
        current["close"] > resistance
        and current["high"] > resistance
    )


def check_30m_confirmation(
    candles
):
    if len(candles) < 10:
        return False

    closes = [
        candle["close"]
        for candle in candles
    ]

    return (
        closes[-1]
        >= max(closes[-6:-1])
    )


def check_30m_structure(
    candles
):
    if len(candles) < 20:
        return False

    return check_higher_lows(
        candles[-40:]
    )


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

    short_ma = average(
        closes[-10:]
    )

    long_ma = average(
        closes[-30:]
    )

    if short_ma > long_ma:
        return "UP"

    if short_ma < long_ma:
        return "DOWN"

    return "NEUTRAL"


def detect_setup_a(
    candles_1h,
    candles_30m
):
    if len(candles_1h) < 30:
        return None

    resistance = find_resistance(
        candles_1h
    )

    if resistance is None:
        return None

    price = candles_1h[
        -1
    ]["close"]

    breakout = check_breakout(
        candles_1h,
        resistance
    )

    volume_ok = volume_expansion(
        candles_1h
    )

    confirmation = (
        check_30m_confirmation(
            candles_30m
        )
        or check_30m_structure(
            candles_30m
        )
    )

    if (
        breakout
        and volume_ok
        and confirmation
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
        and check_higher_lows(
            candles_1h[-60:]
        )
        and check_compression(
            candles_1h
        )
        and price_near_resistance(
            price,
            resistance
        )
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

    for index, candle in enumerate(
        recent
    ):
        if candle["close"] > resistance:
            breakout_index = index
            break

    if breakout_index is None:
        return None

    after = recent[
        breakout_index + 1:
    ]

    if not after:
        return None

    retest = any(
        candle["low"]
        <= resistance * 1.005
        for candle in after
    )

    hold = any(
        candle["close"]
        > resistance
        for candle in after
    )

    if not retest or not hold:
        return None

    current = candles_1h[
        -1
    ]

    confirmation = (
        check_30m_confirmation(
            candles_30m
        )
        or check_30m_structure(
            candles_30m
        )
    )

    if (
        current["close"] > resistance
        and confirmation
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

    if SEND_EARLY:
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


def detect_setup_c(
    candles_1h,
    candles_30m
):
    if len(candles_1h) < 40:
        return None

    swings = find_swing_lows(
        candles_1h[:-5]
    )

    if not swings:
        return None

    swing_low = swings[
        -1
    ][1]

    swept = False
    reclaim = False

    for candle in candles_1h[-10:]:
        if candle["low"] < swing_low:
            swept = True

        if (
            swept
            and candle["close"] > swing_low
        ):
            reclaim = True

    if not swept or not reclaim:
        return None

    structure = check_higher_lows(
        candles_1h[-30:]
    )

    confirmation = (
        check_30m_confirmation(
            candles_30m
        )
        or check_30m_structure(
            candles_30m
        )
    )

    current = candles_1h[
        -1
    ]

    resistance = find_resistance(
        candles_1h
    )

    if structure and confirmation:
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

    if SEND_EARLY and structure:
        return {
            "setup": "C",
            "type": "EARLY",
            "resistance": resistance,
            "price": current["close"],
            "swing_low": swing_low,
            "reason": (
                "Sweep + reclaim + "
                "structure shift"
            )
        }

    return None


def calculate_stop(
    candles,
    signal
):
    price = safe_float(
        signal.get("price")
    )

    if signal.get("setup") == "C":
        swing_low = safe_float(
            signal.get("swing_low")
        )

        if swing_low > 0:
            return swing_low * 0.995

    lows = [
        candle["low"]
        for candle in candles[-10:]
    ]

    if lows:
        return min(lows) * 0.995

    return price * 0.98


def analyze_asset(
    pair,
    btc_context
):
    candles_1h = get_ohlc(
        pair,
        60,
        LOOKBACK_1H
    )

    time.sleep(
        REQUEST_DELAY
    )

    candles_30m = get_ohlc(
        pair,
        30,
        LOOKBACK_30M
    )

    if (
        len(candles_1h) < 30
        or len(candles_30m) < 10
    ):
        return None

    if btc_context == "DOWN":
        return None

    detectors = (
        detect_setup_a,
        detect_setup_b,
        detect_setup_c
    )

    for detector in detectors:
        result = detector(
            candles_1h,
            candles_30m
        )

        if result:
            result["pair"] = pair
            result["candles_1h"] = candles_1h
            result["candles_30m"] = candles_30m
            return result

    return None


def draw_candles(
    ax,
    candles,
    resistance=None,
    price=None,
    stop=None
):
    data = candles[
        -CHART_CANDLES:
    ]

    for index, candle in enumerate(
        data
    ):
        open_price = candle["open"]
        close_price = candle["close"]
        high = candle["high"]
        low = candle["low"]

        bullish = (
            close_price >= open_price
        )

        color = (
            "green"
            if bullish
            else "red"
        )

        body_low = min(
            open_price,
            close_price
        )

        body_height = abs(
            close_price
            - open_price
        )

        if body_height == 0:
            body_height = max(
                candle_range(candle) * 0.01,
                1e-10
            )

        ax.plot(
            [index, index],
            [low, high],
            color=color,
            linewidth=1
        )

        ax.add_patch(
            Rectangle(
                (
                    index - 0.3,
                    body_low
                ),
                0.6,
                body_height,
                facecolor=color,
                edgecolor=color,
                linewidth=0.5
            )
        )

    if resistance is not None:
        ax.axhline(
            resistance,
            linestyle="--",
            linewidth=1.2,
            label="Resistance"
        )

    if price is not None:
        ax.axhline(
            price,
            linestyle=":",
            linewidth=1,
            label="Entry"
        )

    if stop is not None:
        ax.axhline(
            stop,
            linestyle="-.",
            linewidth=1,
            label="Stop"
        
