# Product Requirements Document: Miro MCP Server

## 1. Overview
The Miro MCP server exposes automation tools that allow downstream agents to read and modify Miro boards without direct interaction with the Miro REST API. Agents use the server to retrieve structured board context and perform item-level updates (texts, shapes, sticky notes) through consistent Model Context Protocol (MCP) tooling.

## 2. Goals & Success Metrics
- Enable agents to list accessible boards and inspect board contents relevant to supported item types.
- Provide CRUD coverage for text boxes, shapes, and sticky notes with intuitive schemas for create/update operations.
- Guarantee meaningful error responses that translate Miro SDK failures into actionable MCP errors, including rate-limit messaging.
- Ship documentation and runtime defaults that allow setup via personal access tokens and repeatable tooling (`uv`, `ruff`, `mypy`, `pytest`).

Success is measured by:
- Agents can complete end-to-end flows (list boards, inspect items, modify or delete) without manual intervention.
- Linting, type-checking, and test suites pass in CI for every change touching the MCP server code.

## 3. User Story
“As an agent developer, I want my MCP-connected assistant to retrieve and edit board content so a user can iterate on a Miro board through conversation alone.”

## 4. In-Scope Functionality
### 4.1 Board Interactions
- `list_boards`: return board metadata (id, title, description, created/updated timestamps, owner info, access level).
- `get_board_items`: fetch a board snapshot focused on supported item types; include item coordinates, styling, parent frames when exposed.

### 4.2 Item CRUD (Texts, Shapes, Sticky Notes)
- Create items with type-specific payloads, optional styling, and coordinate placement.
- Read individual items (`get_item`) to confirm state after mutations.
- Update item properties (content, styling, position) via partial payloads.
- Delete or archive items; prefer soft-delete where Miro distinguishes between archive vs hard delete.
- Surface rate limit and permission issues with descriptive MCP error payloads and retry guidance.

### 4.3 Error Handling & Observability
- Map authentication, validation, and rate-limit exceptions from the Miro SDK to MCP errors.
- Emit structured logs around SDK calls for debugging and diagnostics.

## 5. Out-of-Scope (Documented for Later)
- CRUD for connectors, images, frames, tables, cards, embeds, documents, or other advanced widgets.
- Board creation, duplication, archival, export, or sharing workflows.
- Real-time websocket updates, event-driven automation, or webhook processing.
- Multi-user credential storage, OAuth consent flows, or token rotation services.
- Bulk operations (batch moves, template application) beyond single-call CRUD primitives.

## 6. Technical Approach
- Build on `fastmcp` to expose discrete tools per capability with Pydantic schemas for requests/responses.
- Wrap the Miro Python Client SDK methods.
- Load Miro personal access token (PAT) from environment variables; defer OAuth flow implementation.
- Define shared item base schema (id, type, board_id, created/modified timestamps, last_editor) with discriminated unions for text, shape, sticky note payloads.
- Implement pagination and filtering for board item queries
- Respect SDK field constraints; validate inputs before sending to Miro to reduce 4xx errors.

## 7. Tool Surface
- `list_boards`
- `get_board_items`
- `get_item`
- `create_item`
- `update_item`
- `delete_item`

Each tool returns typed responses; request schemas accept minimal required fields with optional style dictionaries.

## 8. Non-Functional Requirements
- Strict typing with `mypy` (retain `strict = True` in `mypy.ini`).
- Style and lint enforcement through `ruff format` and `ruff check --select ALL`.
- Dependency management via `uv`; ensure lockfile and reproducible environments.
- Unit tests with `pytest`; mock HTTP via `responses`/`pytest-httpx`.

## 9. Testing Strategy
- Unit coverage for tool handlers validating schema enforcement and error translation.
- Contract-style tests verifying create/update/delete flows, including negative cases (invalid payloads, permission errors).

## 10. Open Questions
1. Should we implement board-level caching to reduce repeated fetches, or always rely on live data? - rely on live data
2. Are localization or timezone adjustments needed for timestamps in tool responses? - no
3. Do we need a server-side rate-limit policy to protect the PAT from excessive calls by aggressive clients? - no

