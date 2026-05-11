from __future__ import annotations

import json
import re
from urllib.parse import parse_qs, urljoin, urlparse

import httpx
from bs4 import BeautifulSoup, Tag

from profiru_orders_watcher.models import FetchConfig, Order, SourceConfig

PRICE_RE = re.compile(r"(?P<price>\d[\d\s]{2,})\s*(₽|руб|р\.)", re.IGNORECASE)

ORDER_CARD_SELECTORS = [
    "article",
    "[data-test*='order']",
    "[class*='order']",
    "[class*='task']",
    "[class*='request']",
]


def _clean_text(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", value).strip()


def _parse_price(text: str) -> tuple[int | None, str | None]:
    match = PRICE_RE.search(text)
    if not match:
        return None, None
    raw = match.group(0)
    number = int(re.sub(r"\D", "", match.group("price")))
    return number, raw


def _order_identity(order: Order) -> str:
    parsed = urlparse(order.url)
    order_id = parse_qs(parsed.query).get("o", [None])[0]
    if order_id:
        return f"{order.source}:order:{order_id}"
    return order.fingerprint


def _extract_json_ld_orders(soup: BeautifulSoup, source: SourceConfig) -> list[Order]:
    orders: list[Order] = []
    scripts = soup.find_all("script", attrs={"type": "application/ld+json"})

    for script in scripts:
        if not script.string:
            continue
        try:
            payload = json.loads(script.string)
        except json.JSONDecodeError:
            continue

        items = payload if isinstance(payload, list) else [payload]
        for item in items:
            if not isinstance(item, dict):
                continue
            graph = item.get("@graph")
            candidates = graph if isinstance(graph, list) else [item]
            for candidate in candidates:
                if not isinstance(candidate, dict):
                    continue
                title = _clean_text(candidate.get("name") or candidate.get("title"))
                url = candidate.get("url") or str(source.url)
                description = _clean_text(candidate.get("description"))
                full_url = urljoin(str(source.url), str(url))
                if title and full_url.rstrip("/") != str(source.url).rstrip("/"):
                    price, raw_price = _parse_price(" ".join([title, description]))
                    orders.append(
                        Order(
                            source=source.name,
                            title=title,
                            url=full_url,
                            description=description or None,
                            price=price,
                            raw_price=raw_price,
                            raw=candidate,
                        )
                    )
    return orders


def _extract_order_from_card(card: Tag, source: SourceConfig) -> Order | None:
    text = _clean_text(card.get_text(" "))
    if len(text) < 20:
        return None

    link = card.find("a", href=lambda href: isinstance(href, str) and "o=" in href)
    if not isinstance(link, Tag):
        link = card.find("a", href=True)
    if not isinstance(link, Tag):
        return None

    href = link.get("href") if isinstance(link, Tag) else None
    url = urljoin(str(source.url), str(href)) if href else str(source.url)

    heading = card.find(["h1", "h2", "h3", "h4"])
    title = _clean_text(heading.get_text(" ") if heading else None)
    if not title and link:
        title = _clean_text(link.get_text(" "))
    if not title:
        title = text[:120]

    price, raw_price = _parse_price(text)

    return Order(
        source=source.name,
        title=title,
        url=url,
        description=text,
        price=price,
        raw_price=raw_price,
        raw={"html_preview": str(card)[:1000]},
    )


class PublicHtmlFetcher:
    def __init__(self, fetch_config: FetchConfig) -> None:
        self.fetch_config = fetch_config

    def fetch(self, source: SourceConfig) -> list[Order]:
        headers = {"User-Agent": self.fetch_config.user_agent}
        with httpx.Client(timeout=self.fetch_config.timeout_seconds, headers=headers, follow_redirects=True) as client:
            response = client.get(str(source.url))
            response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        orders = _extract_json_ld_orders(soup, source)
        seen = {_order_identity(order) for order in orders}

        for selector in ORDER_CARD_SELECTORS:
            for card in soup.select(selector):
                order = _extract_order_from_card(card, source)
                if order and _order_identity(order) not in seen:
                    orders.append(order)
                    seen.add(_order_identity(order))

        return orders
