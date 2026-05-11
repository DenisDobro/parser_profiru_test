from profiru_orders_watcher.fetchers.public_html import _extract_order_from_card, _order_identity
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
    assert _order_identity(order) == "history:order:89292166"


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
