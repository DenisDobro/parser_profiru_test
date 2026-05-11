from __future__ import annotations

from profiru_orders_watcher.models import FilterConfig, Order


def _contains_any(text: str, keywords: list[str]) -> bool:
    return any(keyword.strip().lower() in text for keyword in keywords if keyword.strip())


def is_relevant(order: Order, config: FilterConfig) -> bool:
    text = order.searchable_text

    if config.include_keywords and not _contains_any(text, config.include_keywords):
        return False

    if config.exclude_keywords and _contains_any(text, config.exclude_keywords):
        return False

    if config.cities:
        city_text = (order.city or "").lower()
        full_text = order.searchable_text
        allowed = [city.lower() for city in config.cities]
        if not any(city in city_text or city in full_text for city in allowed):
            return False

    if config.min_price is not None and order.price is not None and order.price < config.min_price:
        return False

    if config.max_price is not None and order.price is not None and order.price > config.max_price:
        return False

    return True
