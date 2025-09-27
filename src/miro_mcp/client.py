"""HTTP client wrapper around the Miro REST API."""

from __future__ import annotations

import contextlib
import json
from typing import TYPE_CHECKING, Any, Protocol, Self, cast

import httpx

from .exceptions import MiroAPIError

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Mapping
    from types import TracebackType

JsonDict = dict[str, Any]
HTTP_ERROR_STATUS = 400


class MiroClientProtocol(Protocol):
    """Interface implemented by Miro API clients."""

    async def list_boards(self, *, limit: int, cursor: str | None) -> JsonDict:
        """Return metadata for boards visible to the authenticated user."""

    async def get_board_items(self, board_id: str, *, limit: int, cursor: str | None) -> JsonDict:
        """Return raw Miro payloads for items on a board."""

    async def get_item(self, board_id: str, item_id: str) -> JsonDict:
        """Return the raw payload for a single board item."""

    async def create_item(self, board_id: str, payload: Mapping[str, Any]) -> JsonDict:
        """Create a new board item and return the resulting payload."""

    async def update_item(
        self, board_id: str, item_id: str, payload: Mapping[str, Any]
    ) -> JsonDict:
        """Update an existing board item and return the resulting payload."""

    async def delete_item(self, board_id: str, item_id: str, *, permanent: bool) -> None:
        """Delete or archive an item depending on the `permanent` flag."""


class HttpMiroClient:
    """Asynchronous HTTPX-backed Miro API client."""

    def __init__(
        self,
        *,
        token: str,
        base_url: str,
        timeout_seconds: float,
        user_agent: str,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """Store configuration values for subsequent requests."""
        self._token = token
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds
        self._user_agent = user_agent
        self._transport = transport
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> Self:
        """Create the underlying HTTPX client when entering the context manager."""
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=self._timeout,
            headers={
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/json",
                "User-Agent": self._user_agent,
            },
            transport=self._transport,
        )
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Close the HTTPX client when leaving the context manager."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def list_boards(self, *, limit: int, cursor: str | None) -> JsonDict:
        """List boards accessible to the configured token."""
        params: dict[str, Any] = {"limit": limit}
        if cursor:
            params["cursor"] = cursor
        return await self._request("GET", "/boards", params=params)

    async def get_board_items(self, board_id: str, *, limit: int, cursor: str | None) -> JsonDict:
        """List items for a specific board."""
        params: dict[str, Any] = {"limit": limit}
        if cursor:
            params["cursor"] = cursor
        path = f"/boards/{board_id}/items"
        return await self._request("GET", path, params=params)

    async def get_item(self, board_id: str, item_id: str) -> JsonDict:
        """Retrieve a single item."""
        path = f"/boards/{board_id}/items/{item_id}"
        return await self._request("GET", path)

    async def create_item(self, board_id: str, payload: Mapping[str, Any]) -> JsonDict:
        """Create a new item."""
        path = f"/boards/{board_id}/items"
        return await self._request("POST", path, json_payload=dict(payload))

    async def update_item(
        self, board_id: str, item_id: str, payload: Mapping[str, Any]
    ) -> JsonDict:
        """Update an existing item."""
        path = f"/boards/{board_id}/items/{item_id}"
        return await self._request("PATCH", path, json_payload=dict(payload))

    async def delete_item(self, board_id: str, item_id: str, *, permanent: bool) -> None:
        """Delete (or archive) an item."""
        path = f"/boards/{board_id}/items/{item_id}"
        params = {"permanent": json.dumps(permanent)}
        await self._request("DELETE", path, params=params)

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        json_payload: Mapping[str, Any] | None = None,
    ) -> JsonDict:
        """Perform an HTTP request and translate errors into :class:`MiroAPIError`."""
        if self._client is None:  # pragma: no cover - defensive guard
            msg = "Client is not initialized; use 'async with HttpMiroClient(...)'."
            raise RuntimeError(msg)

        request_data: dict[str, Any] = {}
        if params:
            request_data["params"] = params
        if json_payload:
            request_data["json"] = json_payload

        try:
            response = await self._client.request(method, path, **request_data)
        except httpx.TimeoutException as exc:
            raise MiroAPIError(
                status_code=408,
                message="Timed out while contacting the Miro API",
                code="timeout",
            ) from exc
        except httpx.HTTPError as exc:
            raise MiroAPIError(status_code=500, message=str(exc), code="transport_error") from exc

        if response.status_code >= HTTP_ERROR_STATUS:
            raise MiroAPIError.from_response(response)

        if response.status_code == httpx.codes.NO_CONTENT or not response.content:
            return {}

        with contextlib.suppress(ValueError):
            return cast("JsonDict", response.json())

        return {"raw": response.text}


def create_http_client(
    *,
    token: str,
    base_url: str,
    timeout_seconds: float,
    user_agent: str,
    transport: httpx.AsyncBaseTransport | None = None,
) -> contextlib.AbstractAsyncContextManager[MiroClientProtocol]:
    """Return an async context manager yielding an :class:`HttpMiroClient`."""

    @contextlib.asynccontextmanager
    async def manager() -> AsyncIterator[MiroClientProtocol]:
        async with HttpMiroClient(
            token=token,
            base_url=base_url,
            timeout_seconds=timeout_seconds,
            user_agent=user_agent,
            transport=transport,
        ) as instance:
            yield instance

    return manager()
