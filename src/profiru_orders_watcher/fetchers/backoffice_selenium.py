from __future__ import annotations

import json
import os
import re
import time
from typing import Any

from bs4 import BeautifulSoup, Tag

from profiru_orders_watcher.fetchers.public_html import _clean_text, _parse_price
from profiru_orders_watcher.models import FetchConfig, Order, SourceConfig

ORDER_CONTAINER_CLASS = "OrderSnippetContainerStyles__Container-sc-1qf4h1o-0"
SUBJECT_CLASS = "SubjectAndPriceStyles__SubjectsText-sc-18v5hu8-1"
DESCRIPTION_CLASS = "SnippetBodyStyles__MainInfo-sc-tnih0-6"
PRICE_CLASS = "SubjectAndPriceStyles__PriceValue-sc-18v5hu8-5"
DATE_CLASS = "Date__DateText-sc-e1f8oi-1"

OLD_ORDER_WORDS = {
    "час",
    "часов",
    "вчера",
    "января",
    "февраля",
    "марта",
    "апреля",
    "мая",
    "июня",
    "июля",
    "августа",
    "сентября",
    "октября",
    "ноября",
    "декабря",
}


def _first_text(container: Tag, class_name: str) -> str | None:
    tag = container.find(class_=class_name)
    text = _clean_text(tag.get_text(" ") if isinstance(tag, Tag) else None)
    return text or None


def _extract_order_id(container: Tag) -> str | None:
    link = container.find("a")
    if not isinstance(link, Tag):
        return None

    raw_id = link.get("id")
    if isinstance(raw_id, str) and raw_id.strip():
        return raw_id.strip()

    href = link.get("href")
    if isinstance(href, str):
        match = re.search(r"(?:[?&]o=|/)(\d{4,})", href)
        if match:
            return match.group(1)

    return None


def parse_backoffice_orders(html: str, source: SourceConfig) -> list[Order]:
    soup = BeautifulSoup(html, "html.parser")
    orders: list[Order] = []
    seen: set[str] = set()

    for container in soup.find_all(class_=ORDER_CONTAINER_CLASS):
        if not isinstance(container, Tag):
            continue

        order_id = _extract_order_id(container)
        title = _first_text(container, SUBJECT_CLASS)
        description = _first_text(container, DESCRIPTION_CLASS)
        raw_price = _first_text(container, PRICE_CLASS)
        time_info = _first_text(container, DATE_CLASS)

        if not order_id or not title:
            continue

        price, parsed_raw_price = _parse_price(raw_price or "")
        response_url = f"https://profi.ru/backoffice/n.php?o={order_id}"
        order = Order(
            source=source.name,
            title=title,
            url=response_url,
            description=description,
            price=price,
            raw_price=raw_price or parsed_raw_price,
            raw={
                "order_id": order_id,
                "time_info": time_info,
                "response_url": response_url,
                "html_preview": str(container)[:1000],
            },
        )
        if order.fingerprint in seen:
            continue
        orders.append(order)
        seen.add(order.fingerprint)

    return orders


def is_fresh_backoffice_order(order: Order) -> bool:
    time_info = str(order.raw.get("time_info") or "").strip().lower()
    return not any(word in time_info for word in OLD_ORDER_WORDS)


class BackofficeSeleniumFetcher:
    def __init__(self, fetch_config: FetchConfig) -> None:
        self.fetch_config = fetch_config

    def fetch(self, source: SourceConfig) -> list[Order]:
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
        except ImportError as exc:
            raise RuntimeError("Selenium fetcher requires installing the 'selenium' package") from exc

        options = Options()
        chrome_bin = os.getenv("CHROME_BIN")
        if chrome_bin:
            options.binary_location = chrome_bin
        if self.fetch_config.selenium_headless:
            options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        if self.fetch_config.selenium_profile_path:
            options.add_argument(f"--user-data-dir={self.fetch_config.selenium_profile_path}")

        driver = webdriver.Chrome(options=options)
        try:
            _load_profi_cookies(driver)
            driver.get(str(source.url))
            time.sleep(self.fetch_config.selenium_page_wait_seconds)
            html = driver.page_source
        finally:
            driver.quit()

        return [order for order in parse_backoffice_orders(html, source) if is_fresh_backoffice_order(order)]


def _load_profi_cookies(driver: Any) -> None:
    raw_cookies = os.getenv("PROFI_COOKIES_JSON")
    if not raw_cookies:
        return

    try:
        cookies = json.loads(raw_cookies)
    except json.JSONDecodeError as exc:
        raise RuntimeError("PROFI_COOKIES_JSON must be a JSON array exported from the browser") from exc

    if not isinstance(cookies, list):
        raise RuntimeError("PROFI_COOKIES_JSON must be a JSON array")

    driver.get("https://profi.ru/")
    for cookie in cookies:
        if not isinstance(cookie, dict):
            continue
        if "expiry" not in cookie and "expirationDate" in cookie:
            cookie["expiry"] = int(cookie["expirationDate"])
        prepared = {
            key: value
            for key, value in cookie.items()
            if key in {"name", "value", "domain", "path", "expiry", "secure", "httpOnly", "sameSite"}
        }
        if prepared.get("sameSite") not in {None, "Strict", "Lax", "None"}:
            prepared.pop("sameSite", None)
        if "name" in prepared and "value" in prepared:
            driver.add_cookie(prepared)
