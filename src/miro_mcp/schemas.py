"""Pydantic schemas for Miro MCP tooling."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SUPPORTED_ITEM_TYPES = {"text", "shape", "sticky_note"}


def _coerce_optional_str(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return str(value)


def _coerce_str(value: Any, *, default: str) -> str:
    result = _coerce_optional_str(value)
    if result is None or result == "":
        return default
    return result


def _parse_datetime(raw: Any) -> datetime | None:
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw
    if isinstance(raw, str) and raw:
        normalized = raw.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(normalized)
        except ValueError:
            return None
    return None


class BoardOwner(BaseModel):
    """Board owner metadata."""

    id: str | None = None
    name: str | None = None
    type: str | None = None


class BoardSummary(BaseModel):
    """Lightweight board metadata."""

    id: str
    title: str
    description: str | None = None
    created_at: datetime | None = Field(default=None, alias="createdAt")
    updated_at: datetime | None = Field(default=None, alias="updatedAt")
    owner: BoardOwner | None = None
    access_level: str | None = None

    model_config = ConfigDict(populate_by_name=True)

    @classmethod
    def from_api(cls, payload: Mapping[str, Any]) -> BoardSummary:
        """Build a summary from a raw API payload."""
        owner_data = payload.get("owner") or payload.get("createdBy")
        owner: BoardOwner | None = None
        if isinstance(owner_data, Mapping):
            owner = BoardOwner(
                id=_coerce_optional_str(owner_data.get("id")),
                name=_coerce_optional_str(owner_data.get("name")),
                type=_coerce_optional_str(owner_data.get("type")),
            )

        return cls(
            id=_coerce_str(payload.get("id") or payload.get("boardId"), default="unknown"),
            title=_coerce_str(
                payload.get("name") or payload.get("title"), default="Untitled board"
            ),
            description=_coerce_optional_str(payload.get("description")),
            createdAt=_parse_datetime(payload.get("createdAt")),
            updatedAt=_parse_datetime(payload.get("modifiedAt") or payload.get("updatedAt")),
            owner=owner,
            access_level=_coerce_optional_str(
                payload.get("currentUserAccessLevel") or payload.get("accessLevel")
            ),
        )


class ListBoardsRequest(BaseModel):
    """Request payload for `list_boards`."""

    cursor: str | None = None
    limit: int = Field(default=50, ge=1, le=100)


class ListBoardsResponse(BaseModel):
    """Response payload for `list_boards`."""

    boards: list[BoardSummary]
    next_cursor: str | None = None


class ItemPosition(BaseModel):
    """Geometry for an item on a board."""

    x: float | None = None
    y: float | None = None
    width: float | None = None
    height: float | None = None
    rotation: float | None = None


class BoardItemBase(BaseModel):
    """Shared fields across supported board items."""

    id: str
    board_id: str
    type: str
    created_at: datetime | None = Field(default=None, alias="createdAt")
    updated_at: datetime | None = Field(default=None, alias="updatedAt")
    created_by: str | None = None
    last_modified_by: str | None = None
    position: ItemPosition | None = None
    style: Mapping[str, Any] | None = None
    parent_id: str | None = None

    model_config = ConfigDict(populate_by_name=True)


class TextItem(BoardItemBase):
    """Typed representation of a text widget."""

    type: Literal["text"] = Field(default="text", frozen=True)
    content: str


class ShapeItem(BoardItemBase):
    """Typed representation of a shape widget."""

    type: Literal["shape"] = Field(default="shape", frozen=True)
    shape: str | None = None
    content: str | None = None


class StickyNoteItem(BoardItemBase):
    """Typed representation of a sticky note."""

    type: Literal["sticky_note"] = Field(default="sticky_note", frozen=True)
    content: str
    shape: str | None = None
    format: str | None = None


BoardItem = Annotated[TextItem | ShapeItem | StickyNoteItem, Field(discriminator="type")]


class GetBoardItemsRequest(BaseModel):
    """Request parameters for fetching board items."""

    board_id: str
    cursor: str | None = None
    limit: int = Field(default=100, ge=1, le=200)


class GetBoardItemsResponse(BaseModel):
    """Response payload wrapping board items."""

    items: list[BoardItem]
    next_cursor: str | None = None


class GetItemRequest(BaseModel):
    """Request payload for retrieving a single item."""

    board_id: str
    item_id: str


class ItemCreateBase(BaseModel):
    """Shared fields when creating an item."""

    position: ItemPosition | None = None
    style: Mapping[str, Any] | None = None


class TextItemCreate(ItemCreateBase):
    """Create payload for text items."""

    type: Literal["text"] = Field(default="text", frozen=True)
    content: str


class ShapeItemCreate(ItemCreateBase):
    """Create payload for shape items."""

    type: Literal["shape"] = Field(default="shape", frozen=True)
    shape: str
    content: str | None = None


class StickyNoteItemCreate(ItemCreateBase):
    """Create payload for sticky notes."""

    type: Literal["sticky_note"] = Field(default="sticky_note", frozen=True)
    content: str
    shape: str | None = None
    format: str | None = None


ItemCreatePayload = Annotated[
    TextItemCreate | ShapeItemCreate | StickyNoteItemCreate,
    Field(discriminator="type"),
]


class CreateItemRequest(BaseModel):
    """Top-level request for item creation."""

    board_id: str
    item: ItemCreatePayload


class CreateItemResponse(BaseModel):
    """Response returned after creating an item."""

    item: BoardItem


class ItemUpdateBase(BaseModel):
    """Shared update fields for items."""

    position: ItemPosition | None = None
    style: Mapping[str, Any] | None = None


class TextItemUpdate(ItemUpdateBase):
    """Update payload for text items."""

    type: Literal["text"] = Field(default="text", frozen=True)
    content: str | None = None


class ShapeItemUpdate(ItemUpdateBase):
    """Update payload for shape items."""

    type: Literal["shape"] = Field(default="shape", frozen=True)
    shape: str | None = None
    content: str | None = None


class StickyNoteItemUpdate(ItemUpdateBase):
    """Update payload for sticky notes."""

    type: Literal["sticky_note"] = Field(default="sticky_note", frozen=True)
    content: str | None = None
    shape: str | None = None
    format: str | None = None


ItemUpdatePayload = Annotated[
    TextItemUpdate | ShapeItemUpdate | StickyNoteItemUpdate,
    Field(discriminator="type"),
]


class UpdateItemRequest(BaseModel):
    """Request payload for item updates."""

    board_id: str
    item_id: str
    item: ItemUpdatePayload

    @model_validator(mode="after")
    def ensure_updates_present(self) -> UpdateItemRequest:
        """Ensure the update payload contains at least one field."""
        payload = self.item
        has_updates = any(
            getattr(payload, field) is not None
            for field in ("content", "shape", "format", "position", "style")
        )
        if not has_updates:
            message = "Provide at least one field to update."
            raise ValueError(message)
        return self


class UpdateItemResponse(BaseModel):
    """Response payload after updating an item."""

    item: BoardItem


class DeleteItemRequest(BaseModel):
    """Request payload for deleting an item."""

    board_id: str
    item_id: str
    hard_delete: bool = False


class DeleteItemResponse(BaseModel):
    """Response payload indicating delete success."""

    ok: bool


def build_position(payload: Mapping[str, Any]) -> ItemPosition | None:
    """Convert raw geometry fields into an ItemPosition model."""
    position_data = payload.get("position")
    geometry = payload.get("geometry") or payload.get("bounds")

    x = _coerce_optional_float(position_data, "x")
    y = _coerce_optional_float(position_data, "y")
    rotation = _coerce_optional_float(position_data, "rotation")
    width = _coerce_optional_float(geometry, "width")
    height = _coerce_optional_float(geometry, "height")

    if all(value is None for value in (x, y, rotation, width, height)):
        return None
    return ItemPosition(x=x, y=y, rotation=rotation, width=width, height=height)


def _coerce_optional_float(data: Any, key: str) -> float | None:
    if not isinstance(data, Mapping):
        return None
    value = data.get(key)
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_item(payload: Mapping[str, Any], *, board_id: str) -> BoardItem | None:
    """Convert a raw Miro item payload into a typed BoardItem."""
    raw_type = _coerce_optional_str(payload.get("type")) or _coerce_optional_str(
        payload.get("itemType")
    )
    if raw_type not in SUPPORTED_ITEM_TYPES:
        return None

    style_section = payload.get("style") if isinstance(payload.get("style"), Mapping) else None
    base_kwargs: dict[str, Any] = {
        "id": _coerce_str(payload.get("id"), default="unknown"),
        "board_id": board_id,
        "created_at": _parse_datetime(payload.get("createdAt")),
        "updated_at": _parse_datetime(payload.get("modifiedAt") or payload.get("updatedAt")),
        "created_by": _coerce_optional_str(_nested_lookup(payload, ("createdBy", "id"))),
        "last_modified_by": _coerce_optional_str(_nested_lookup(payload, ("modifiedBy", "id"))),
        "position": build_position(payload),
        "style": style_section,
        "parent_id": _coerce_optional_str(_nested_lookup(payload, ("parent", "id"))),
    }

    data_section = payload.get("data")
    content = _extract_content(data_section)

    if raw_type == "text":
        if content is None:
            content = ""
        payload_data = {**base_kwargs, "content": content}
        return TextItem.model_validate(payload_data)

    if raw_type == "shape":
        shape_value = _extract_shape(data_section)
        payload_data = {**base_kwargs, "content": content, "shape": shape_value}
        return ShapeItem.model_validate(payload_data)

    if raw_type == "sticky_note":
        shape_value = _extract_shape(data_section)
        format_value = None
        if isinstance(data_section, Mapping):
            format_value = _coerce_optional_str(data_section.get("format"))
        if content is None:
            content = ""
        payload_data = {
            **base_kwargs,
            "content": content,
            "shape": shape_value,
            "format": format_value,
        }
        return StickyNoteItem.model_validate(payload_data)

    return None


def _nested_lookup(payload: Mapping[str, Any], path: tuple[str, ...]) -> Any:
    current: Any = payload
    for key in path:
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)
    return current


def _extract_content(data_section: Any) -> str | None:
    if isinstance(data_section, Mapping):
        return _coerce_optional_str(data_section.get("content"))
    return None


def _extract_shape(data_section: Any) -> str | None:
    if isinstance(data_section, Mapping):
        shape_value = data_section.get("shape")
        if isinstance(shape_value, Mapping):
            return _coerce_optional_str(shape_value.get("type"))
        return _coerce_optional_str(shape_value)
    return None
