"""Command line entry point for running the Miro MCP server."""

from __future__ import annotations

from fastmcp.exceptions import ToolError

from .server import create_server


def main() -> None:
    """Start the FastMCP server using environment configuration."""
    try:
        server = create_server()
    except ValueError as exc:
        message = str(exc)
        raise SystemExit(message) from exc

    try:
        server.run()
    except ToolError as exc:  # pragma: no cover - defensive guard
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    main()
