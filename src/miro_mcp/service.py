"""Domain logic for interacting with the Miro API."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Mapping
from contextlib import AbstractAsyncContextManager
from typing import TYPE_CHECKING, Any

from fastmcp.exceptions import ToolError

from .client import MiroClientProtocol, create_http_client
from .exceptions import MiroAPIError
from .logging_utils import format_log

if TYPE_CHECKING:
    import httpx
    from fastmcp.server.context import Context

    from .settings import Settings

from .schemas import (
    SUPPORTED_ITEM_TYPES,
    BoardItem,
    BoardSummary,
    CreateItemRequest,
    CreateItemResponse,
    DeleteItemRequest,
    DeleteItemResponse,
    GetBoardItemsRequest,
    GetBoardItemsResponse,
    GetItemRequest,
    ItemCreateBase,
    ItemCreatePayload,
    ItemPosition,
    ItemUpdatePayload,
    ListBoardsRequest,
    ListBoardsResponse,
    ShapeItemCreate,
    ShapeItemUpdate,
    StickyNoteItemCreate,
    StickyNoteItemUpdate,
    TextItemCreate,
    TextItemUpdate,
    UpdateItemRequest,
    UpdateItemResponse,
    parse_item,
)

HTTP_STATUS_BAD_REQUEST = 400
HTTP_STATUS_UNAUTHORIZED = 401
HTTP_STATUS_FORBIDDEN = 403
HTTP_STATUS_NOT_FOUND = 404
HTTP_STATUS_RATE_LIMIT = 429
HTTP_STATUS_SERVER_ERROR = 500
ClientFactory = Callable[[], AbstractAsyncContextManager[MiroClientProtocol]]


class MiroService:
    """Encapsulates business logic for Miro board automation."""

    def __init__(
        self,
        *,
        client_factory: ClientFactory,
        logger: logging.Logger,
        default_list_limit: int,
        supported_item_types: set[str] | None = None,
    ) -> None:
        """Initialise the service with dependencies and defaults."""
        self._client_factory = client_factory
        self._logger = logger
        self._default_list_limit = default_list_limit
        self._supported_item_types = supported_item_types or set(SUPPORTED_ITEM_TYPES)

    @classmethod
    def from_settings(
        cls,
        settings: Settings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        logger: logging.Logger | None = None,
    ) -> MiroService:
        """Construct a service from application settings."""
        token = settings.require_token().get_secret_value()

        def factory() -> AbstractAsyncContextManager[MiroClientProtocol]:
            return create_http_client(
                token=token,
                base_url=settings.api_base_url,
                timeout_seconds=settings.request_timeout_seconds,
                user_agent=settings.user_agent,
                transport=transport,
            )

        effective_logger = logger or logging.getLogger("miro_mcp.service")
        return cls(
            client_factory=factory,
            logger=effective_logger,
            default_list_limit=settings.default_page_size,
        )

    async def list_boards(
        self, request: ListBoardsRequest, ctx: Context | None = None
    ) -> ListBoardsResponse:
        """Return boards available to the configured credentials."""
        limit = request.limit or self._default_list_limit
        payload = await self._execute(
            "list_boards",
            lambda client: client.list_boards(limit=limit, cursor=request.cursor),
            ctx,
            cursor=request.cursor,
            limit=limit,
        )
        boards_payload = self._extract_sequence(payload)
        boards = [
            board for board in (_to_board_summary(entry) for entry in boards_payload) if board
        ]
        next_cursor = _extract_cursor(payload)
        await self._log_success("list_boards", ctx, count=len(boards), next_cursor=next_cursor)
        return ListBoardsResponse(boards=boards, next_cursor=next_cursor)

    async def get_board_items(
        self, request: GetBoardItemsRequest, ctx: Context | None = None
    ) -> GetBoardItemsResponse:
        """Fetch supported items from a specific board."""
        limit = request.limit or self._default_list_limit
        payload = await self._execute(
            "get_board_items",
            lambda client: client.get_board_items(
                request.board_id,
                limit=limit,
                cursor=request.cursor,
            ),
            ctx,
            board_id=request.board_id,
            limit=limit,
            cursor=request.cursor,
        )
        items_payload = self._extract_sequence(payload)
        items = [
            item
            for entry in items_payload
            for item in [
                _parse_supported_item(
                    entry, board_id=request.board_id, allowed=self._supported_item_types
                )
            ]
            if item is not None
        ]
        next_cursor = _extract_cursor(payload)
        await self._log_success(
            "get_board_items",
            ctx,
            board_id=request.board_id,
            count=len(items),
            next_cursor=next_cursor,
        )
        return GetBoardItemsResponse(items=items, next_cursor=next_cursor)

    async def get_item(self, request: GetItemRequest, ctx: Context | None = None) -> BoardItem:
        """Return a single supported item from the specified board."""
        payload = await self._execute(
            "get_item",
            lambda client: client.get_item(request.board_id, request.item_id),
            ctx,
            board_id=request.board_id,
            item_id=request.item_id,
        )
        if not isinstance(payload, Mapping):
            message = "Unexpected response from Miro when fetching an item."
            raise ToolError(message)
        item = parse_item(payload, board_id=request.board_id)
        if item is None:
            message = "The requested item type is not supported by this server."
            raise ToolError(message)
        await self._log_success(
            "get_item",
            ctx,
            board_id=request.board_id,
            item_id=request.item_id,
            item_type=item.type,
        )
        return item

    async def create_item(
        self, request: CreateItemRequest, ctx: Context | None = None
    ) -> CreateItemResponse:
        """Create an item on the requested board."""
        self._ensure_supported(request.item.type)
        payload = _build_create_payload(request.item)
        response_data = await self._execute(
            "create_item",
            lambda client: client.create_item(request.board_id, payload),
            ctx,
            board_id=request.board_id,
            item_type=request.item.type,
        )
        item = _coerce_item_from_payload(response_data, request.board_id)
        await self._log_success(
            "create_item",
            ctx,
            board_id=request.board_id,
            item_type=item.type,
            item_id=item.id,
        )
        return CreateItemResponse(item=item)

    async def update_item(
        self, request: UpdateItemRequest, ctx: Context | None = None
    ) -> UpdateItemResponse:
        """Apply updates to an existing item."""
        self._ensure_supported(request.item.type)
        payload = _build_update_payload(request.item)
        response_data = await self._execute(
            "update_item",
            lambda client: client.update_item(request.board_id, request.item_id, payload),
            ctx,
            board_id=request.board_id,
            item_id=request.item_id,
            item_type=request.item.type,
        )
        item = _coerce_item_from_payload(response_data, request.board_id)
        await self._log_success(
            "update_item",
            ctx,
            board_id=request.board_id,
            item_type=item.type,
            item_id=item.id,
        )
        return UpdateItemResponse(item=item)

    async def delete_item(
        self, request: DeleteItemRequest, ctx: Context | None = None
    ) -> DeleteItemResponse:
        """Delete or archive an item depending on the request."""
        await self._execute(
            "delete_item",
            lambda client: client.delete_item(
                request.board_id, request.item_id, permanent=request.hard_delete
            ),
            ctx,
            board_id=request.board_id,
            item_id=request.item_id,
            hard_delete=request.hard_delete,
        )
        await self._log_success(
            "delete_item",
            ctx,
            board_id=request.board_id,
            item_id=request.item_id,
            hard_delete=request.hard_delete,
        )
        return DeleteItemResponse(ok=True)

    async def _execute(
        self,
        operation: str,
        action: Callable[[MiroClientProtocol], Awaitable[Any]],
        ctx: Context | None,
        **details: Any,
    ) -> Any:
        """Execute a client action and translate errors."""
        message = format_log(f"miro.{operation}.request", **details)
        self._logger.info(message)
        if ctx is not None:
            await ctx.info(message)

        try:
            async with self._client_factory() as client:
                return await action(client)
        except MiroAPIError as error:
            error_message = self._format_error(operation, error)
            self._logger.exception(
                format_log(error_message, status_code=error.status_code, code=error.code)
            )
            if ctx is not None:
                await ctx.error(error_message)
            raise ToolError(error_message) from error

    async def _log_success(self, operation: str, ctx: Context | None, **details: Any) -> None:
        message = format_log(f"miro.{operation}.success", **details)
        self._logger.info(message)
        if ctx is not None:
            await ctx.info(message)

    def _format_error(self, operation: str, error: MiroAPIError) -> str:
        """Map HTTP errors to human readable messages."""
        base = f"{operation.replace('_', ' ').title()} failed: {error.message}"
        if error.status_code == HTTP_STATUS_UNAUTHORIZED:
            base = "Authentication with Miro failed. Check that the personal access token is valid."
        elif error.status_code == HTTP_STATUS_FORBIDDEN:
            base = "The configured token does not have permission to perform this action."
        elif error.status_code == HTTP_STATUS_NOT_FOUND:
            base = "The requested board or item could not be found."
        elif error.status_code == HTTP_STATUS_RATE_LIMIT:
            base = "The Miro API rate limit was exceeded."
        elif HTTP_STATUS_BAD_REQUEST <= error.status_code < HTTP_STATUS_SERVER_ERROR:
            base = f"Miro rejected the request ({error.status_code})."
        elif error.status_code >= HTTP_STATUS_SERVER_ERROR:
            base = "Miro experienced an internal error."

        if error.retry_after is not None and error.retry_after > 0:
            base = f"{base} Retry after {int(error.retry_after)} seconds."
        return base

    def _extract_sequence(self, payload: Any) -> list[Mapping[str, Any]]:
        """Extract a list of item dictionaries from the payload."""
        if not isinstance(payload, Mapping):
            return []
        candidates = (
            payload.get("data"),
            payload.get("items"),
            payload.get("boards"),
        )
        for candidate in candidates:
            if isinstance(candidate, list):
                return [entry for entry in candidate if isinstance(entry, Mapping)]
        return []

    def _ensure_supported(self, item_type: str) -> None:
        """Ensure the item type is supported before making API calls."""
        if item_type not in self._supported_item_types:
            message = f"Item type '{item_type}' is not supported."
            raise ToolError(message)


def _to_board_summary(entry: Mapping[str, Any]) -> BoardSummary | None:
    try:
        return BoardSummary.from_api(entry)
    except (TypeError, ValueError):  # pragma: no cover - defensive fallback
        return None


def _extract_cursor(payload: Mapping[str, Any]) -> str | None:
    cursor_section = payload.get("cursor")
    if isinstance(cursor_section, Mapping):
        candidate = cursor_section.get("next") or cursor_section.get("nextCursor")
        if isinstance(candidate, str):
            return candidate
    candidate = payload.get("next") or payload.get("nextCursor")
    if isinstance(candidate, str):
        return candidate
    return None


def _parse_supported_item(
    entry: Mapping[str, Any],
    *,
    board_id: str,
    allowed: set[str],
) -> BoardItem | None:
    item = parse_item(entry, board_id=board_id)
    if item is None:
        return None
    if item.type not in allowed:
        return None
    return item


def _build_create_payload(item: ItemCreatePayload) -> Mapping[str, Any]:
    data_payload: dict[str, Any] = {}
    position = None
    style = None
    if isinstance(item, ItemCreateBase):
        position = _position_to_dict(item.position)
        style = dict(item.style) if item.style is not None else None

    if isinstance(item, TextItemCreate):
        data_payload["content"] = item.content
    elif isinstance(item, ShapeItemCreate):
        data_payload["shape"] = {"type": item.shape}
        if item.content is not None:
            data_payload["content"] = item.content
    elif isinstance(item, StickyNoteItemCreate):
        data_payload["content"] = item.content
        if item.shape is not None:
            data_payload["shape"] = item.shape
        if item.format is not None:
            data_payload["format"] = item.format
    else:  # pragma: no cover - discriminator guarantees subclass
        data_payload["content"] = getattr(item, "content", "")

    payload: dict[str, Any] = {"data": data_payload}
    if position:
        payload["position"] = position
    if style:
        payload["style"] = style
    return payload


def _build_update_payload(item: ItemUpdatePayload) -> Mapping[str, Any]:
    """Construct the update payload compatible with the Miro API."""
    position = _position_to_dict(item.position)
    style = dict(item.style) if item.style is not None else None
    data_payload = _build_update_data(item)

    payload: dict[str, Any] = {}
    if data_payload:
        payload["data"] = data_payload
    if position:
        payload["position"] = position
    if style:
        payload["style"] = style
    return payload


def _build_update_data(item: ItemUpdatePayload) -> dict[str, Any]:
    """Return type-specific update values for the payload."""
    if isinstance(item, TextItemUpdate):
        return _text_update_fields(item)
    if isinstance(item, ShapeItemUpdate):
        return _shape_update_fields(item)
    if isinstance(item, StickyNoteItemUpdate):
        return _sticky_note_update_fields(item)
    return {}


def _text_update_fields(item: TextItemUpdate) -> dict[str, Any]:
    data: dict[str, Any] = {}
    if item.content is not None:
        data["content"] = item.content
    return data


def _shape_update_fields(item: ShapeItemUpdate) -> dict[str, Any]:
    data: dict[str, Any] = {}
    if item.shape is not None:
        data["shape"] = {"type": item.shape}
    if item.content is not None:
        data["content"] = item.content
    return data


def _sticky_note_update_fields(item: StickyNoteItemUpdate) -> dict[str, Any]:
    data: dict[str, Any] = {}
    if item.content is not None:
        data["content"] = item.content
    if item.shape is not None:
        data["shape"] = item.shape
    if item.format is not None:
        data["format"] = item.format
    return data


def _position_to_dict(position: ItemPosition | None) -> dict[str, Any] | None:
    if position is None:
        return None
    data: dict[str, Any] = {}
    if position.x is not None:
        data["x"] = position.x
    if position.y is not None:
        data["y"] = position.y
    if position.width is not None:
        data["width"] = position.width
    if position.height is not None:
        data["height"] = position.height
    if position.rotation is not None:
        data["rotation"] = position.rotation
    return data or None


def _coerce_item_from_payload(payload: Any, board_id: str) -> BoardItem:
    if not isinstance(payload, Mapping):
        message = "Unexpected response payload from Miro."
        raise ToolError(message)
    item = parse_item(payload, board_id=board_id)
    if item is None:
        message = "Miro returned an item that is not supported."
        raise ToolError(message)
    return item
