from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from typing import Any
from urllib.parse import parse_qs, urlparse

from pydantic import BaseModel, Field, HttpUrl


class SourceConfig(BaseModel):
    name: str
    url: HttpUrl
    enabled: bool = True
    kind: str = "public_html"


class FilterConfig(BaseModel):
    include_keywords: list[str] = Field(default_factory=list)
    exclude_keywords: list[str] = Field(default_factory=list)
    cities: list[str] = Field(default_factory=list)
    min_price: int | None = None
    max_price: int | None = None


class FetchConfig(BaseModel):
    timeout_seconds: int = 20
    delay_between_requests_seconds: int = 5
    user_agent: str = "Mozilla/5.0 profiru-orders-watcher/0.1"
    discover_related_sources: bool = False
    max_discovered_sources: int = 25
    related_source_prefixes: list[str] = Field(default_factory=lambda: ["/rabota/repetitor/"])
    related_source_keywords: list[str] = Field(default_factory=list)
    selenium_headless: bool = True
    selenium_page_wait_seconds: int = 10
    selenium_profile_path: str | None = None


class StorageConfig(BaseModel):
    sqlite_path: str = "./data/orders.sqlite3"


class AppConfig(BaseModel):
    sources: list[SourceConfig]
    filters: FilterConfig = Field(default_factory=FilterConfig)
    fetch: FetchConfig = Field(default_factory=FetchConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)


class Order(BaseModel):
    source: str
    title: str
    url: str
    description: str | None = None
    city: str | None = None
    price: int | None = None
    raw_price: str | None = None
    published_at: datetime | None = None
    collected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    raw: dict[str, Any] = Field(default_factory=dict)

    @property
    def response_url(self) -> str:
        if self.raw.get("response_url"):
            return str(self.raw["response_url"])
        return self.url

    @property
    def fingerprint(self) -> str:
        order_id = parse_qs(urlparse(self.url).query).get("o", [None])[0]
        if order_id:
            return sha256(f"profi-order:{order_id}".encode("utf-8")).hexdigest()

        base = "|".join(
            [
                self.source.strip().lower(),
                self.url.strip().lower(),
                self.title.strip().lower(),
                (self.description or "").strip().lower()[:300],
            ]
        )
        return sha256(base.encode("utf-8")).hexdigest()

    @property
    def searchable_text(self) -> str:
        parts = [self.title, self.description or "", self.city or "", self.raw_price or ""]
        return "\n".join(parts).lower()
