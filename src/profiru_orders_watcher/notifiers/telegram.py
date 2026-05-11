from __future__ import annotations

import os

import httpx

from profiru_orders_watcher.models import Order


def format_order_message(order: Order) -> str:
    parts = [
        f"Новый заказ: {order.title}",
        f"Источник: {order.source}",
    ]
    if order.city:
        parts.append(f"Город: {order.city}")
    if order.raw_price:
        parts.append(f"Бюджет: {order.raw_price}")
    if order.description:
        description = order.description[:700]
        parts.append(f"Описание: {description}")
    time_info = order.raw.get("time_info")
    if time_info:
        parts.append(f"Когда: {time_info}")
    parts.append(order.response_url)
    return "\n\n".join(parts)


class TelegramNotifier:
    def __init__(self, token: str | None = None, chat_id: str | None = None) -> None:
        self.token = token or os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID")

    @property
    def enabled(self) -> bool:
        return bool(self.token and self.chat_id)

    def send(self, order: Order) -> None:
        if not self.enabled:
            return

        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": format_order_message(order),
            "disable_web_page_preview": True,
            "reply_markup": {
                "inline_keyboard": [
                    [{"text": "Откликнуться", "url": order.response_url}],
                ],
            },
        }
        with httpx.Client(timeout=20) as client:
            response = client.post(url, json=payload)
            response.raise_for_status()
