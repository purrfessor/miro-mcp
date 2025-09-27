"""Custom exception hierarchy for Miro API error handling."""

from __future__ import annotations

import contextlib
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import httpx


@dataclass(slots=True)
class MiroAPIError(Exception):
    """Represents a failure returned by the Miro REST API."""

    status_code: int
    message: str
    code: str | None = None
    details: Mapping[str, Any] | None = None
    retry_after: float | None = None

    def __str__(self) -> str:
        """Return a human-readable representation of the error."""
        detail = f" ({self.code})" if self.code else ""
        return f"HTTP {self.status_code}{detail}: {self.message}"

    @classmethod
    def from_response(cls, response: httpx.Response) -> MiroAPIError:
        """Build an error from an HTTP response."""
        retry_after: float | None = None
        header_value = response.headers.get("Retry-After")
        if header_value is not None:
            with contextlib.suppress(ValueError):
                retry_after = float(header_value)

        message = response.reason_phrase or "Miro API request failed"
        code: str | None = None
        details: Mapping[str, Any] | None = None

        with contextlib.suppress(ValueError):
            payload = response.json()
            if isinstance(payload, Mapping):
                code = _coerce_optional_str(payload.get("code"))
                if "message" in payload:
                    message = str(payload["message"])
                errors = payload.get("errors")
                if isinstance(errors, list) and errors:
                    first_error = errors[0]
                    if isinstance(first_error, Mapping):
                        code = _coerce_optional_str(first_error.get("code")) or code
                        detail_message = _coerce_optional_str(first_error.get("message"))
                        if detail_message:
                            message = detail_message
                details = payload

        return cls(
            status_code=response.status_code,
            message=message,
            code=code,
            details=details,
            retry_after=retry_after,
        )


def _coerce_optional_str(value: Any) -> str | None:
    """Coerce arbitrary values into optional strings."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return str(value)
