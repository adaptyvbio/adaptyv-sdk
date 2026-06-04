"""Contract tests pegging the SDK to the deployed Foundry OpenAPI spec.

Network-only (``integration``). They fetch the live ``openapi.json`` and fail
when it drifts from what the SDK targets, signaling that the types should be
regenerated (``mise run gen:types``) and ``FOUNDRY_SPEC_VERSION`` bumped to
match. CI runs them on a schedule so drift surfaces as a failed build rather
than as silent breakage at call time.
"""

from __future__ import annotations

import json
import os
import urllib.request

import pytest

from adaptyv.config import FOUNDRY_SPEC_VERSION

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not os.environ.get("ADAPTYV_API_URL"),
        reason="ADAPTYV_API_URL must be set",
    ),
]

# Every endpoint the client implements, relative to the /api/v1 base the
# base_url carries. Keep this in lockstep with the spec: when a test below
# fails, add or remove the client method and update this set to match.
SDK_PATHS = {
    "/experiments",
    "/experiments/cost-estimate",
    "/experiments/{experiment_id}",
    "/experiments/{experiment_id}/invoice",
    "/experiments/{experiment_id}/quote",
    "/experiments/{experiment_id}/quote/confirm",
    "/experiments/{experiment_id}/quote/pdf",
    "/experiments/{experiment_id}/results",
    "/experiments/{experiment_id}/sequences",
    "/experiments/{experiment_id}/submit",
    "/experiments/{experiment_id}/updates",
    "/feedback/submit",
    "/info/health",
    "/info/health-db",
    "/quotes",
    "/quotes/{quote_id}",
    "/quotes/{quote_id}/confirm",
    "/quotes/{quote_id}/reject",
    "/results",
    "/results/{result_id}",
    "/sequences",
    "/sequences/{sequence_id}",
    "/targets",
    "/targets/request-custom",
    "/targets/request-custom/{request_id}",
    "/targets/{target_id}",
    "/tokens",
    "/tokens/attenuate",
    "/tokens/revoke",
    "/updates",
}


@pytest.fixture(scope="module")
def spec() -> dict:
    base = os.environ["ADAPTYV_API_URL"].rstrip("/")
    headers = {}
    key = os.environ.get("ADAPTYV_API_KEY")
    if key:
        headers["Authorization"] = f"Bearer {key}"
    req = urllib.request.Request(f"{base}/openapi.json", headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


@pytest.fixture(scope="module")
def spec_paths(spec: dict) -> set:
    return {path.replace("/api/v1", "", 1) for path in spec["paths"]}


def test_spec_version_matches(spec: dict) -> None:
    """Deployed info.version must equal the version the SDK targets."""
    deployed = spec["info"]["version"]
    assert deployed == FOUNDRY_SPEC_VERSION, (
        f"Deployed spec is {deployed!r}, SDK targets {FOUNDRY_SPEC_VERSION!r}. "
        "Run `mise run gen:types` and bump FOUNDRY_SPEC_VERSION."
    )


def test_sdk_implements_every_spec_path(spec_paths: set) -> None:
    """Every endpoint in the spec must be implemented by the client."""
    missing = spec_paths - SDK_PATHS
    assert not missing, (
        f"Spec exposes endpoints the SDK does not implement: {sorted(missing)}. "
        "Add the client method and list its path in SDK_PATHS."
    )


def test_sdk_targets_no_unknown_paths(spec_paths: set) -> None:
    """The client must not target endpoints the spec no longer defines."""
    dead = SDK_PATHS - spec_paths
    assert not dead, (
        f"SDK targets endpoints absent from the spec: {sorted(dead)}. "
        "Remove the client method or update SDK_PATHS."
    )
