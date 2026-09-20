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

MAX_ASSETS = int(
    os.environ.get("MAX_ASSETS", "60")
)

REQUEST_DELAY = float(
    os.environ.get("REQUEST_DELAY", "0.25")
)

SCAN_INTERVAL = int(
    os.environ.get("SCAN_INTERVAL", "600")
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

SEND_EARLY = (
    os.environ.get("SEND_EARLY", "1") == "1"
)

DRY_RUN = (
    os.environ.get("DRY_RUN", "0") == "1"
)

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

log = logging.getLogger(
    "kraken_scanner"
)


# ============================================================
# GLOBALS
# ============================================================

STOP_REQUESTED = False


# ============================================================
# HTTP SESSION
# ============================================================

SESSION = requests.Session()

SESSION.headers.update(
    {
        "User-Agent":
            "KrakenTelegramScanner/1.0"
    }
)


# ============================================================
# SIGNAL HANDLERS
# ============================================================

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


# ============================================================
# BASIC HELPERS
# ============================================================

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
    tmp_file = (
        STATE_FILE
        + ".tmp"
    )

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

    url = (
        f"{TELEGRAM_URL}/{method}"
    )

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
    url = (
        f"{KRAKEN_URL}/{endpoint}"
    )

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

        return payload.get(
            "result"
        )

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
    result = kraken_public(
        "AssetPairs"
    )

    if not result:
        return []

    pairs = []

    for pair_name, info in result.items():

        if not isinstance(
            info,
            dict
        ):
            continue

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

        status = str(
            info.get(
                "status",
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
            pairs.append(
                pair_name
            )

    pairs = sorted(
        set(pairs)
    )

    return pairs[
        :MAX_ASSETS
    ]


# ============================================================
# OHLC
# ============================================================

def parse_ohlc(rows):
