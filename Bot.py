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

MAX_ASSETS = 60
REQUEST_DELAY = 0.25

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

log = logging.getLogger("scanner")


# ============================================================
# GLOBALS
# ============================================================

STOP_REQUESTED = False


# ============================================================
# SIGNAL HANDLING
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
# HTTP SESSION
# ============================================================

SESSION = requests.Session()

SESSION.headers.update(
    {
        "User-Agent":
            "KrakenTelegramCryptoScanner/1.0"
    }
)


# ============================================================
# UTILS
# ============================================================

def now_ts():
    return int(
        datetime.now(
            timezone.utc
        ).timestamp()
    )


def safe_float(value, default=0.0):
    try:
        return float(value)
    except Exception:
        return default


def fmt_price(value):
    value = safe_float(value)

    if value >= 1000:
        return f"{value:,.2f}"

    if value >= 1:
        return f"{value:,.4f}"

    if value >= 0.01:
        return f"{value:,.6f}"

    return f"{value:.8f}"


def pct_change(a, b):
    a = safe_float(a)
    b = safe_float(b)

    if a == 0:
        return 0.0

    return (
        (b - a) / a
    ) * 100.0


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
        ) as f:
            state = json.load(f)

        if not isinstance(state, dict):
            return {}

        return state

    except Exception as e:
        log.warning(
            "Could not load state: %s",
            e
        )

        return {}


def save_state(state):
    tmp_file = STATE_FILE + ".tmp
