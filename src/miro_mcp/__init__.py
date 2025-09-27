"""Miro MCP server package."""

from __future__ import annotations

from importlib import metadata

__all__ = ["__version__"]

try:
    __version__ = metadata.version("miro-mcp")
except metadata.PackageNotFoundError:  # pragma: no cover - fallback during local runs
    __version__ = "0.0.0"
