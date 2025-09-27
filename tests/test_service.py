from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

import pytest
from fastmcp.exceptions import ToolError

from miro_mcp.client import MiroClientProtocol
from miro_mcp.exceptions import MiroAPIError
from miro_mcp.schemas import (
    CreateItemRequest,
    DeleteItemRequest,
    GetBoardItemsRequest,
    GetItemRequest,
    ListBoardsRequest,
    ShapeItem,
    ShapeItemUpdate,
    StickyNoteItem,
    TextItemCreate,
    UpdateItemRequest,
)
from miro_mcp.service import MiroService

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Mapping


class FakeClient(MiroClientProtocol):
    def __init__(self) -> None:
        self.list_boards_response: dict[str, Any] = {"data": []}
        self.board_items_response: dict[str, Any] = {"data": []}
        self.item_response: dict[str, Any] = {}
        self.create_item_response: dict[str, Any] = {}
        self.update_item_response: dict[str, Any] = {}
        self.raise_exc: Exception | None = None
        self.create_calls: list[tuple[str, dict[str, Any]]] = []
        self.update_calls: list[tuple[str, str, dict[str, Any]]] = []
        self.delete_calls: list[tuple[str, str, bool]] = []
        self.list_calls: list[tuple[int, str | None]] = []
        self.board_item_calls: list[tuple[str, int, str | None]] = []
        self.get_item_calls: list[tuple[str, str]] = []

    async def list_boards(self, *, limit: int, cursor: str | None) -> dict[str, Any]:
        self._maybe_raise()
        self.list_calls.append((limit, cursor))
        return self.list_boards_response

    async def get_board_items(
        self, board_id: str, *, limit: int, cursor: str | None
    ) -> dict[str, Any]:
        self._maybe_raise()
        self.board_item_calls.append((board_id, limit, cursor))
        return self.board_items_response

    async def get_item(self, board_id: str, item_id: str) -> dict[str, Any]:
        self._maybe_raise()
        self.get_item_calls.append((board_id, item_id))
        return self.item_response

    async def create_item(self, board_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        self._maybe_raise()
        self.create_calls.append((board_id, dict(payload)))
        return self.create_item_response

    async def update_item(
        self, board_id: str, item_id: str, payload: Mapping[str, Any]
    ) -> dict[str, Any]:
        self._maybe_raise()
        self.update_calls.append((board_id, item_id, dict(payload)))
        return self.update_item_response

    async def delete_item(self, board_id: str, item_id: str, *, permanent: bool) -> None:
        self._maybe_raise()
        self.delete_calls.append((board_id, item_id, permanent))

    def _maybe_raise(self) -> None:
        if self.raise_exc is not None:
            raise self.raise_exc


def build_service(client: FakeClient) -> MiroService:
    logger = logging.getLogger("tests.miro-service")

    @asynccontextmanager
    async def factory() -> AsyncIterator[MiroClientProtocol]:
        yield client

    return MiroService(
        client_factory=lambda: factory(),
        logger=logger,
        default_list_limit=50,
    )


@pytest.mark.asyncio
async def test_list_boards_parses_metadata() -> None:
    client = FakeClient()
    client.list_boards_response = {
        "data": [
            {
                "id": "b1",
                "name": "Discovery",
                "description": "Team board",
                "createdAt": "2024-03-01T12:00:00Z",
                "modifiedAt": "2024-03-02T15:30:00Z",
                "owner": {"id": "u1", "name": "Pat", "type": "user"},
                "currentUserAccessLevel": "editor",
            }
        ],
        "cursor": {"next": "cursor-token"},
    }
    service = build_service(client)

    response = await service.list_boards(ListBoardsRequest(limit=25))

    assert response.next_cursor == "cursor-token"
    assert len(response.boards) == 1
    board = response.boards[0]
    assert board.id == "b1"
    assert board.title == "Discovery"
    assert board.owner is not None
    assert board.owner.id == "u1"
    assert board.access_level == "editor"


@pytest.mark.asyncio
async def test_get_board_items_filters_supported_types() -> None:
    client = FakeClient()
    client.board_items_response = {
        "data": [
            {
                "id": "text-1",
                "type": "text",
                "data": {"content": "Hello"},
                "createdAt": "2024-05-01T11:00:00Z",
            },
            {
                "id": "shape-1",
                "type": "shape",
                "data": {"content": "<p>Box</p>", "shape": {"type": "rectangle"}},
            },
            {
                "id": "image-1",
                "type": "image",
                "data": {},
            },
        ],
    }
    service = build_service(client)

    response = await service.get_board_items(GetBoardItemsRequest(board_id="b1", limit=10))

    assert len(response.items) == 2
    types = {item.type for item in response.items}
    assert types == {"text", "shape"}


@pytest.mark.asyncio
async def test_get_item_returns_typed_model() -> None:
    client = FakeClient()
    client.item_response = {
        "id": "sticky-1",
        "type": "sticky_note",
        "data": {"content": "Reminder", "shape": "square", "format": "note"},
    }
    service = build_service(client)

    item = await service.get_item(GetItemRequest(board_id="b1", item_id="sticky-1"))

    assert item.type == "sticky_note"
    assert item.content == "Reminder"
    assert isinstance(item, StickyNoteItem)
    assert item.shape == "square"


@pytest.mark.asyncio
async def test_create_item_sends_expected_payload() -> None:
    client = FakeClient()
    client.create_item_response = {
        "id": "text-2",
        "type": "text",
        "data": {"content": "Hello"},
    }
    service = build_service(client)

    request = CreateItemRequest(
        board_id="b1",
        item=TextItemCreate(content="Hello"),
    )

    response = await service.create_item(request)

    assert response.item.id == "text-2"
    assert client.create_calls == [
        (
            "b1",
            {
                "data": {"content": "Hello"},
            },
        )
    ]


@pytest.mark.asyncio
async def test_update_item_records_payload() -> None:
    client = FakeClient()
    client.update_item_response = {
        "id": "shape-9",
        "type": "shape",
        "data": {"content": "Updated", "shape": {"type": "triangle"}},
    }
    service = build_service(client)

    request = UpdateItemRequest(
        board_id="b1",
        item_id="shape-9",
        item=ShapeItemUpdate(content="Updated", shape="triangle"),
    )

    result = await service.update_item(request)

    assert result.item.type == "shape"
    assert client.update_calls == [
        (
            "b1",
            "shape-9",
            {"data": {"content": "Updated", "shape": {"type": "triangle"}}},
        )
    ]
    assert isinstance(result.item, ShapeItem)
    assert result.item.shape == "triangle"


@pytest.mark.asyncio
async def test_delete_item_passes_permanent_flag() -> None:
    client = FakeClient()
    service = build_service(client)

    await service.delete_item(DeleteItemRequest(board_id="b1", item_id="i1", hard_delete=True))

    assert client.delete_calls == [("b1", "i1", True)]


@pytest.mark.asyncio
async def test_error_translates_to_tool_error() -> None:
    client = FakeClient()
    client.raise_exc = MiroAPIError(status_code=429, message="Slow down", retry_after=2.0)
    service = build_service(client)

    with pytest.raises(ToolError) as exc:
        await service.list_boards(ListBoardsRequest())

    assert "rate limit" in exc.value.args[0].lower()
    assert "2" in exc.value.args[0]
