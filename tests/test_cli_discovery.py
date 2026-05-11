import respx
from httpx import Response

from profiru_orders_watcher.cli import _discover_related_source_urls, _expand_sources
from profiru_orders_watcher.models import AppConfig, FetchConfig, SourceConfig


@respx.mock
def test_discover_related_source_urls_filters_repetitor_paths() -> None:
    source = SourceConfig(name="history", url="https://profi.ru/rabota/repetitor/istoriya/")
    config = AppConfig(
        sources=[source],
        fetch=FetchConfig(discover_related_sources=True),
    )
    respx.get("https://profi.ru/rabota/repetitor/istoriya/").mock(
        return_value=Response(
            200,
            text="""
            <a href="/rabota/repetitor/obshchestvoznanie/">Обществознание</a>
            <a href="/rabota/remont/">Ремонт</a>
            <a href="/rabota/repetitor/repetitor-po-podgotovke-k-ege-po-istorii/?x=1">ЕГЭ</a>
            """,
        )
    )

    urls = _discover_related_source_urls(source, config)

    assert urls == [
        "https://profi.ru/rabota/repetitor/obshchestvoznanie/",
        "https://profi.ru/rabota/repetitor/repetitor-po-podgotovke-k-ege-po-istorii/",
    ]


@respx.mock
def test_expand_sources_respects_discovery_limit() -> None:
    source = SourceConfig(name="history", url="https://profi.ru/rabota/repetitor/istoriya/")
    config = AppConfig(
        sources=[source],
        fetch=FetchConfig(discover_related_sources=True, max_discovered_sources=1),
    )
    respx.get("https://profi.ru/rabota/repetitor/istoriya/").mock(
        return_value=Response(
            200,
            text="""
            <a href="/rabota/repetitor/obshchestvoznanie/">Обществознание</a>
            <a href="/rabota/repetitor/repetitor-po-podgotovke-k-ege-po-istorii/">ЕГЭ</a>
            """,
        )
    )

    sources = _expand_sources(config)

    assert [source.name for source in sources] == ["history", "discovered-2"]


@respx.mock
def test_discover_related_source_urls_filters_keywords() -> None:
    source = SourceConfig(name="history", url="https://profi.ru/rabota/repetitor/istoriya/")
    config = AppConfig(
        sources=[source],
        fetch=FetchConfig(
            discover_related_sources=True,
            related_source_keywords=["истори", "istor"],
        ),
    )
    respx.get("https://profi.ru/rabota/repetitor/istoriya/").mock(
        return_value=Response(
            200,
            text="""
            <a href="/rabota/repetitor/repetitor-po-podgotovke-k-ege-po-istorii/">ЕГЭ</a>
            <a href="/rabota/repetitor/obshchestvoznanie/">Обществознание</a>
            <a href="/rabota/repetitor/repetitor-po-podgotovke-k-ege-po-fizike/">ЕГЭ по физике</a>
            """,
        )
    )

    urls = _discover_related_source_urls(source, config)

    assert urls == [
        "https://profi.ru/rabota/repetitor/repetitor-po-podgotovke-k-ege-po-istorii/",
    ]
