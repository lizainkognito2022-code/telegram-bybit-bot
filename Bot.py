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
        print(f"Ошибка Telegram: {e}")


def main_keyboard():
    return {
        "keyboard": [
            [{"text": "🛒 ЧТО КУПИТЬ?"}]
        ],
        "resize_keyboard": True,
        "is_persistent": True
    }


def handle_message(chat_id, text):

    if text == "/start":
        send_message(
            chat_id,
            "🤖 INVEST ZONE\n\n"
            "Торговый анализ по структуре и поведению цены.\n\n"
            "Главный принцип:\n"
            "не покупать уже выросшую монету,\n"
            "а искать изменение баланса сил ДО основного импульса.\n\n"
            "Нажми кнопку ниже.",
            main_keyboard()
        )

    elif text == "🛒 ЧТО КУПИТЬ?":
        send_message(
            chat_id,
            "🔎 INVEST ZONE\n\n"
            "Запускаю поиск торговых сетапов...\n\n"
            "Приоритет:\n"
            "A — Поджатие → Пробой\n"
            "B — Пробой → Ретест → Продолжение\n"
            "C — Снятие ликвидности → Разворот\n\n"
            "Фильтры:\n"
            "• BTC Context\n"
            "• 4H Structure\n"
            "• 1H Setup\n"
            "• Volume\n"
            "• Open Interest\n"
            "• Funding\n"
            "• Liquidity\n"
            "• Room to Target\n"
            "• Structural Stop Loss\n\n"
            "⚠️ Анализатор рынка пока не подключён.\n"
            "Качественного сигнала пока не выдаю."
        )

    elif text == "/help":
        send_message(
            chat_id,
            "ℹ️ INVEST ZONE\n\n"
            "🛒 ЧТО КУПИТЬ? — поиск торговых сетапов
