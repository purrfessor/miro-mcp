# Miro MCP Server

The Miro MCP server exposes Model Context Protocol (MCP) tools for listing boards and
managing text, shape, and sticky note items on behalf of downstream agents. It wraps the
Miro REST API with consistent schemas and error handling so assistants can perform board
operations without bespoke API integrations.

## Features

- List accessible boards with metadata including owner and access level.
- Fetch board snapshots focused on text boxes, shapes, and sticky notes.
- Create, update, and delete supported items with typed payloads.
- Translate Miro API failures into meaningful MCP tool errors with retry hints.

## Getting Started

1. Install dependencies with [`uv`](https://docs.astral.sh/uv/):

   ```bash
   uv sync --dev
   ```

2. Export a [Miro personal access token](https://developers.miro.com/reference/personal-access-tokens)
   for the workspace you want to access:

   ```bash
   export MIRO_TOKEN="your-token"
   ```

3. Start the MCP server:

   ```bash
   uv run python -m miro_mcp
   ```

   The server exposes the MCP tools `list_boards`, `get_board_items`, `get_item`,
   `create_item`, `update_item`, and `delete_item`.

## Using with MCP Clients

You can connect the running server to any MCP-compatible client by referencing the
same command that you would run locally. Below are example configurations for the
most common tools.

### Claude Code (VS Code extension)

Add an entry under `claudeCode.mcpServers` in your VS Code `settings.json`:

```json
{
  "claudeCode.mcpServers": [
    {
      "name": "miro",
      "command": "uv",
      "args": ["run", "python", "-m", "miro_mcp"],
      "env": {
        "MIRO_TOKEN": "${env:MIRO_TOKEN}"
      }
    }
  ]
}
```

The extension will spawn the server automatically when you open a workspace and
surface the `miro` tools from the MCP sidebar.

### Cursor

In Cursor, open **Settings → MCP Servers → Add Server** and supply the same
command:

```json
{
  "name": "miro",
  "command": "uv",
  "args": ["run", "python", "-m", "miro_mcp"],
  "env": {
    "MIRO_TOKEN": "${env:MIRO_TOKEN}"
  }
}
```

Once saved, the Cursor chat sidebar will list the `miro` tools and allow you to
invoke them within your project.

### Codex CLI

Register the server with the Codex CLI using the `mcp add` subcommand:

```bash
codex mcp add miro --command uv -- uv run python -m miro_mcp
```

The CLI forwards your current environment so make sure `MIRO_TOKEN` is set before
invoking any MCP tools:

```bash
MIRO_TOKEN=your-token codex mcp call miro list_boards
```

## Development

- Format and lint the codebase:

  ```bash
  uv run ruff format .
  uv run ruff check --fix
  ```

- Run type checks:

  ```bash
  uv run mypy --strict
  ```

- Execute the test suite:

  ```bash
  uv run pytest
  ```

## Configuration

The server uses the following environment variables:

| Variable     | Description                                              |
| ------------ | -------------------------------------------------------- |
| `MIRO_TOKEN` | Personal access token used to authenticate with the API. |
| `MIRO_API_BASE_URL` | Optional override for the Miro REST API base URL. |

Timeouts, default pagination size, and the user agent can be tuned through
`Settings` in `src/miro_mcp/settings.py`.

## Testing

The project includes unit tests that exercise request/response schemas, service logic,
and error translation. HTTP requests are mocked so tests can run without real Miro
credentials.
