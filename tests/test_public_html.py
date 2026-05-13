from profiru_orders_watcher.fetchers.public_html import (
    _extract_next_data_orders,
    _extract_order_from_card,
    _order_identity,
)
from profiru_orders_watcher.models import SourceConfig

from bs4 import BeautifulSoup


def test_public_card_requires_link() -> None:
    source = SourceConfig(name="history", url="https://profi.ru/rabota/repetitor/istoriya/")
    soup = BeautifulSoup("<article>Репетитор по истории нужен срочно</article>", "html.parser")

    assert _extract_order_from_card(soup.article, source) is None  # type: ignore[arg-type]


def test_public_order_identity_prefers_order_id() -> None:
    source = SourceConfig(name="history", url="https://profi.ru/rabota/repetitor/istoriya/")
    soup = BeautifulSoup(
        """
        <article>
          <a href="/backoffice/n.php?o=89292166">Репетитор по истории</a>
          <p>Подготовка к ВПР по истории</p>
          <p>1700 ₽</p>
        </article>
        """,
        "html.parser",
    )

    order = _extract_order_from_card(soup.article, source)  # type: ignore[arg-type]

    assert order is not None
    assert _order_identity(order) == "profi-order:89292166"


def test_order_fingerprint_deduplicates_same_profi_order_across_sources() -> None:
    source = SourceConfig(name="history", url="https://profi.ru/rabota/repetitor/istoriya/")
    other_source = SourceConfig(name="ege", url="https://profi.ru/rabota/repetitor/ege/")
    html = """
    <article>
      <a href="/backoffice/n.php?o=89292166">Репетитор по истории</a>
      <p>Подготовка к ВПР по истории</p>
    </article>
    """

    first = _extract_order_from_card(BeautifulSoup(html, "html.parser").article, source)  # type: ignore[arg-type]
    second = _extract_order_from_card(
        BeautifulSoup(html, "html.parser").article, other_source  # type: ignore[arg-type]
    )

    assert first is not None
    assert second is not None
    assert first.fingerprint == second.fingerprint


def test_extract_next_data_orders_from_current_orders() -> None:
    source = SourceConfig(name="history", url="https://profi.ru/rabota/repetitor/istoriya/")
    soup = BeautifulSoup(
        """
        <script id="__NEXT_DATA__" type="application/json">
        {
          "props": {
            "pageProps": {
              "legoData": {
                "legoLandingData": {
                  "blocks": [
                    {
                      "__typename": "LegoLandingRegistrationOrdersBlock",
                      "currentOrders": [
                        {
                          "id": "89292166",
                          "receivd": "Tue May 12 2026 10:20:30 GMT+0300 (MSK)",
                          "program": "11 класс.",
                          "aim": "ЕГЭ по истории",
                          "detailsPublic": "Нужна подготовка к ЕГЭ по истории.",
                          "wpriceMin": 1500,
                          "wpriceMax": 2200,
                          "city": {"gity": {"name": "Москва"}},
                          "pservices": [
                            {"id": "8", "name": "история"},
                            {"id": "1010080", "name": "ЕГЭ по истории"}
                          ]
                        }
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
        "html.parser",
    )

    orders = _extract_next_data_orders(soup, source)

    assert len(orders) == 1
    assert orders[0].title == "ЕГЭ по истории"
    assert orders[0].url == "https://profi.ru/backoffice/n.php?o=89292166"
    assert orders[0].description == "11 класс. ЕГЭ по истории Нужна подготовка к ЕГЭ по истории. история, ЕГЭ по истории"
    assert orders[0].city == "Москва"
    assert orders[0].price == 1500
    assert orders[0].raw_price == "1500-2200 ₽"
    assert _order_identity(orders[0]) == "profi-order:89292166"
