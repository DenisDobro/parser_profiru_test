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


def test_history_art_order_is_blocked_by_exclude_keywords() -> None:
    order = Order(
        source="test",
        title="Подготовка к экзамену в вузе",
        url="https://profi.ru/backoffice/n.php?o=89301484",
        description="Подготовка к вступительным экзаменам на факультет истории искусств.",
    )
    config = FilterConfig(
        include_keywords=["история"],
        exclude_keywords=["история искусств", "искусств", "архитектур"],
    )

    assert not is_relevant(order, config)


def test_ballet_history_order_is_blocked_by_exclude_keywords() -> None:
    order = Order(
        source="test",
        title="Для учеников балетной школы",
        url="https://profi.ru/backoffice/n.php?o=89088948",
        description="Провести цикл лекций: история классического балета, развитие балетного искусства.",
    )
    config = FilterConfig(
        include_keywords=["история"],
        exclude_keywords=["балет", "искусств"],
    )

    assert not is_relevant(order, config)
