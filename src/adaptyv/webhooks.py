"""Webhook signature verification for Foundry deliveries.

Foundry POSTs signed events to the webhook_url registered on an experiment.
Each delivery carries X-Adaptyv-Signature, which is "sha256=<hex>" over the
HMAC-SHA256 of the raw request body, alongside X-Adaptyv-Event and
X-Adaptyv-Delivery-Id. The contract is documented at
https://docs.adaptyvbio.com/api-reference/api-introduction.

verify() is framework-agnostic on purpose: hand it the raw body bytes, the
request headers, and the webhook secret, and it either returns a WebhookEvent
or raises WebhookVerificationError. The README has FastAPI and framework-free
handlers built on it.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from adaptyv.exceptions import WebhookPayloadError, WebhookVerificationError

SIGNATURE_HEADER = "X-Adaptyv-Signature"

_SIGNATURE_PREFIX = "sha256="
_DIGEST_SIZE = hashlib.sha256().digest_size


@dataclass(frozen=True)
class WebhookEvent:
    """A webhook delivery whose signature has been verified.

    Attributes:
        event: Event slug, for example "experiment_update".
        delivery_id: Unique id for this delivery attempt. Foundry retries a
            failed delivery up to three times, so a handler that errors once
            will see this id again and should use it as its dedupe key.
        payload: The whole parsed envelope, including timestamp, api_version,
            and the nested data object.
    """

    event: str
    delivery_id: str
    payload: dict[str, Any]


def _get_header(headers: Mapping[str, str], name: str) -> str | None:
    """Look up a header without depending on the caller's capitalization.

    Frameworks disagree here: httpx and Starlette hand back case-insensitive
    mappings, while dict(request.headers) hands back whatever casing arrived on
    the wire. HTTP header names are case-insensitive, so this treats them so.
    """
    value = headers.get(name)
    if value is not None:
        return value

    wanted = name.lower()
    for key, candidate in headers.items():
        if key.lower() == wanted:
            return candidate
    return None


def _parse_signature(headers: Mapping[str, str]) -> bytes:
    """Decode the digest carried by the signature header.

    Returns the digest decoded to bytes rather than the hex text it arrived as,
    so the comparison cannot turn on the casing the sender chose.

    Raises:
        WebhookVerificationError: The header is absent or cannot be parsed.
    """
    header = _get_header(headers, SIGNATURE_HEADER)
    if header is None:
        raise WebhookVerificationError(f"{SIGNATURE_HEADER} header is missing from the delivery")

    if not header.startswith(_SIGNATURE_PREFIX):
        raise WebhookVerificationError(
            f"{SIGNATURE_HEADER} must be formatted as 'sha256=<hex>', got {header!r}"
        )

    hex_digest = header[len(_SIGNATURE_PREFIX) :]
    try:
        digest = bytes.fromhex(hex_digest)
    except ValueError as exc:
        raise WebhookVerificationError(
            f"{SIGNATURE_HEADER} digest is not valid hex: {hex_digest!r}"
        ) from exc

    if len(digest) != _DIGEST_SIZE:
        raise WebhookVerificationError(
            f"{SIGNATURE_HEADER} digest must be {_DIGEST_SIZE} bytes, got {len(digest)}"
        )
    return digest


def _parse_payload(body: bytes) -> dict[str, Any]:
    """Parse an already verified body into an event envelope.

    Raises:
        WebhookPayloadError: The body is not a JSON object. Not a verification
            failure: the signature already proved where these bytes came from.
    """
    try:
        payload = json.loads(body)
    except ValueError as exc:
        raise WebhookPayloadError(f"Webhook body is not valid JSON: {exc}") from exc

    if not isinstance(payload, dict):
        raise WebhookPayloadError(
            f"Webhook body must be a JSON object, got {type(payload).__name__}"
        )
    return payload


def _required_str(payload: dict[str, Any], key: str) -> str:
    """Read an envelope field that WebhookEvent types as str.

    Raises:
        WebhookPayloadError: The field is absent or is not a string.
    """
    value = payload.get(key)
    if not isinstance(value, str):
        raise WebhookPayloadError(f"Webhook payload has no string {key!r} field")
    return value


def verify(body: bytes, headers: Mapping[str, str], secret: str) -> WebhookEvent:
    """Verify a webhook delivery and return the event it carries.

    Args:
        body: The raw request body, exactly as it arrived. A str or an already
            parsed payload is refused, because re-serializing a payload changes
            the bytes the signature was computed over.
        headers: The request headers, looked up case-insensitively.
        secret: The webhook secret for this endpoint.

    Returns:
        The verified event. Its event name and delivery id come from the signed
        body, not from the X-Adaptyv-Event and X-Adaptyv-Delivery-Id headers,
        which the signature does not cover. The whole envelope is exposed
        unchanged on payload, so fields this SDK does not know about pass
        through rather than being dropped.

    Raises:
        WebhookVerificationError: The delivery did not prove it came from
            Foundry. The body is not bytes, the secret is empty, the signature
            header is missing or malformed, or the signature does not match.
            Answer 4xx: resending would not help.
        WebhookPayloadError: The signature checked out but the envelope could
            not be read. Answer 5xx or accept and log, never 4xx, or a genuine
            event is discarded and the API is told not to retry it.
    """
    if not isinstance(body, bytes):
        raise WebhookVerificationError(
            "Webhook body must be the raw request body as bytes, got "
            f"{type(body).__name__}. Re-serializing a parsed payload produces "
            "different bytes than the ones that were signed."
        )

    if not isinstance(secret, str) or not secret.strip():
        raise WebhookVerificationError(
            "Webhook secret must be a non-empty string. An unset secret still "
            "produces a valid HMAC, so verification would pass for every request "
            "instead of failing closed."
        )

    provided = _parse_signature(headers)
    expected = hmac.new(secret.encode(), body, hashlib.sha256).digest()
    if not hmac.compare_digest(expected, provided):
        raise WebhookVerificationError("Webhook signature does not match the request body")

    # Parsed only after the signature checks out, so an unverified body never
    # reaches the JSON parser.
    payload = _parse_payload(body)
    return WebhookEvent(
        event=_required_str(payload, "event"),
        delivery_id=_required_str(payload, "delivery_id"),
        payload=payload,
    )
