"""Configuration and constants for Adaptyv Lab SDK."""

from __future__ import annotations

import os
from dataclasses import dataclass

from pydantic_settings import BaseSettings, SettingsConfigDict

from adaptyv.types.internal import CostEstimate

FOUNDRY_API_BASE_URL = "https://foundry-api-public.adaptyvbio.com"
FOUNDRY_API_INTERNAL_URL = "https://foundry-api-internal.adaptyvbio.com"
DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_RETRIES = 3

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


# Mock mode for CI/testing (disables real API calls)
# Set ADAPTYV_MOCK_MODE=1 or ADAPTYV_MOCK_MODE=true to enable
MOCK_MODE = os.environ.get("ADAPTYV_MOCK_MODE", "").lower() in ("1", "true", "yes")

# RCSB PDB download URL template - use /download/ not /view/
# Format with pdb_id: RCSB_PDB_DOWNLOAD_URL.format(pdb_id="4ZQK")
RCSB_PDB_DOWNLOAD_URL = "https://files.rcsb.org/download/{pdb_id}.pdb"

# CLI defaults for design workflows
DEFAULT_BINDER_LENGTH_RANGE: tuple[int, int] = (50, 100)
DEFAULT_NUM_DESIGNS: int = 5
DEFAULT_DESIGN_TEMPERATURE: float = 0.1
DEFAULT_COST_PER_DESIGN_USD: float = 99.0  # USD per design for screening
DEFAULT_TIME_PER_DESIGN_SEC: float = 20.0  # ~20 seconds per protein design
DEFAULT_HISTORY_LIMIT: int = 10
DEFAULT_FILTERED_RUNS_LIMIT: int = 20

# Local Dashboard URL - the local protein designer dashboard
LOCAL_DASHBOARD_URL = os.environ.get("LOCAL_DASHBOARD_URL", "http://localhost:5050")

# MCP Server script path (for protein design tools)
MCP_SERVER_SCRIPT = os.path.join(os.path.dirname(__file__), "agent", "mcp_server.py")

# Remote config for SDK defaults (URLs not hardcoded in source)
_REMOTE_CONFIG_URL = "https://api.adaptyvbio.com/sdk/config.json"
_REMOTE_CONFIG_CACHE: dict[str, str] | None = None


def _fetch_remote_config() -> dict[str, str]:
    """Fetch SDK configuration from remote endpoint.

    Returns cached config if available. Falls back to empty dict on failure.
    This allows internal URLs to work without hardcoding them in source.
    """
    global _REMOTE_CONFIG_CACHE
    if _REMOTE_CONFIG_CACHE is not None:
        return _REMOTE_CONFIG_CACHE

    try:
        import httpx

        resp = httpx.get(_REMOTE_CONFIG_URL, timeout=5.0, follow_redirects=True)
        if resp.status_code == 200:
            _REMOTE_CONFIG_CACHE = resp.json()
        else:
            _REMOTE_CONFIG_CACHE = {}
    except Exception:
        _REMOTE_CONFIG_CACHE = {}

    return _REMOTE_CONFIG_CACHE


def get_labos_url() -> str:
    """Get LabOS Dashboard URL.

    Priority: env var > remote config > empty string.
    Set LABOS_BASE_URL environment variable to override.
    """
    return os.environ.get("LABOS_BASE_URL") or _fetch_remote_config().get("labos_url", "")


# Adaptyv Molstar viewer (hardcoded)
_ADAPTYV_MOLSTAR_URL = "https://adaptyv-molstar-git-feat-url-query-params-adaptyv-bio.vercel.app"


def get_molstar_url() -> str:
    """Get Molstar Viewer URL.

    Priority: env var > remote config > hardcoded Adaptyv viewer.
    Set MOLSTAR_VIEWER_URL environment variable to override.
    Features: surface view by default, hotspot highlighting via hotspots param.
    """
    return (
        os.environ.get("MOLSTAR_VIEWER_URL")
        or _fetch_remote_config().get("molstar_url", "")
        or _ADAPTYV_MOLSTAR_URL
    )


def get_sdk_service_url() -> str:
    """Get Adaptyv Lab SDK Modal service URL.

    This is the URL for modal_server.py deployed on Modal.

    Priority: env var > remote config > empty string.
    When running in Modal, this is automatically provided by the Modal secret
    'adaptyv-lab-sdk-auth' which contains SDK_SERVICE_URL.
    For local CLI usage, set SDK_SERVICE_URL environment variable or it will
    be fetched from remote config.
    """
    env_url = os.environ.get("SDK_SERVICE_URL")
    if env_url:
        return env_url

    # Fall back to remote config
    remote_config = _fetch_remote_config()
    return remote_config.get("sdk_service_url", "")


# Backwards compatibility - these now call the getter functions
# Note: These are evaluated at import time, so env vars must be set before import
LABOS_BASE_URL = get_labos_url()
MOLSTAR_VIEWER_URL = get_molstar_url()


class FoundrySettings(BaseSettings):
    """Foundry API configuration with automatic env var loading.

    Reads configuration from environment variables with ADAPTYV_ prefix:
    - ADAPTYV_API_KEY: API key for authentication
    - ADAPTYV_API_URL: Override public API URL
    - ADAPTYV_API_TYPE: "public" or "internal" to select API
    - ADAPTYV_ORGANIZATION_ID: Default organization ID
    - ADAPTYV_TIMEOUT: Request timeout in seconds
    - ADAPTYV_MOCK_MODE: Enable mock mode for testing

    Note: Does NOT load from .env file by default. Use python-dotenv's
    load_dotenv() before instantiation if needed, or the CLI which
    handles this automatically.
    """

    model_config = SettingsConfigDict(
        env_prefix="ADAPTYV_",
        extra="ignore",
    )

    api_key: str = ""
    api_url: str = FOUNDRY_API_BASE_URL
    api_type: str = "public"  # "public" or "internal"
    organization_id: str | None = None
    timeout: int = DEFAULT_TIMEOUT_SECONDS
    mock_mode: bool = False

    def get_base_url(self) -> str:
        """Get the appropriate base URL based on api_type."""
        if self.api_type == "internal":
            return FOUNDRY_API_INTERNAL_URL
        return self.api_url


# Hardcoded cost estimates (vibe estimates, not exact)
COST_ESTIMATES = {
    "bindcraft": CostEstimate(
        generation_usd=0.25,
        auto_filtering_usd=0.02,
        manual_filtering_usd=0.0,
        experimental_usd=0.0,  # Set from quote
        generation_range=(0.10, 0.50),
        experimental_range=(99.0, 500.0),
        can_upsize=True,
        can_downsize=True,
        upsize_cost_delta=0.10,
        downsize_cost_delta=-0.05,
    ),
    "germinal": CostEstimate(
        generation_usd=0.30,
        auto_filtering_usd=0.02,
        manual_filtering_usd=0.0,
        experimental_usd=0.0,
        generation_range=(0.15, 0.60),
        experimental_range=(99.0, 500.0),
        can_upsize=True,
        can_downsize=True,
        upsize_cost_delta=0.15,
        downsize_cost_delta=-0.08,
    ),
}


def get_cost_estimate(workflow: str, n_designs: int) -> CostEstimate:
    """Get estimated costs for a workflow (demo: experimental cost only)."""
    experimental_cost = DEFAULT_COST_PER_DESIGN_USD * n_designs  # $99 × designs
    return CostEstimate(
        generation_usd=0.0,  # Removed for demo
        auto_filtering_usd=0.0,  # Removed for demo
        manual_filtering_usd=0.0,
        experimental_usd=experimental_cost,
        generation_range=(0.0, 0.0),
        experimental_range=(experimental_cost, experimental_cost),
        can_upsize=False,
        can_downsize=False,
        upsize_cost_delta=0.0,
        downsize_cost_delta=0.0,
    )


def get_time_estimate(n_designs: int) -> float:
    """Get estimated time for design generation in seconds."""
    return DEFAULT_TIME_PER_DESIGN_SEC * n_designs
