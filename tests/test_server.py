from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

import pytest

from miro_mcp.schemas import ListBoardsRequest, ListBoardsResponse
from miro_mcp.server import create_server

if TYPE_CHECKING:
    from collections.abc import Mapping


class DummyContext:
    def __init__(self) -> None:
        self.messages: list[str] = []
        self.errors: list[str] = []

    async def info(
        self,
        message: str,
        _logger_name: str | None = None,
        _extra: Mapping[str, object] | None = None,
    ) -> None:
        self.messages.append(message)

    async def error(
        self,
        message: str,
        _logger_name: str | None = None,
        _extra: Mapping[str, object] | None = None,
    ) -> None:
        self.errors.append(message)

    async def warning(
        self,
        message: str,
        _logger_name: str | None = None,
        _extra: Mapping[str, object] | None = None,
    ) -> None:
        self.messages.append(message)


class FakeService:
    def __init__(self) -> None:
        self.list_boards_calls: list[ListBoardsRequest] = []
        self.response = ListBoardsResponse(boards=[], next_cursor=None)

    async def list_boards(
        self, request: ListBoardsRequest, _ctx: DummyContext
    ) -> ListBoardsResponse:
        self.list_boards_calls.append(request)
        return self.response

    async def get_board_items(self, *args: object, **kwargs: object) -> object:  # pragma: no cover
        raise NotImplementedError

    async def get_item(self, *args: object, **kwargs: object) -> object:  # pragma: no cover
        raise NotImplementedError

    async def create_item(self, *args: object, **kwargs: object) -> object:  # pragma: no cover
        raise NotImplementedError

    async def update_item(self, *args: object, **kwargs: object) -> object:  # pragma: no cover
        raise NotImplementedError

    async def delete_item(self, *args: object, **kwargs: object) -> object:  # pragma: no cover
        raise NotImplementedError


@pytest.mark.asyncio
async def test_create_server_registers_expected_tools() -> None:
    fake_service = cast("Any", FakeService())
    server = create_server(service=fake_service)

    tools = await server.get_tools()
    names = set(tools)
    assert {
        "list_boards",
        "get_board_items",
        "get_item",
        "create_item",
        "update_item",
        "delete_item",
    }.issubset(names)


@pytest.mark.asyncio
async def test_list_boards_tool_invokes_service() -> None:
    fake_service = cast("Any", FakeService())
    fake_service.response = ListBoardsResponse(boards=[], next_cursor="token")
    server = create_server(service=fake_service)

    tool = await server.get_tool("list_boards")
    ctx = DummyContext()
    result = await cast("Any", tool).fn(ListBoardsRequest(limit=5), ctx)

    assert isinstance(result, ListBoardsResponse)
    assert fake_service.list_boards_calls
    assert fake_service.list_boards_calls[0].limit == 5
