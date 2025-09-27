"""FastMCP server exposing tools for Miro board automation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastmcp import FastMCP

from . import __version__, schemas
from .logging_utils import configure_logging
from .service import MiroService
from .settings import Settings

if TYPE_CHECKING:
    from fastmcp.server.context import Context
else:
    Context = Any

_SERVER_NAME = "miro-mcp-server"
_SERVER_DESCRIPTION = (
    "Tools for listing Miro boards and managing text, shape, and sticky note items."
)


def create_server(
    *,
    settings: Settings | None = None,
    service: MiroService | None = None,
) -> FastMCP:
    """Create and configure the FastMCP server."""
    configure_logging()

    instance = FastMCP(name=_SERVER_NAME, instructions=_SERVER_DESCRIPTION, version=__version__)

    active_service = service
    if active_service is None:
        runtime_settings = settings or Settings()
        active_service = MiroService.from_settings(runtime_settings)

    @instance.tool(
        name="list_boards", description="List boards accessible to the configured token."
    )
    async def list_boards(
        request: schemas.ListBoardsRequest, ctx: Context
    ) -> schemas.ListBoardsResponse:
        return await active_service.list_boards(request, ctx)

    @instance.tool(name="get_board_items", description="Fetch supported items from a Miro board.")
    async def get_board_items(
        request: schemas.GetBoardItemsRequest, ctx: Context
    ) -> schemas.GetBoardItemsResponse:
        return await active_service.get_board_items(request, ctx)

    @instance.tool(name="get_item", description="Retrieve a single board item by identifier.")
    async def get_item(request: schemas.GetItemRequest, ctx: Context) -> schemas.BoardItem:
        return await active_service.get_item(request, ctx)

    @instance.tool(name="create_item", description="Create a new board item on a target board.")
    async def create_item(
        request: schemas.CreateItemRequest, ctx: Context
    ) -> schemas.CreateItemResponse:
        return await active_service.create_item(request, ctx)

    @instance.tool(name="update_item", description="Update properties for an existing board item.")
    async def update_item(
        request: schemas.UpdateItemRequest, ctx: Context
    ) -> schemas.UpdateItemResponse:
        return await active_service.update_item(request, ctx)

    @instance.tool(name="delete_item", description="Delete or archive a board item.")
    async def delete_item(
        request: schemas.DeleteItemRequest, ctx: Context
    ) -> schemas.DeleteItemResponse:
        return await active_service.delete_item(request, ctx)

    return instance
