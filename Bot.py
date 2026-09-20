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
            info.get("ws
