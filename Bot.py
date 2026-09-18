import os
import requests

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

TELEGRAM_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"
COINGECKO_URL = "https://api.coingecko.com/api/v3"


def send_message(chat_id, text):
    requests.post(
        f"{TELEGRAM_URL}/sendMessage",
        json={
            "chat_id": chat_id,
            "text": text
        },
        timeout=15
    )


def get_btc_data():
    response = requests.get(
        f"{COINGECKO_URL}/coins/bitcoin/market_chart",
        params={
            "vs_currency": "usd",
            "days": "7",
            "interval": "hourly"
        },
        timeout=20
    )

    response.raise_for_status()

    return response.json()


def make_candles(data):
    prices = data.get("prices", [])
    volumes = data.get("total_volumes", [])

    if len(prices) < 10:
        raise Exception("Недостаточно ценовых данных")

    candles = []

    volume_map = {}

    for item in volumes:
        timestamp = item[0]
        volume_map[timestamp] = item[1]

    for i in range(1, len(prices)):
        timestamp = prices[i][0]
        current_price = float(prices[i][1])
        previous_price = float(prices[i - 1][1])

        high = max(
            current_price,
            previous_price
        )

        low = min(
            current_price,
            previous_price
        )

        open_price = previous_price
        close_price = current_price

        volume = float(
            volume_map.get(timestamp, 0)
        )

        candles.append({
            "timestamp": timestamp,
            "open": open_price,
            "high": high,
            "low": low,
            "close": close_price,
            "volume": volume
        })

    return candles


def calculate_atr(candles, period=14):
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

    return sum(
        ranges[-period:]
    ) / period


def main():
    try:
        data = get_btc_data()

        candles = make_candles(data)

        if len(candles) < 20:
            raise Exception(
                "Недостаточно свечей"
            )

        last = candles[-1]

        atr = calculate_atr(
            candles,
            14
        )

        recent_high = max(
            candle["high"]
            for candle in candles[-20:]
        )

        recent_low = min(
            candle["low"]
            for candle in candles[-20:]
        )

        average_volume = sum(
            candle["volume"]
            for candle in candles[-20:]
        ) / 20

        if average_volume > 0:
            volume_ratio = (
                last["volume"]
                / average_volume
            )
        else:
            volume_ratio = 0

        message = (
            "🟢 INVEST ZONE\n\n"
            "BTC OHLCV тест пройден.\n\n"
            f"Open: {last['open']:,.2f}\n"
            f"High: {last['high']:,.2f}\n"
            f"Low: {last['low']:,.2f}\n"
            f"Close: {last['close']:,.2f}\n\n"
            f"ATR(14): {atr:,.2f}\n"
            f"20H High: {recent_high:,.2f}\n"
            f"20H Low: {recent_low:,.2f}\n"
            f"Volume ratio: {volume_ratio:.2f}x\n\n"
            f"Свечей получено: {len(candles)}"
        )

        send_message(
            CHAT_ID,
            message
        )

    except Exception as e:

        send_message(
            CHAT_ID,
            f"🔴 Ошибка OHLCV:\n{e}"
        )


if __name__ == "__main__":
    main()
