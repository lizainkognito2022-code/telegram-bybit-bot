import os
import requests
import matplotlib.pyplot as plt

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

KRAKEN_URL = "https://api.kraken.com/0/public/OHLC"


def send_photo(filename, caption):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"

    with open(filename, "rb") as photo:
        response = requests.post(
            url,
            data={
                "chat_id": CHAT_ID,
                "caption": caption
            },
            files={
                "photo": photo
            },
            timeout=60
        )

    print("Telegram:", response.status_code)
    print(response.text)

    response.raise_for_status()


def get_ohlc():
    response = requests.get(
        KRAKEN_URL,
        params={
            "pair": "XBTUSD",
            "interval": 60
        },
        timeout=30
    )

    response.raise_for_status()

    data = response.json()

    print("Kraken:", data.get("error"))

    result = data["result"]

    pair = [x for x in result if x != "last"][0]

    return result[pair]


def main():

    raw = get_ohlc()

    candles = raw[-30:]

    closes = [float(x[4]) for x in candles]
    highs = [float(x[2]) for x in candles]
    lows = [float(x[3]) for x in candles]

    current = closes[-1]
    resistance = max(highs[:-3])

    distance = ((resistance - current) / resistance) * 100

    plt.figure(figsize=(12, 6))

    plt.plot(
        closes,
        linewidth=2,
        label="BTC 1H"
    )

    plt.axhline(
        resistance,
        linestyle="--",
        linewidth=2,
        label=f"Resistance {resistance:,.0f}"
    )

    plt.axhline(
        current,
        linestyle=":",
        linewidth=1,
        label=f"Price {current:,.0f}"
    )

    plt.title(
        "INVEST ZONE — BTC/USD — 1H",
        fontsize=16
    )

    plt.xlabel("1H candles")
    plt.ylabel("Price")

    plt.grid(alpha=0.2)
    plt.legend()

    plt.tight_layout()

    filename = "invest_zone.png"

    plt.savefig(
        filename,
        dpi=150
    )

    plt.close()

    if distance <= 1.5:
        status = "🟡 ПОДЖАТИЕ — цена у сопротивления"
    else:
        status = "⚪ ПОДЖАТИЯ ПОКА НЕТ"

    caption = (
        "INVEST ZONE\n\n"
        f"{status}\n\n"
        f"BTC: ${current:,.2f}\n"
        f"Resistance: ${resistance:,.2f}\n"
        f"Distance: {distance:.2f}%\n\n"
        "Таймфрейм: 1H"
    )

    send_photo(
        filename,
        caption
    )


if __name__ == "__main__":
    main()
