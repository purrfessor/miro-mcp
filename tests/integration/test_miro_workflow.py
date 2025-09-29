from __future__ import annotations

import asyncio
import contextlib
import json
from typing import TYPE_CHECKING, Any, cast
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from pydantic import SecretStr
from testcontainers.core.container import DockerContainer  # type: ignore[import-untyped]

from miro_mcp.schemas import (
    CreateItemRequest,
    DeleteItemRequest,
    GetBoardItemsRequest,
    GetItemRequest,
    ItemPosition,
    ListBoardsRequest,
    ShapeItem,
    StickyNoteItem,
    TextItem,
    TextItemCreate,
    TextItemUpdate,
    UpdateItemRequest,
)
from miro_mcp.service import MiroService
from miro_mcp.settings import Settings

try:  # pragma: no cover - import guard for optional dependency
    import docker  # type: ignore[import-untyped]
except ImportError:  # pragma: no cover - handled in fixture skip
    docker = cast("Any", None)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterator

WIREMOCK_IMAGE = "wiremock/wiremock:3.9.1"
ADMIN_RESET_PATH = "/__admin/reset"
ADMIN_MAPPINGS_PATH = "/__admin/mappings"
ADMIN_FIND_REQUESTS_PATH = "/__admin/requests/find"


@pytest.fixture(scope="module", autouse=True)
def _require_docker() -> None:
    if docker is None:
        pytest.skip("Docker SDK is required for integration tests")

    client = None
    try:
        client = docker.from_env()
        client.ping()
    except docker.errors.DockerException as exc:
        pytest.skip(f"Docker daemon is not available: {exc}")
    finally:
        if client is not None:
            with contextlib.suppress(AttributeError, docker.errors.DockerException):
                client.close()


@pytest.fixture(scope="module")
def wiremock_container() -> Iterator[DockerContainer]:
    container = DockerContainer(WIREMOCK_IMAGE).with_exposed_ports(8080)
    with container:
        yield container


@pytest.fixture
async def integration_env(
    wiremock_container: DockerContainer,
) -> AsyncIterator[tuple[MiroService, str]]:
    base_url = _wiremock_base_url(wiremock_container)
    await _wait_for_wiremock(base_url)
    await _reset_wiremock(base_url)
    settings = Settings(
        token=SecretStr("test-token"),
        api_base_url=f"{base_url}/v2",
        request_timeout_seconds=5.0,
        user_agent="miro-mcp-integration-tests/0.1.0",
        default_page_size=10,
    )
    service = MiroService.from_settings(settings)
    try:
        yield service, base_url
    finally:
        await _reset_wiremock(base_url)


async def _reset_wiremock(base_url: str) -> None:
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(f"{base_url}{ADMIN_RESET_PATH}")
        response.raise_for_status()


def _wiremock_base_url(container: DockerContainer) -> str:
    host = container.get_container_host_ip()
    port = container.get_exposed_port(8080)
    return f"http://{host}:{port}"


async def _wait_for_wiremock(base_url: str, *, startup_timeout: float = 30.0) -> None:
    deadline = asyncio.get_event_loop().time() + startup_timeout
    async with httpx.AsyncClient(timeout=5.0) as client:
        while True:
            try:
                response = await client.get(f"{base_url}{ADMIN_MAPPINGS_PATH}")
            except httpx.HTTPError:
                response = None
            if response is not None and response.status_code < 500:
                return
            if asyncio.get_event_loop().time() >= deadline:
                msg = "WireMock container did not become ready in time"
                raise RuntimeError(msg)
            await asyncio.sleep(0.5)


async def _register_stub(
    base_url: str,
    *,
    method: str,
    url_path: str,
    status: int,
    body: dict[str, Any] | None = None,
) -> None:
    mapping: dict[str, Any] = {
        "request": {"method": method, "urlPath": url_path},
        "response": {"status": status},
    }
    if body is not None:
        mapping["response"]["jsonBody"] = body
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(f"{base_url}{ADMIN_MAPPINGS_PATH}", json=mapping)
        response.raise_for_status()


async def _fetch_requests(
    base_url: str,
    *,
    method: str,
    url_path: str,
) -> list[dict[str, Any]]:
    criteria = {"method": method, "urlPath": url_path}
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(f"{base_url}{ADMIN_FIND_REQUESTS_PATH}", json=criteria)
        response.raise_for_status()
    payload = response.json()
    raw_requests = payload.get("requests", [])
    requests: list[dict[str, Any]] = []
    for entry in raw_requests:
        if isinstance(entry, dict):
            request_data = entry.get("request") if "request" in entry else entry
            if isinstance(request_data, dict):
                requests.append(request_data)
    return requests


def _extract_header(request: dict[str, Any], header_name: str) -> str | None:
    headers = request.get("headers")
    if not isinstance(headers, dict):
        return None
    target = header_name.lower()
    for key, value in headers.items():
        if isinstance(key, str) and key.lower() == target:
            candidate = value[0] if isinstance(value, list) and value else value
            if isinstance(candidate, str):
                return candidate
            return str(candidate)
    return None


def _request_path_and_query(request: dict[str, Any]) -> tuple[str, dict[str, list[str]]]:
    url = request.get("url") or request.get("absoluteUrl") or ""
    parsed = urlsplit(url)
    return parsed.path, parse_qs(parsed.query)


def _request_body_json(request: dict[str, Any]) -> dict[str, Any]:
    body = request.get("bodyAsJson")
    if isinstance(body, dict):
        return body
    raw_text = request.get("body")
    if isinstance(raw_text, str) and raw_text:
        try:
            parsed = json.loads(raw_text)
        except json.JSONDecodeError:  # pragma: no cover - defensive fallback
            return {}
        if isinstance(parsed, dict):
            return parsed
    return {}


@pytest.mark.asyncio
async def test_list_boards_integration(integration_env: tuple[MiroService, str]) -> None:
    service, base_url = integration_env
    await _register_stub(
        base_url,
        method="GET",
        url_path="/v2/boards",
        status=200,
        body={
            "data": [
                {
                    "id": "b1",
                    "name": "Discovery Board",
                    "description": "Team planning space",
                    "createdAt": "2024-04-01T09:00:00Z",
                    "modifiedAt": "2024-04-02T10:30:00Z",
                    "owner": {"id": "u1", "name": "Pat Garcia", "type": "user"},
                    "currentUserAccessLevel": "editor",
                }
            ],
            "cursor": {"next": "next-cursor-token"},
        },
    )

    response = await service.list_boards(ListBoardsRequest(limit=5))

    assert response.next_cursor == "next-cursor-token"
    assert len(response.boards) == 1
    board = response.boards[0]
    assert board.id == "b1"
    assert board.title == "Discovery Board"
    assert board.description == "Team planning space"
    assert board.owner is not None
    assert board.owner.name == "Pat Garcia"
    assert board.access_level == "editor"

    requests = await _fetch_requests(base_url, method="GET", url_path="/v2/boards")
    assert requests, "Expected list boards request to be sent"
    path, query = _request_path_and_query(requests[0])
    assert path == "/v2/boards"
    assert query.get("limit") == ["5"]
    assert _extract_header(requests[0], "authorization") == "Bearer test-token"


@pytest.mark.asyncio
async def test_get_board_items_integration(integration_env: tuple[MiroService, str]) -> None:
    service, base_url = integration_env
    await _register_stub(
        base_url,
        method="GET",
        url_path="/v2/boards/board-1/items",
        status=200,
        body={
            "data": [
                {
                    "id": "text-1",
                    "type": "text",
                    "data": {"content": "Sprint goals"},
                    "createdAt": "2024-04-03T12:00:00Z",
                    "position": {"x": 120, "y": 80},
                },
                {
                    "id": "shape-1",
                    "type": "shape",
                    "data": {"content": "Milestone", "shape": {"type": "rectangle"}},
                    "modifiedAt": "2024-04-04T08:15:00Z",
                    "geometry": {"width": 320, "height": 180},
                },
                {
                    "id": "sticky-1",
                    "type": "sticky_note",
                    "data": {"content": "Retrospective", "shape": "square", "format": "note"},
                    "createdAt": "2024-04-05T09:00:00Z",
                    "position": {"x": 200, "y": 160},
                },
            ],
            "cursor": {"next": "items-cursor"},
        },
    )

    response = await service.get_board_items(GetBoardItemsRequest(board_id="board-1", limit=3))

    assert response.next_cursor == "items-cursor"
    assert len(response.items) == 3
    assert {item.type for item in response.items} == {"text", "shape", "sticky_note"}
    text_item = next(item for item in response.items if isinstance(item, TextItem))
    assert text_item.content == "Sprint goals"
    assert text_item.position is not None
    assert text_item.position.x == 120
    shape_item = next(item for item in response.items if isinstance(item, ShapeItem))
    assert shape_item.shape == "rectangle"
    sticky_item = next(item for item in response.items if isinstance(item, StickyNoteItem))
    assert sticky_item.format == "note"

    requests = await _fetch_requests(base_url, method="GET", url_path="/v2/boards/board-1/items")
    assert requests, "Expected get_board_items request to be sent"
    path, query = _request_path_and_query(requests[0])
    assert path == "/v2/boards/board-1/items"
    assert query.get("limit") == ["3"]
    assert _extract_header(requests[0], "authorization") == "Bearer test-token"


@pytest.mark.asyncio
async def test_get_item_integration(integration_env: tuple[MiroService, str]) -> None:
    service, base_url = integration_env
    await _register_stub(
        base_url,
        method="GET",
        url_path="/v2/boards/board-9/items/shape-9",
        status=200,
        body={
            "id": "shape-9",
            "type": "shape",
            "data": {"content": "Architecture", "shape": {"type": "triangle"}},
            "modifiedAt": "2024-04-06T07:45:00Z",
        },
    )

    item = await service.get_item(GetItemRequest(board_id="board-9", item_id="shape-9"))

    assert isinstance(item, ShapeItem)
    assert item.id == "shape-9"
    assert item.content == "Architecture"
    assert item.shape == "triangle"

    requests = await _fetch_requests(
        base_url, method="GET", url_path="/v2/boards/board-9/items/shape-9"
    )
    assert requests, "Expected get_item request to be sent"
    path, query = _request_path_and_query(requests[0])
    assert path == "/v2/boards/board-9/items/shape-9"
    assert query == {}
    assert _extract_header(requests[0], "authorization") == "Bearer test-token"


@pytest.mark.asyncio
async def test_create_update_delete_item_flow(integration_env: tuple[MiroService, str]) -> None:
    service, base_url = integration_env
    await _register_stub(
        base_url,
        method="POST",
        url_path="/v2/boards/board-2/items",
        status=201,
        body={
            "id": "text-2",
            "type": "text",
            "data": {"content": "Integration text"},
        },
    )
    await _register_stub(
        base_url,
        method="PATCH",
        url_path="/v2/boards/board-2/items/text-2",
        status=200,
        body={
            "id": "text-2",
            "type": "text",
            "data": {"content": "Updated content"},
            "modifiedAt": "2024-04-07T12:00:00Z",
        },
    )
    await _register_stub(
        base_url,
        method="DELETE",
        url_path="/v2/boards/board-2/items/text-2",
        status=204,
        body=None,
    )

    create_response = await service.create_item(
        CreateItemRequest(
            board_id="board-2",
            item=TextItemCreate(content="Integration text"),
        )
    )
    assert create_response.item.id == "text-2"
    assert create_response.item.content == "Integration text"

    update_response = await service.update_item(
        UpdateItemRequest(
            board_id="board-2",
            item_id="text-2",
            item=TextItemUpdate(
                content="Updated content",
                position=ItemPosition(x=400.0, y=320.0),
            ),
        )
    )
    assert update_response.item.content == "Updated content"

    delete_response = await service.delete_item(
        DeleteItemRequest(board_id="board-2", item_id="text-2", hard_delete=True)
    )
    assert delete_response.ok is True

    create_requests = await _fetch_requests(
        base_url, method="POST", url_path="/v2/boards/board-2/items"
    )
    assert create_requests, "Expected create_item request"
    create_body = _request_body_json(create_requests[0])
    assert create_body.get("data", {}).get("content") == "Integration text"

    update_requests = await _fetch_requests(
        base_url, method="PATCH", url_path="/v2/boards/board-2/items/text-2"
    )
    assert update_requests, "Expected update_item request"
    update_body = _request_body_json(update_requests[0])
    assert update_body.get("data", {}).get("content") == "Updated content"
    position = update_body.get("position")
    assert position is not None
    assert position.get("x") == 400.0

    delete_requests = await _fetch_requests(
        base_url, method="DELETE", url_path="/v2/boards/board-2/items/text-2"
    )
    assert delete_requests, "Expected delete_item request"
    path, query = _request_path_and_query(delete_requests[0])
    assert path == "/v2/boards/board-2/items/text-2"
    assert query.get("permanent") == ["true"]
    assert _extract_header(delete_requests[0], "authorization") == "Bearer test-token"
