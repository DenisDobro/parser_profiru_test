from __future__ import annotations

import time

import typer
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

    for source in loaded.sources:
        if not source.enabled:
            continue

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
            storage.save(order)
            notifier.send(order)
            sent += 1
            console.print(f"New relevant order: {order.title}")

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
