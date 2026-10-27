from __future__ import annotations

import httpx
import pytest

from hr_posts.client import ConnectSafelyClient, ConnectSafelyError
from hr_posts.config import Settings


def settings() -> Settings:
    return Settings(api_key="test-key", base_url="https://api.connectsafely.ai")


def client_for(handler: httpx.MockTransport) -> ConnectSafelyClient:
    http_client = httpx.Client(
        transport=handler,
        base_url="https://api.connectsafely.ai",
        headers={"Authorization": "Bearer test-key"},
    )
    return ConnectSafelyClient(settings(), client=http_client)


def test_search_posts_sends_expected_payload() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["json"] = request.read().decode("utf-8")
        return httpx.Response(
            200,
            json={"success": True, "posts": [{"text": "We are hiring"}]},
        )

    service = client_for(httpx.MockTransport(handler))
    payload = service.search_posts(
        account_id="acc_12345",
        keywords="AI Engineer hiring",
        count=20,
        start=0,
    )

    assert payload["success"] is True
    assert captured["url"] == "https://api.connectsafely.ai/linkedin/posts/search"
    body = str(captured["json"])
    assert '"accountId":"acc_12345"' in body
    assert '"datePosted":"past-24h"' in body
    assert '"exactSearch":false' in body


def test_get_feed_requests_recent_and_relevance_sorts() -> None:
    captured: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append((str(request.url), request.read().decode("utf-8")))
        return httpx.Response(200, json={"success": True, "posts": []})

    service = client_for(httpx.MockTransport(handler))
    service.get_feed(account_id="acc_12345", count=20, sort_order="recent")
    service.get_feed(account_id="acc_12345", count=20, sort_order="relevance")

    assert captured[0][0] == "https://api.connectsafely.ai/linkedin/feed"
    assert '"accountId":"acc_12345"' in captured[0][1]
    assert '"count":20' in captured[0][1]
    assert '"sortOrder":"recent"' in captured[0][1]
    assert '"sortOrder":"relevance"' in captured[1][1]


def test_missing_account_is_mapped() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": "No LinkedIn account found"})

    service = client_for(httpx.MockTransport(handler))
    with pytest.raises(ConnectSafelyError, match="account ID"):
        service.search_posts(
            account_id="missing",
            keywords="AI Engineer hiring",
            count=10,
            start=0,
        )


def test_provider_error_is_mapped() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"message": "upstream failed"})

    service = client_for(httpx.MockTransport(handler))
    with pytest.raises(ConnectSafelyError, match="upstream failed"):
        service.search_posts(
            account_id="acc_12345",
            keywords="AI Engineer hiring",
            count=10,
            start=0,
        )
