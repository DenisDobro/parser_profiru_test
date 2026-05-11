import httpx

from profiru_orders_watcher.notifiers.telegram import _retry_after_seconds


def test_retry_after_seconds_reads_telegram_parameter() -> None:
    response = httpx.Response(
        429,
        json={"ok": False, "parameters": {"retry_after": 7}},
        request=httpx.Request("POST", "https://api.telegram.org/botREDACTED/sendMessage"),
    )

    assert _retry_after_seconds(response) == 8


def test_retry_after_seconds_defaults_for_invalid_payload() -> None:
    response = httpx.Response(
        429,
        content=b"not json",
        request=httpx.Request("POST", "https://api.telegram.org/botREDACTED/sendMessage"),
    )

    assert _retry_after_seconds(response) == 5
