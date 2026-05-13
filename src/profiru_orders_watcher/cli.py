from __future__ import annotations

import http.server
import threading
import time
from typing import Any, cast
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

import httpx
import typer
from bs4 import BeautifulSoup, Tag
from dotenv import load_dotenv
from rich.console import Console

from profiru_orders_watcher.config import load_config
from profiru_orders_watcher.fetchers.backoffice_selenium import BackofficeSeleniumFetcher
from profiru_orders_watcher.fetchers.public_html import _lego_landing_blocks
from profiru_orders_watcher.fetchers.public_html import PublicHtmlFetcher
from profiru_orders_watcher.filters import is_relevant
from profiru_orders_watcher.models import AppConfig, Order, SourceConfig
from profiru_orders_watcher.notifiers.telegram import TelegramNotifier
from profiru_orders_watcher.storage import OrderStorage

app = typer.Typer(no_args_is_help=True)
console = Console()


def _normalize_source_url(url: str) -> str:
    parsed = urlparse(url)
    query = urlencode(sorted(parse_qsl(parsed.query, keep_blank_values=True)))
    path = parsed.path.rstrip("/") + "/" if parsed.path else "/"
    return urlunparse((parsed.scheme, parsed.netloc, path, "", query, ""))


def _fetch_orders(source: SourceConfig, loaded: AppConfig) -> list[Order]:
    if source.kind == "public_html":
        return PublicHtmlFetcher(loaded.fetch).fetch(source)
    if source.kind == "backoffice_selenium":
        return BackofficeSeleniumFetcher(loaded.fetch).fetch(source)
    raise ValueError(f"Unknown source kind: {source.kind}")


def _expand_sources(loaded: AppConfig) -> list[SourceConfig]:
    enabled = [source for source in loaded.sources if source.enabled]
    if (
        not loaded.fetch.discover_related_sources
        and not loaded.fetch.discover_pservice_sources
        and not loaded.fetch.discover_paginated_sources
    ):
        return enabled

    expanded = list(enabled)
    seen_urls = {_normalize_source_url(str(source.url)) for source in expanded}

    for source in enabled:
        if source.kind != "public_html":
            continue
        urls: list[tuple[str, str]] = []
        if loaded.fetch.discover_related_sources:
            urls.extend((url, "discovered") for url in _discover_related_source_urls(source, loaded))
        if loaded.fetch.discover_pservice_sources:
            urls.extend((url, "pservice") for url in _discover_pservice_source_urls(source, loaded))
        if loaded.fetch.discover_paginated_sources:
            base_urls = [str(source.url), *(url for url, source_type in urls if source_type == "pservice")]
            urls.extend((url, "page") for base_url in base_urls for url in _paginated_source_urls(base_url, loaded))

        discovered_count = 0
        pservice_count = 0
        for url, source_type in urls:
            if source_type == "discovered" and discovered_count >= loaded.fetch.max_discovered_sources:
                continue
            if source_type == "pservice" and pservice_count >= loaded.fetch.max_pservice_sources:
                continue
            normalized = _normalize_source_url(url)
            if normalized in seen_urls:
                continue
            seen_urls.add(normalized)
            if source_type == "pservice":
                pservice_count += 1
                name = f"pservice-{len(expanded) + 1}"
            elif source_type == "page":
                name = f"page-{len(expanded) + 1}"
            else:
                discovered_count += 1
                name = f"discovered-{len(expanded) + 1}"
            expanded.append(
                SourceConfig.model_validate(
                    {
                        "name": name,
                        "kind": "public_html",
                        "url": url,
                        "enabled": True,
                    }
                )
            )
            if (
                discovered_count >= loaded.fetch.max_discovered_sources
                and pservice_count >= loaded.fetch.max_pservice_sources
            ):
                return expanded

    return expanded


def _with_query_param(url: str, name: str, value: str) -> str:
    parsed = urlparse(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query[name] = value
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", urlencode(sorted(query.items())), ""))


def _paginated_source_urls(url: str, loaded: AppConfig) -> list[str]:
    if loaded.fetch.max_pages_per_source < 2:
        return []

    urls: list[str] = []
    for param_name in loaded.fetch.pagination_param_names:
        for page in range(2, loaded.fetch.max_pages_per_source + 1):
            urls.append(_with_query_param(url, param_name, str(page)))
    return urls


def _discover_related_source_urls(source: SourceConfig, loaded: AppConfig) -> list[str]:
    headers = {"User-Agent": loaded.fetch.user_agent}
    with httpx.Client(
        timeout=loaded.fetch.timeout_seconds,
        headers=headers,
        follow_redirects=True,
    ) as client:
        response = client.get(str(source.url))
        response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    urls: list[str] = []
    seen: set[str] = set()
    for link in soup.find_all("a", href=True):
        if not isinstance(link, Tag):
            continue
        href = link.get("href")
        if not isinstance(href, str):
            continue
        absolute = urljoin(str(source.url), href)
        parsed = urlparse(absolute)
        path = parsed.path
        if not any(path.startswith(prefix) for prefix in loaded.fetch.related_source_prefixes):
            continue
        link_text = link.get_text(" ").lower()
        keyword_target = f"{path} {link_text}".lower()
        if loaded.fetch.related_source_keywords and not any(
            keyword.lower() in keyword_target for keyword in loaded.fetch.related_source_keywords
        ):
            continue
        if "?" in absolute or "#" in absolute:
            absolute = absolute.split("?", 1)[0].split("#", 1)[0]
        normalized = absolute.rstrip("/")
        if normalized in seen:
            continue
        seen.add(normalized)
        urls.append(f"{normalized}/")
    return urls


def _matches_keywords(value: str, include_keywords: list[str], exclude_keywords: list[str]) -> bool:
    normalized = value.lower()
    if include_keywords and not any(keyword.lower() in normalized for keyword in include_keywords):
        return False
    return not any(keyword.lower() in normalized for keyword in exclude_keywords)


def _discover_pservice_source_urls(source: SourceConfig, loaded: AppConfig) -> list[str]:
    headers = {"User-Agent": loaded.fetch.user_agent}
    with httpx.Client(
        timeout=loaded.fetch.timeout_seconds,
        headers=headers,
        follow_redirects=True,
    ) as client:
        response = client.get(str(source.url))
        response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    counts_by_id: dict[str, int] = {}
    pservices: list[dict[str, Any]] = []
    for block in _lego_landing_blocks(soup):
        counts = block.get("pserviceOrderCounts", [])
        if isinstance(counts, list):
            for count in counts:
                if not isinstance(count, dict):
                    continue
                pservice_id = count.get("pserviceId")
                order_count = count.get("count")
                if isinstance(pservice_id, str) and isinstance(order_count, int):
                    counts_by_id[pservice_id] = order_count

        filter_options = block.get("filterOptions", {})
        if isinstance(filter_options, dict) and isinstance(filter_options.get("pservices"), list):
            pservices.extend(
                cast(dict[str, Any], item) for item in filter_options["pservices"] if isinstance(item, dict)
            )

    urls: list[str] = []
    seen_ids: set[str] = set()
    base = _normalize_source_url(str(source.url)).split("?", 1)[0]
    for pservice in pservices:
        pservice_id = pservice.get("value")
        label = pservice.get("label")
        if not isinstance(pservice_id, str) or not isinstance(label, str):
            continue
        if pservice_id in seen_ids or counts_by_id.get(pservice_id, 0) <= 0:
            continue
        if not _matches_keywords(label, loaded.fetch.pservice_include_keywords, loaded.fetch.pservice_exclude_keywords):
            continue
        seen_ids.add(pservice_id)
        urls.append(f"{base}?{urlencode({'pserviceIds': pservice_id})}")
        if len(urls) >= loaded.fetch.max_pservice_sources:
            break

    return urls


@app.command("validate-config")
def validate_config(config: str = typer.Option("config.yaml", "--config", "-c")) -> None:
    loaded = load_config(config)
    enabled = [source.name for source in loaded.sources if source.enabled]
    console.print(f"Config is valid. Enabled sources: {', '.join(enabled) or 'none'}")


@app.command("run")
def run_once(config: str = typer.Option("config.yaml", "--config", "-c")) -> None:
    load_dotenv()
    loaded = load_config(config)
    storage = OrderStorage(loaded.storage.sqlite_path)
    notifier = TelegramNotifier()

    total = 0
    relevant = 0
    sent = 0

    for source in _expand_sources(loaded):

        console.print(f"Fetching source: {source.name}")
        try:
            orders = _fetch_orders(source, loaded)
        except Exception as exc:  # noqa: BLE001
            console.print(f"Source failed: {source.name}. Error: {exc}")
            continue

        total += len(orders)

        for order in orders:
            if not is_relevant(order, loaded.filters):
                continue
            relevant += 1
            if storage.exists(order):
                continue
            if not notifier.send(order):
                console.print(f"Notification failed: {order.title}")
                continue
            storage.save(order)
            sent += 1
            console.print(f"New relevant order: {order.title}")
            time.sleep(1)

        time.sleep(loaded.fetch.delay_between_requests_seconds)

    console.print(f"Done. Parsed: {total}. Relevant: {relevant}. New sent: {sent}.")


def _start_health_server(port: int = 8080) -> None:
    class HealthHandler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"OK")

        def log_message(self, format: str, *args: str) -> None:
            pass

    server = http.server.HTTPServer(("0.0.0.0", port), HealthHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()


@app.command("loop")
def run_loop(
    config: str = typer.Option("config.yaml", "--config", "-c"),
    interval: int = typer.Option(300, "--interval", "-i"),
) -> None:
    _start_health_server()
    while True:
        run_once(config=config)
        time.sleep(interval)


if __name__ == "__main__":
    app()
