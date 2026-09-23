import os
import time
import math
import io
from datetime import datetime, timezone

import requests
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle


# ============================================================
# CONFIG
# ============================================================

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

KRAKEN_API = "https://api.kraken.com/0/public"

MAX_ASSETS = 60
REQUEST_DELAY = 0.25

TIMEFRAME_1H = 60
TIMEFRAME_30M = 30
TIMEFRAME_4H = 240

MIN_CANDLES = 80

BTC_PAIR = "XBTUSD"

EXCLUDED_BASES = {
    "BTC",
    "XBT",
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


# ============================================================
# HTTP
# ============================================================

SESSION
