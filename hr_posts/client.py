from __future__ import annotations

from typing import Any

import httpx

from hr_posts.config import Settings


class ConnectSafelyError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def build_search_keywords(job_role: str) -> str:
    role = " ".join(job_role.split())
    if not role:
        raise ConnectSafelyError("invalid_job_role", "A job role is required.")
    return f"{role} hiring"


class ConnectSafelyClient:
    def __init__(self, settings: Settings, client: httpx.Client | None = None) -> None:
        self._settings = settings
        self._owns_client = client is None
        self._client = client or httpx.Client(
            base_url=settings.base_url,
            timeout=settings.timeout_seconds,
            headers={
                "Authorization": f"Bearer {settings.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def search_posts(
        self,
        *,
        account_id: str,
        keywords: str,
        count: int,
        start: int,
        date_posted: str = "past-24h",
        sort_by: str = "date_posted",
        exact_search: bool = False,
    ) -> dict[str, Any]:
        try:
            response = self._client.post(
                "/linkedin/posts/search",
                json={
                    "accountId": account_id,
                    "keywords": keywords,
                    "count": count,
                    "start": start,
                    "datePosted": date_posted,
                    "sortBy": sort_by,
                    "exactSearch": exact_search,
                },
            )
        except httpx.HTTPError as exc:
            raise ConnectSafelyError(
                "provider_unavailable",
                "The ConnectSafely request failed.",
            ) from exc
        return _checked_payload(response, failure="ConnectSafely search failed.")

    def get_feed(
        self,
        *,
        account_id: str,
        count: int = 20,
        sort_order: str,
    ) -> dict[str, Any]:
        try:
            response = self._client.post(
                "/linkedin/feed",
                json={
                    "accountId": account_id,
                    "count": count,
                    "start": 0,
                    "sortOrder": sort_order,
                },
            )
        except httpx.HTTPError as exc:
            raise ConnectSafelyError(
                "provider_unavailable",
                "The ConnectSafely request failed.",
            ) from exc
        return _checked_payload(response, failure="ConnectSafely feed failed.")


def _checked_payload(response: httpx.Response, *, failure: str) -> dict[str, Any]:
    if response.status_code == 401:
        raise ConnectSafelyError("unauthorized", "ConnectSafely rejected the API key.")
    if response.status_code == 404:
        raise ConnectSafelyError(
            "account_not_found",
            "No LinkedIn account was found for the given account ID.",
        )
    if response.status_code >= 400:
        raise ConnectSafelyError("provider_error", _safe_error_message(response))

    try:
        payload = response.json()
    except ValueError as exc:
        raise ConnectSafelyError(
            "invalid_response",
            "ConnectSafely returned a non-JSON response.",
        ) from exc

    if not isinstance(payload, dict):
        raise ConnectSafelyError(
            "invalid_response",
            "ConnectSafely returned an unexpected payload.",
        )
    if payload.get("success") is False:
        raise ConnectSafelyError("provider_error", str(payload.get("message") or failure))
    return payload


def _safe_error_message(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return f"ConnectSafely returned HTTP {response.status_code}."
    if isinstance(payload, dict):
        for key in ("message", "error", "details"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value
    return f"ConnectSafely returned HTTP {response.status_code}."
