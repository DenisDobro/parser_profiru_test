from profiru_orders_watcher.fetchers.backoffice_selenium import (
    is_fresh_backoffice_order,
    parse_backoffice_orders,
)
from profiru_orders_watcher.models import SourceConfig


def test_parse_backoffice_order() -> None:
    source = SourceConfig(
        name="backoffice",
        kind="backoffice_selenium",
        url="https://profi.ru/backoffice/n.php",
    )
    html = """
    <div class="OrderSnippetContainerStyles__Container-sc-1qf4h1o-0">
      <a id="123456"></a>
      <div class="SubjectAndPriceStyles__SubjectsText-sc-18v5hu8-1">Telegram bot</div>
      <div class="SnippetBodyStyles__MainInfo-sc-tnih0-6">Нужно сделать парсер заказов</div>
      <div class="SubjectAndPriceStyles__PriceValue-sc-18v5hu8-5">15 000 ₽</div>
      <div class="Date__DateText-sc-e1f8oi-1">5 минут назад</div>
    </div>
    """

    orders = parse_backoffice_orders(html, source)

    assert len(orders) == 1
    assert orders[0].title == "Telegram bot"
    assert orders[0].price == 15000
    assert orders[0].response_url == "https://profi.ru/backoffice/n.php?o=123456"
    assert orders[0].raw["time_info"] == "5 минут назад"


def test_old_backoffice_order_is_not_fresh() -> None:
    source = SourceConfig(
        name="backoffice",
        kind="backoffice_selenium",
        url="https://profi.ru/backoffice/n.php",
    )
    order = parse_backoffice_orders(
        """
        <div class="OrderSnippetContainerStyles__Container-sc-1qf4h1o-0">
          <a id="123456"></a>
          <div class="SubjectAndPriceStyles__SubjectsText-sc-18v5hu8-1">API</div>
          <div class="Date__DateText-sc-e1f8oi-1">2 часа назад</div>
        </div>
        """,
        source,
    )[0]

    assert not is_fresh_backoffice_order(order)
