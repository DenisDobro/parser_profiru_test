from profiru_orders_watcher.filters import is_relevant
from profiru_orders_watcher.models import FilterConfig, Order


def test_include_keyword_matches_title() -> None:
    order = Order(source="test", title="Нужна интеграция API", url="https://example.com")
    config = FilterConfig(include_keywords=["api"])
    assert is_relevant(order, config)


def test_exclude_keyword_blocks_order() -> None:
    order = Order(source="test", title="Нужен бот бесплатно", url="https://example.com")
    config = FilterConfig(include_keywords=["бот"], exclude_keywords=["бесплатно"])
    assert not is_relevant(order, config)


def test_min_price_blocks_low_budget() -> None:
    order = Order(source="test", title="API", url="https://example.com", price=1000)
    config = FilterConfig(include_keywords=["api"], min_price=3000)
    assert not is_relevant(order, config)
