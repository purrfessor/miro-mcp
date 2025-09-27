"""Application settings for the Miro MCP server."""

from __future__ import annotations

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration."""

    model_config = SettingsConfigDict(env_prefix="MIRO_", env_file=".env", extra="ignore")

    token: SecretStr | None = Field(
        default=None, description="Personal access token for the Miro API"
    )
    api_base_url: str = Field(
        default="https://api.miro.com/v2", description="Base URL for the Miro REST API"
    )
    request_timeout_seconds: float = Field(
        default=30.0, gt=0, description="HTTP request timeout in seconds"
    )
    user_agent: str = Field(
        default="miro-mcp-server/0.1.0",
        description="User agent string sent with Miro API requests",
    )
    default_page_size: int = Field(
        default=50, ge=1, le=100, description="Default pagination size for list endpoints"
    )

    def require_token(self) -> SecretStr:
        """Return the configured token or raise a helpful error."""
        if self.token is None:
            msg = (
                "Missing MIRO_TOKEN environment variable. Configure a personal access token before "
                "starting the server."
            )
            raise ValueError(msg)
        return self.token
