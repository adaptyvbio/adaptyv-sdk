"""Configuration for Adaptyv SDK."""

from __future__ import annotations

from dataclasses import dataclass

from pydantic_settings import BaseSettings, SettingsConfigDict

# Default timeouts and retries
DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_RETRIES = 3

# Default API URL
FOUNDRY_API_URL = "https://foundry-api.adaptyvbio.com/api/v1"

# Retry configuration defaults (exponential backoff)
DEFAULT_RETRY_MAX_ATTEMPTS = 3
DEFAULT_RETRY_BACKOFF_FACTOR = 2.0
DEFAULT_RETRY_MAX_BACKOFF = 30.0  # Cap backoff at 30s (AWS standard)
DEFAULT_RETRY_JITTER = True


@dataclass
class RetryConfig:
    """Configuration for exponential backoff retry logic.

    Backoff formula: min(max_backoff, backoff_factor ** attempt) + jitter

    Attributes:
        max_attempts: Maximum number of retry attempts (not including initial request)
        backoff_factor: Base for exponential backoff (default 2.0)
        max_backoff: Maximum backoff time in seconds (default 30.0)
        jitter: Whether to add random jitter (0-1s) to prevent thundering herd
    """

    max_attempts: int = DEFAULT_RETRY_MAX_ATTEMPTS
    backoff_factor: float = DEFAULT_RETRY_BACKOFF_FACTOR
    max_backoff: float = DEFAULT_RETRY_MAX_BACKOFF
    jitter: bool = DEFAULT_RETRY_JITTER

    def get_backoff(self, attempt: int) -> float:
        """Calculate backoff time for a given attempt number.

        Args:
            attempt: Current attempt number (0-indexed, so attempt=0 is first retry)

        Returns:
            Backoff time in seconds with optional jitter.
        """
        import random

        backoff = min(self.max_backoff, self.backoff_factor**attempt)
        if self.jitter:
            backoff += random.uniform(0, 1)  # noqa: S311
        return backoff


class AdaptyvConfig(BaseSettings):
    """SDK configuration loaded from environment.

    Reads configuration from environment variables with ADAPTYV_ prefix:
    - ADAPTYV_API_KEY: API key for authentication (required)
    - ADAPTYV_API_URL: API base URL (defaults to Foundry internal API)
    - ADAPTYV_ORGANIZATION_ID: Default organization ID
    - ADAPTYV_TIMEOUT: Request timeout in seconds

    Note: Does NOT load from .env file by default. Use python-dotenv's
    load_dotenv() before instantiation if needed.
    """

    model_config = SettingsConfigDict(
        env_prefix="ADAPTYV_",
        extra="ignore",
    )

    api_key: str = ""
    api_url: str = FOUNDRY_API_URL
    organization_id: str | None = None
    timeout: int = DEFAULT_TIMEOUT_SECONDS
    mock_mode: bool = False
