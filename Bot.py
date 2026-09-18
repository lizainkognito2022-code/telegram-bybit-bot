import os
import time
import requests

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"


def send_message(chat_id, text, keyboard=None):
    data = {
        "chat_id": chat_id,
        "text": text
    }

    if keyboard:
        data["reply_markup"] = keyboard

    try:
        requests.post(
            f"{API_URL}/sendMessage",
            json=data,
            timeout=10
        )
    except Exception as e:
        print("Telegram error:", e)


def keyboard():
    return {
        "keyboard": [
            [{"text": "🛒 ЧТО КУПИТЬ?"}]
        ],
        "resize_keyboard": True,
        "is_persistent": True
    }


def handle_message(chat_id, text):

    if text == "/start":
        message = (
            "🤖 INVEST ZONE\n\n"
            "Торговый анализ по структуре и поведению цены.\n\n"
            "Главный принцип:\n"
            "искать изменение баланса сил ДО основного импульса.\n\n"
            "Нажми кнопку ниже."
        )

        send_message(chat_id, message, keyboard())

    elif text == "🛒 ЧТО КУПИТЬ?":

        message = (
            "🔎 INVEST ZONE\n\n"
            "Поиск торговых сетапов...\n\n"
            "A — Поджатие → Пробой\n"
            "B — Пробой → Ретест → Продолжение\n"
            "C — Снятие ликвидности → Разворот\n\n"
            "Фильтры:\n"
            "BTC Context\n"
            "4H Structure\n"
            "1H Setup\n"
            "Volume\n"
            "Open Interest\n"
            "Funding\n"
            "Liquidity\n"
            "Room to Target\n"
            "Structural Stop Loss\n\n"
            "⚠️ Анализатор рынка пока не подключён.\n"
            "Качественного сигнала пока не выдаю."
        )

        send_message(chat_id, message)

    elif text == "/help":

        message = (
            "ℹ️ INVEST ZONE\n\n"
            "🛒 ЧТО КУПИТЬ? — поиск торговых сетапов.\n\n"
            "A — Поджатие → Пробой\n"
            "B — Пробой → Ретест → Продолжение\n"
            "C — Снятие ликвидности → Разворот"
        )

        send_message(chat_id, message)

    else:
        send_message(
            chat_id,
            "Используй кнопку 🛒 ЧТО КУПИТЬ?"
        )


def main():

    offset = 0

    send_message(
        CHAT_ID,
        "🟢 INVEST ZONE запущен.\n\n"
        "Нажми кнопку 🛒 ЧТО КУПИТЬ?",
        keyboard()
    )

    while True:

        try:

            response = requests.get(
                f"{API_URL}/getUpdates",
                params={
                    "offset": offset,
                    "timeout": 30
                },
                timeout=35
            )

            data = response.json()

            for update in data.get("result", []):

                offset = update["update_id"] + 1

                message = update.get("message")

                if message is None:
                    continue

                chat_id = message["chat"]["id"]
                text = message.get("text", "")

                handle_message(chat_id, text)

        except Exception as e:

            print("Ошибка:", e)
            time.sleep(5)


if __name__ == "__main__":
    main()
