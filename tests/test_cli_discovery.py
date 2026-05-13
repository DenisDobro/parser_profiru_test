import respx
from httpx import Response

from profiru_orders_watcher.cli import (
    _discover_pservice_source_urls,
    _discover_related_source_urls,
    _expand_sources,
    _paginated_source_urls,
)
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


@respx.mock
def test_discover_pservice_source_urls_filters_history_services() -> None:
    source = SourceConfig(name="history", url="https://profi.ru/rabota/repetitor/istoriya/")
    config = AppConfig(
        sources=[source],
        fetch=FetchConfig(
            discover_pservice_sources=True,
            max_pservice_sources=5,
            pservice_include_keywords=["истори", "ЕГЭ", "ОГЭ", "ВПР"],
            pservice_exclude_keywords=["обществозн", "искусств", "балет", "архитектур"],
        ),
    )
    respx.get("https://profi.ru/rabota/repetitor/istoriya/").mock(
        return_value=Response(
            200,
            text="""
            <script id="__NEXT_DATA__" type="application/json">
            {
              "props": {
                "pageProps": {
                  "legoData": {
                    "legoLandingData": {
                      "blocks": [
                        {
                          "filterOptions": {
                            "pservices": [
                              {"label": "ЕГЭ по истории", "value": "1010080"},
                              {"label": "ОГЭ по истории", "value": "1010081"},
                              {"label": "История искусств", "value": "2000561"},
                              {"label": "Обществознание", "value": "9"},
                              {"label": "Киноведение", "value": "2002735"}
                            ]
                          },
                          "pserviceOrderCounts": [
                            {"pserviceId": "1010080", "count": 8},
                            {"pserviceId": "1010081", "count": 3},
                            {"pserviceId": "2000561", "count": 2},
                            {"pserviceId": "9", "count": 20},
                            {"pserviceId": "2002735", "count": 0}
                          ]
                        }
                      ]
                    }
                  }
                }
              }
            }
            </script>
            """,
        )
    )

    urls = _discover_pservice_source_urls(source, config)

    assert urls == [
        "https://profi.ru/rabota/repetitor/istoriya/?pserviceIds=1010080",
        "https://profi.ru/rabota/repetitor/istoriya/?pserviceIds=1010081",
    ]


@respx.mock
def test_expand_sources_includes_pservice_sources() -> None:
    source = SourceConfig(name="history", url="https://profi.ru/rabota/repetitor/istoriya/")
    config = AppConfig(
        sources=[source],
        fetch=FetchConfig(
            discover_pservice_sources=True,
            max_pservice_sources=1,
            pservice_include_keywords=["истори"],
        ),
    )
    respx.get("https://profi.ru/rabota/repetitor/istoriya/").mock(
        return_value=Response(
            200,
            text="""
            <script id="__NEXT_DATA__" type="application/json">
            {
              "props": {
                "pageProps": {
                  "legoData": {
                    "legoLandingData": {
                      "blocks": [
                        {
                          "filterOptions": {
                            "pservices": [
                              {"label": "ЕГЭ по истории", "value": "1010080"}
                            ]
                          },
                          "pserviceOrderCounts": [
                            {"pserviceId": "1010080", "count": 8}
                          ]
                        }
                      ]
                    }
                  }
                }
              }
            }
            </script>
            """,
        )
    )

    sources = _expand_sources(config)

    assert [source.name for source in sources] == ["history", "pservice-2"]
    assert str(sources[1].url) == "https://profi.ru/rabota/repetitor/istoriya/?pserviceIds=1010080"


def test_paginated_source_urls_preserve_existing_query() -> None:
    config = AppConfig(
        sources=[SourceConfig(name="history", url="https://profi.ru/rabota/repetitor/istoriya/")],
        fetch=FetchConfig(discover_paginated_sources=True, max_pages_per_source=3),
    )

    urls = _paginated_source_urls("https://profi.ru/rabota/repetitor/istoriya/?pserviceIds=1010080", config)

    assert urls == [
        "https://profi.ru/rabota/repetitor/istoriya/?page=2&pserviceIds=1010080",
        "https://profi.ru/rabota/repetitor/istoriya/?page=3&pserviceIds=1010080",
    ]


@respx.mock
def test_expand_sources_includes_paginated_sources() -> None:
    source = SourceConfig(name="history", url="https://profi.ru/rabota/repetitor/istoriya/")
    config = AppConfig(
        sources=[source],
        fetch=FetchConfig(
            discover_paginated_sources=True,
            max_pages_per_source=3,
        ),
    )

    sources = _expand_sources(config)

    assert [source.name for source in sources] == ["history", "page-2", "page-3"]
    assert str(sources[1].url) == "https://profi.ru/rabota/repetitor/istoriya/?page=2"
    assert str(sources[2].url) == "https://profi.ru/rabota/repetitor/istoriya/?page=3"
