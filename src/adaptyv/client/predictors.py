"""Client for calling predictor endpoints via modal_server.py.

This module provides client functions to call predictors through the
Adaptyv Lab SDK Modal service, which requires Foundry API key authentication
and has access to Modal secrets for endpoint URLs.
"""

from __future__ import annotations

import logging
import os
import uuid
from typing import Any

import httpx

from adaptyv.config import get_sdk_service_url
from adaptyv.exceptions import AdaptyvLabError, AuthenticationError

logger = logging.getLogger(__name__)

# Default timeout for HTTP requests (seconds)
DEFAULT_TIMEOUT = 60.0


class PredictorClientError(AdaptyvLabError):
    """Error from predictor client."""

    pass


def _get_api_key() -> str:
    """Get Foundry API key from environment."""
    api_key = os.environ.get("ADAPTYV_API_KEY")
    if not api_key:
        raise AuthenticationError(
            "ADAPTYV_API_KEY environment variable not set. "
            "Set it to authenticate with the SDK service."
        )
    return api_key


async def _call_predictor_service(
    model_name: str,
    sequences: dict[str, str],
    params: dict[str, Any] | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    """Call the predictor service via modal_server.py.

    Args:
        model_name: Predictor model name (e.g., "solubility")
        sequences: Mapping of design_id to sequence
        params: Optional parameters for the predictor
        timeout: Request timeout in seconds

    Returns:
        Response from the predictor service

    Raises:
        PredictorClientError: If the request fails
    """
    service_url = get_sdk_service_url()
    if not service_url:
        raise PredictorClientError(
            "SDK_SERVICE_URL environment variable not set. "
            "When running in Modal, this is automatically provided by the 'adaptyv-lab-sdk-auth' secret. "
            "For local CLI usage, set SDK_SERVICE_URL environment variable."
        )

    api_key = _get_api_key()

    # Prepare request
    design_ids = list(sequences.keys())
    request_data = {
        "design_run_id": f"cli_{uuid.uuid4().hex[:12]}",
        "design_ids": design_ids,
        "sequences": sequences,
        "params": params or {},
    }

    # Normalize service URL (remove trailing slash)
    service_url = service_url.rstrip("/")
    endpoint_url = f"{service_url}/predictors/{model_name}/run"

    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            response = await client.post(
                endpoint_url,
                json=request_data,
                headers={"Authorization": f"Bearer {api_key}"},
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                raise AuthenticationError(
                    "Invalid Foundry API key. Check your ADAPTYV_API_KEY environment variable."
                ) from e
            # Try to extract error details from response
            error_detail = e.response.text
            try:
                error_json = e.response.json()
                # Try multiple possible error message fields
                error_detail = (
                    error_json.get("detail")
                    or error_json.get("error")
                    or error_json.get("message")
                    or error_json.get("error_message")
                    or str(error_json)
                )
                # If still generic, include full JSON
                if not error_detail or error_detail == "Internal Server Error":
                    error_detail = str(error_json)
            except Exception:
                pass  # Use text response if JSON parsing fails

            # Include full response text if detail is generic
            if not error_detail or error_detail == "Internal Server Error":
                full_text = e.response.text[:1000]  # First 1000 chars
                error_detail = f"{error_detail}\nFull response: {full_text}"

            raise PredictorClientError(
                f"HTTP error {e.response.status_code}: {error_detail}"
            ) from e
        except httpx.RequestError as e:
            raise PredictorClientError(f"Request failed: {e}") from e

        try:
            return response.json()
        except ValueError as e:
            raise PredictorClientError(f"Invalid JSON response: {response.text[:200]}") from e


async def predict_solubility_via_service(
    sequence: str,
    timeout: float = DEFAULT_TIMEOUT,
) -> dict[str, float]:
    """Predict protein solubility via SDK service.

    Args:
        sequence: Amino acid sequence
        timeout: Request timeout in seconds

    Returns:
        Dictionary with solubility_score
    """
    design_id = "single"
    response = await _call_predictor_service(
        model_name="solubility",
        sequences={design_id: sequence},
        params={"models": ["plm_sol"]},
        timeout=timeout,
    )

    # Extract result from response
    job_id = response.get("job_id")
    if not job_id:
        raise PredictorClientError("Response missing job_id")

    # modal_server.py runs predictions synchronously, so results are immediately available
    # Fetch results right away
    service_url = get_sdk_service_url().rstrip("/")
    api_key = _get_api_key()

    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            result_response = await client.get(
                f"{service_url}/predictors/jobs/{job_id}/results",
                headers={"Authorization": f"Bearer {api_key}"},
            )
            result_response.raise_for_status()
            results_data = result_response.json()
        except httpx.RequestError as e:
            raise PredictorClientError(f"Failed to get results: {e}") from e

        # Extract metrics from results
        results = results_data.get("results", [])
        if not results:
            # Check job status for error details
            error_details = None
            try:
                status_response = await client.get(
                    f"{service_url}/predictors/jobs/{job_id}/status",
                    headers={"Authorization": f"Bearer {api_key}"},
                )
                if status_response.status_code == 200:
                    status_data = status_response.json()
                    error_details = status_data.get("error")
                    logger.debug(f"Job status response: {status_data}")
                    if error_details:
                        raise PredictorClientError(f"Predictor job failed: {error_details}")
            except PredictorClientError:
                raise  # Re-raise if we already have the error
            except Exception as e:
                logger.debug(f"Failed to get job status: {e}")

            # If we have error details but didn't raise above, include it
            error_msg = f"No results returned from predictor service. Job ID: {job_id}."
            if error_details:
                error_msg += f" Error: {error_details}"
            else:
                error_msg += " Check Modal logs for details."
            raise PredictorClientError(error_msg)

        # Find result for our design_id
        result = next((r for r in results if r.get("design_id") == design_id), None)
        if not result:
            raise PredictorClientError(
                f"Result not found for design_id '{design_id}'. "
                f"Available design_ids: {[r.get('design_id') for r in results]}"
            )

        metrics = result.get("metrics", {})
        solubility_score = metrics.get("solubility_score") or metrics.get(
            "plm_sol_solubility_score"
        )

        if solubility_score is None:
            raise PredictorClientError("Solubility score not found in results")

        return {"solubility_score": float(solubility_score)}


async def predict_expression_rp3net_via_service(
    sequence: str,
    timeout: float = DEFAULT_TIMEOUT,
) -> dict[str, float]:
    """Predict protein expression via RP3Net using SDK service.

    Args:
        sequence: Amino acid sequence
        timeout: Request timeout in seconds

    Returns:
        Dictionary with expression_score
    """
    design_id = "single"
    response = await _call_predictor_service(
        model_name="solubility",  # Uses the solubility predictor which supports rp3net
        sequences={design_id: sequence},
        params={"models": ["rp3net"]},
        timeout=timeout,
    )

    job_id = response.get("job_id")
    if not job_id:
        raise PredictorClientError("Response missing job_id")

    # Get results
    service_url = get_sdk_service_url().rstrip("/")
    api_key = _get_api_key()

    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            result_response = await client.get(
                f"{service_url}/predictors/jobs/{job_id}/results",
                headers={"Authorization": f"Bearer {api_key}"},
            )
            result_response.raise_for_status()
            results_data = result_response.json()
        except httpx.RequestError as e:
            raise PredictorClientError(f"Failed to get results: {e}") from e

        # Extract metrics from results
        results = results_data.get("results", [])
        if not results:
            # Check job status for error details
            error_details = None
            try:
                status_response = await client.get(
                    f"{service_url}/predictors/jobs/{job_id}/status",
                    headers={"Authorization": f"Bearer {api_key}"},
                )
                if status_response.status_code == 200:
                    status_data = status_response.json()
                    error_details = status_data.get("error")
                    logger.debug(f"Job status response: {status_data}")
                    if error_details:
                        raise PredictorClientError(f"Predictor job failed: {error_details}")
            except PredictorClientError:
                raise  # Re-raise if we already have the error
            except Exception as e:
                logger.debug(f"Failed to get job status: {e}")

            # If we have error details but didn't raise above, include it
            error_msg = f"No results returned from predictor service. Job ID: {job_id}."
            if error_details:
                error_msg += f" Error: {error_details}"
            else:
                error_msg += " Check Modal logs for details."
            raise PredictorClientError(error_msg)

        result = next((r for r in results if r.get("design_id") == design_id), None)
        if not result:
            raise PredictorClientError(
                f"Result not found for design_id '{design_id}'. "
                f"Available design_ids: {[r.get('design_id') for r in results]}"
            )

        metrics = result.get("metrics", {})
        expression_score = metrics.get("expression_prediction") or metrics.get(
            "rp3net_expression_score"
        )

        if expression_score is None:
            raise PredictorClientError("Expression score not found in results")

        return {"expression_score": float(expression_score)}
