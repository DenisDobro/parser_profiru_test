from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any, cast
from urllib.parse import parse_qs, urlencode, urljoin, urlparse

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
        return f"profi-order:{order_id}"
    return order.fingerprint


def _parse_public_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        cleaned = re.sub(r"\s*\([^)]*\)$", "", value).replace(" GMT", "")
        return datetime.strptime(cleaned, "%a %b %d %Y %H:%M:%S%z")
    except ValueError:
        return None


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


def _next_data(soup: BeautifulSoup) -> dict[str, Any]:
    script = soup.find("script", id="__NEXT_DATA__")
    if not script or not script.string:
        return {}
    try:
        payload = json.loads(script.string)
    except json.JSONDecodeError:
        return {}
    return cast(dict[str, Any], payload) if isinstance(payload, dict) else {}


def _lego_landing_blocks(soup: BeautifulSoup) -> list[dict[str, Any]]:
    payload = _next_data(soup)
    blocks = (
        payload.get("props", {})
        .get("pageProps", {})
        .get("legoData", {})
        .get("legoLandingData", {})
        .get("blocks", [])
    )
    return [cast(dict[str, Any], block) for block in blocks if isinstance(block, dict)]


def _extract_next_data_orders(soup: BeautifulSoup, source: SourceConfig) -> list[Order]:
    orders: list[Order] = []
    for block in _lego_landing_blocks(soup):
        current_orders = block.get("currentOrders", [])
        if not isinstance(current_orders, list):
            continue
        for item in current_orders:
            if not isinstance(item, dict):
                continue
            order_id = item.get("id")
            if not order_id:
                continue

            aim = _clean_text(str(item.get("aim") or ""))
            program = _clean_text(str(item.get("program") or ""))
            details = _clean_text(
                str(item.get("detailsPublic") or item.get("seoCleanedDetails") or item.get("seoCleanedDescription") or "")
            )
            pservices = item.get("pservices", [])
            pservice_names = [
                _clean_text(str(pservice.get("name")))
                for pservice in pservices
                if isinstance(pservice, dict) and pservice.get("name")
            ]

            title = aim or (pservice_names[-1] if pservice_names else "") or details or "Заказ Profi.ru"
            description = _clean_text(" ".join(part for part in [program, aim, details, ", ".join(pservice_names)] if part))

            price = item.get("wpriceMin")
            price_max = item.get("wpriceMax")
            raw_price = None
            if isinstance(price, int):
                raw_price = f"{price} ₽"
                if isinstance(price_max, int) and price_max != price:
                    raw_price = f"{price}-{price_max} ₽"
            else:
                price = None

            city = None
            raw_city = item.get("city")
            if isinstance(raw_city, dict):
                gity = raw_city.get("gity")
                if isinstance(gity, dict):
                    city = _clean_text(str(gity.get("name") or "")) or None

            url = urljoin(str(source.url), f"/backoffice/n.php?{urlencode({'o': str(order_id)})}")
            orders.append(
                Order(
                    source=source.name,
                    title=title,
                    url=url,
                    description=description or None,
                    city=city,
                    price=price,
                    raw_price=raw_price,
                    published_at=_parse_public_datetime(item.get("receivd") if isinstance(item.get("receivd"), str) else None),
                    raw=item,
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

        for order in _extract_next_data_orders(soup, source):
            identity = _order_identity(order)
            if identity not in seen:
                orders.append(order)
                seen.add(identity)

        for selector in ORDER_CARD_SELECTORS:
            for card in soup.select(selector):
                card_order = _extract_order_from_card(card, source)
                if card_order and _order_identity(card_order) not in seen:
                    orders.append(card_order)
                    seen.add(_order_identity(card_order))

        return orders
