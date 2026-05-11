from __future__ import annotations

import time
from urllib.parse import urljoin, urlparse

import httpx
import typer
from bs4 import BeautifulSoup, Tag
from dotenv import load_dotenv
from rich.console import Console

from profiru_orders_watcher.config import load_config
from profiru_orders_watcher.fetchers.backoffice_selenium import BackofficeSeleniumFetcher
from profiru_orders_watcher.fetchers.public_html import PublicHtmlFetcher
from profiru_orders_watcher.filters import is_relevant
from profiru_orders_watcher.models import AppConfig, Order, SourceConfig
from profiru_orders_watcher.notifiers.telegram import TelegramNotifier
from profiru_orders_watcher.storage import OrderStorage

app = typer.Typer(no_args_is_help=True)
console = Console()


def _fetch_orders(source: SourceConfig, loaded: AppConfig) -> list[Order]:
    if source.kind == "public_html":
        return PublicHtmlFetcher(loaded.fetch).fetch(source)
    if source.kind == "backoffice_selenium":
        return BackofficeSeleniumFetcher(loaded.fetch).fetch(source)
    raise ValueError(f"Unknown source kind: {source.kind}")


def _expand_sources(loaded: AppConfig) -> list[SourceConfig]:
    enabled = [source for source in loaded.sources if source.enabled]
    if not loaded.fetch.discover_related_sources:
        return enabled

    expanded = list(enabled)
    seen_urls = {str(source.url).rstrip("/") for source in expanded}

    for source in enabled:
        if source.kind != "public_html":
            continue
        for url in _discover_related_source_urls(source, loaded):
            normalized = url.rstrip("/")
            if normalized in seen_urls:
                continue
            seen_urls.add(normalized)
            expanded.append(
                SourceConfig.model_validate(
                    {
                        "name": f"discovered-{len(expanded) + 1}",
                        "kind": "public_html",
                        "url": url,
                        "enabled": True,
                    }
                )
            )
            if len(expanded) >= len(enabled) + loaded.fetch.max_discovered_sources:
                return expanded

    return expanded


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
        if "?" in absolute or "#" in absolute:
            absolute = absolute.split("?", 1)[0].split("#", 1)[0]
        normalized = absolute.rstrip("/")
        if normalized in seen:
            continue
        seen.add(normalized)
        urls.append(f"{normalized}/")
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


@app.command("loop")
def run_loop(
    config: str = typer.Option("config.yaml", "--config", "-c"),
    interval: int = typer.Option(300, "--interval", "-i"),
) -> None:
    while True:
        run_once(config=config)
        time.sleep(interval)


if __name__ == "__main__":
    app()
