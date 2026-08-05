"""Tests for webhook signature verification."""

import hashlib
import hmac
import json

import pytest

from adaptyv import webhooks
from adaptyv.exceptions import WebhookPayloadError, WebhookVerificationError
from adaptyv.webhooks import verify

SECRET = "whsec_test_secret"

# Envelope shape documented at https://docs.adaptyvbio.com/api-reference/api-introduction
PAYLOAD = {
    "delivery_id": "019b8da3-4a91-16c6-fa94-619212bee6a6",
    "event": "experiment_update",
    "timestamp": "2026-07-01T14:30:00Z",
    "api_version": "2026-02",
    "data": {
        "type": "experiment.update",
        "experiment_id": "019d4a2b-2b7e-7c3a-9f1e-2a4b6c8d0e1f",
        "experiment_code": "ORG-001-123",
        "organization_id": "11111111-1111-1111-1111-111111111111",
        "update_id": "019d4a2c-3c8f-7d4b-a02f-3b5c7d9e1f20",
        "name": "Materials received",
        "description": "Your target protein arrived and QC passed.",
        "update_type": "progress",
        "eta": "2026-07-15T00:00:00Z",
        "created_at": "2026-07-01T14:30:00Z",
    },
}
BODY = json.dumps(PAYLOAD).encode()


def sign(body: bytes, secret: str = SECRET) -> str:
    """Build an X-Adaptyv-Signature header the way the Foundry API does."""
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


DIGEST_HEX = hmac.new(SECRET.encode(), BODY, hashlib.sha256).hexdigest()


def headers_for(body: bytes, secret: str = SECRET) -> dict[str, str]:
    """Build the three headers that accompany a delivery."""
    return {
        "X-Adaptyv-Event": PAYLOAD["event"],
        "X-Adaptyv-Delivery-Id": PAYLOAD["delivery_id"],
        "X-Adaptyv-Signature": sign(body, secret),
    }


class TestVerify:
    """Test the happy path."""

    def test_returns_event_for_valid_signature(self) -> None:
        """A correctly signed delivery yields the event, delivery id, and payload."""
        event = verify(BODY, headers_for(BODY), SECRET)

        assert event.event == "experiment_update"
        assert event.delivery_id == "019b8da3-4a91-16c6-fa94-619212bee6a6"
        assert event.payload == PAYLOAD


class TestSignatureMismatch:
    """Test that a signature which does not match the body is refused."""

    def test_rejects_signature_made_with_another_secret(self) -> None:
        """A delivery signed with a different secret is refused."""
        with pytest.raises(WebhookVerificationError, match="signature does not match"):
            verify(BODY, headers_for(BODY, "a-different-secret"), SECRET)

    def test_rejects_body_edited_after_signing(self) -> None:
        """A body modified in transit no longer matches its signature."""
        signed_headers = headers_for(BODY)
        tampered = BODY.replace(b'"update_type": "progress"', b'"update_type": "final"')

        with pytest.raises(WebhookVerificationError, match="signature does not match"):
            verify(tampered, signed_headers, SECRET)


class TestRawBodyRequired:
    """Test failure mode 1: signing anything other than the bytes that arrived."""

    def test_rejects_str_body(self) -> None:
        """A decoded str is refused instead of being re-encoded on the caller's behalf."""
        with pytest.raises(WebhookVerificationError, match="raw request body"):
            verify(BODY.decode(), headers_for(BODY), SECRET)

    def test_rejects_parsed_dict_body(self) -> None:
        """A parsed payload is refused, so request.json() cannot be passed in by mistake."""
        with pytest.raises(WebhookVerificationError, match="raw request body"):
            verify(PAYLOAD, headers_for(BODY), SECRET)

    def test_reserialized_body_fails_verification(self) -> None:
        """Re-serializing changes the bytes, which is why only the raw body can be signed."""
        reserialized = json.dumps(PAYLOAD, sort_keys=True, separators=(",", ":")).encode()
        assert reserialized != BODY

        with pytest.raises(WebhookVerificationError, match="signature does not match"):
            verify(reserialized, headers_for(BODY), SECRET)


class TestSecretRequired:
    """Test failure mode 3: an unset secret that makes verification pass.

    Each delivery here is signed with the same unusable secret it is verified
    against, so the HMAC genuinely matches. Without the guard these calls
    return an event instead of raising, which is the point: the control
    disarms itself and still looks like it is working.
    """

    def test_rejects_empty_secret_whose_signature_matches(self) -> None:
        """An empty secret signs and verifies anything, so it is refused up front."""
        with pytest.raises(WebhookVerificationError, match="secret must be a non-empty string"):
            verify(BODY, headers_for(BODY, ""), "")

    def test_rejects_whitespace_only_secret_whose_signature_matches(self) -> None:
        """A secret of blanks is as unset as an empty one."""
        with pytest.raises(WebhookVerificationError, match="secret must be a non-empty string"):
            verify(BODY, headers_for(BODY, "   "), "   ")

    def test_rejects_none_secret(self) -> None:
        """os.environ.get returns None for an unset variable, so None must be refused."""
        with pytest.raises(WebhookVerificationError, match="secret must be a non-empty string"):
            verify(BODY, headers_for(BODY), None)

    def test_rejects_non_str_secret(self) -> None:
        """A bytes secret is refused rather than raising AttributeError on .encode()."""
        with pytest.raises(WebhookVerificationError, match="secret must be a non-empty string"):
            verify(BODY, headers_for(BODY), SECRET.encode())


class TestSignatureHeader:
    """Test failure mode 4: a signature header that cannot be parsed.

    Every case is a refusal carrying WebhookVerificationError. None of them may
    surface a bare TypeError or ValueError, because a handler that only catches
    the SDK error would then answer 500 and earn itself a retry.
    """

    def test_rejects_missing_signature_header(self) -> None:
        """A delivery with no X-Adaptyv-Signature is refused."""
        headers = headers_for(BODY)
        del headers["X-Adaptyv-Signature"]

        with pytest.raises(WebhookVerificationError, match="X-Adaptyv-Signature header is missing"):
            verify(BODY, headers, SECRET)

    def test_rejects_signature_without_prefix(self) -> None:
        """A bare hex digest with no algorithm prefix is refused."""
        headers = headers_for(BODY)
        headers["X-Adaptyv-Signature"] = DIGEST_HEX

        with pytest.raises(WebhookVerificationError, match="must be formatted as 'sha256=<hex>'"):
            verify(BODY, headers, SECRET)

    def test_rejects_unexpected_algorithm_prefix(self) -> None:
        """Only sha256 is accepted, so a relabelled digest cannot downgrade the check."""
        headers = headers_for(BODY)
        headers["X-Adaptyv-Signature"] = f"sha512={DIGEST_HEX}"

        with pytest.raises(WebhookVerificationError, match="must be formatted as 'sha256=<hex>'"):
            verify(BODY, headers, SECRET)

    def test_rejects_non_hex_digest(self) -> None:
        """A digest that is not hex is refused instead of raising ValueError."""
        headers = headers_for(BODY)
        headers["X-Adaptyv-Signature"] = "sha256=" + "z" * 64

        with pytest.raises(WebhookVerificationError, match="is not valid hex"):
            verify(BODY, headers, SECRET)

    def test_rejects_odd_length_hex_digest(self) -> None:
        """An odd number of hex characters cannot decode, and is refused."""
        headers = headers_for(BODY)
        headers["X-Adaptyv-Signature"] = f"sha256={DIGEST_HEX[:-1]}"

        with pytest.raises(WebhookVerificationError, match="is not valid hex"):
            verify(BODY, headers, SECRET)

    def test_rejects_truncated_digest(self) -> None:
        """A digest of the wrong length is refused as malformed, not as a mismatch."""
        headers = headers_for(BODY)
        headers["X-Adaptyv-Signature"] = f"sha256={DIGEST_HEX[:32]}"

        with pytest.raises(WebhookVerificationError, match="must be 32 bytes"):
            verify(BODY, headers, SECRET)

    def test_rejects_empty_signature_header(self) -> None:
        """An empty header value is refused rather than treated as absent."""
        headers = headers_for(BODY)
        headers["X-Adaptyv-Signature"] = ""

        with pytest.raises(WebhookVerificationError, match="must be formatted as 'sha256=<hex>'"):
            verify(BODY, headers, SECRET)


class TestTimingSafeComparison:
    """Test failure mode 2: deciding the comparison with == instead of hmac.

    Counting calls to hmac.compare_digest would show only that it ran, and code
    that calls it and then branches on == of its own would sail through such a
    check. So the first two tests stub the comparison out and assert on what
    its answer does: rewrite the branch as == and the stub goes unconsulted,
    turning both red. The third test pins which primitive is being called,
    which is the part that makes the comparison constant time.
    """

    def test_rejects_a_valid_delivery_when_the_comparison_returns_false(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A correctly signed delivery is refused when the comparison says no."""
        monkeypatch.setattr(hmac, "compare_digest", lambda left, right: False)

        with pytest.raises(WebhookVerificationError, match="signature does not match"):
            verify(BODY, headers_for(BODY), SECRET)

    def test_accepts_a_mismatched_delivery_when_the_comparison_returns_true(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A body whose digest does not match is accepted when the comparison says yes.

        Nothing anyone wants in production, and that is the point: it is the
        other half of the proof that the comparison's answer is the only thing
        gating a delivery, so a second == test ANDed alongside it has nowhere
        to hide.
        """
        monkeypatch.setattr(hmac, "compare_digest", lambda left, right: True)
        tampered = BODY.replace(b'"update_type": "progress"', b'"update_type": "final"')

        event = verify(tampered, headers_for(BODY), SECRET)

        # Asserted on a field that differs between the two bodies, so this
        # cannot pass on the strength of the original body having been parsed.
        assert event.payload["data"]["update_type"] == "final"

    def test_calls_hmac_compare_digest_once(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The primitive doing the comparing is hmac.compare_digest."""
        calls: list[tuple[bytes, bytes]] = []
        real_compare_digest = hmac.compare_digest

        def spy(left: bytes, right: bytes) -> bool:
            calls.append((left, right))
            return real_compare_digest(left, right)

        monkeypatch.setattr(hmac, "compare_digest", spy)

        event = verify(BODY, headers_for(BODY), SECRET)

        assert event.delivery_id == PAYLOAD["delivery_id"]
        assert len(calls) == 1

    def test_compares_decoded_digests_so_hex_casing_is_irrelevant(self) -> None:
        """An uppercase hex digest verifies, because the comparison is over bytes."""
        headers = headers_for(BODY)
        headers["X-Adaptyv-Signature"] = f"sha256={DIGEST_HEX.upper()}"

        assert verify(BODY, headers, SECRET).payload == PAYLOAD


class TestPayloadParsing:
    """Test that an unreadable envelope is not reported as a failed signature.

    Everything here is signed correctly, so the delivery provably came from
    Foundry and only its shape is the problem. That has to raise something
    other than WebhookVerificationError: handlers answer 4xx to a failed
    signature, 4xx is permanent in the retry model, and a real event told never
    to resend is gone for good. WebhookPayloadError is a sibling rather than a
    subclass precisely so that except WebhookVerificationError cannot swallow
    it.
    """

    def test_rejects_body_that_is_not_json(self) -> None:
        """A signed body that will not parse is refused, not raised as JSONDecodeError."""
        body = b"not json at all"

        with pytest.raises(WebhookPayloadError, match="is not valid JSON"):
            verify(body, headers_for(body), SECRET)

    def test_rejects_json_that_is_not_an_object(self) -> None:
        """A JSON array is valid JSON but not an envelope."""
        body = b'["experiment_update"]'

        with pytest.raises(WebhookPayloadError, match="must be a JSON object"):
            verify(body, headers_for(body), SECRET)

    def test_rejects_envelope_without_event(self) -> None:
        """WebhookEvent.event is typed str, so a missing event is refused, not None."""
        body = json.dumps({"delivery_id": PAYLOAD["delivery_id"]}).encode()

        with pytest.raises(WebhookPayloadError, match="'event'") as excinfo:
            verify(body, headers_for(body), SECRET)

        assert not isinstance(excinfo.value, WebhookVerificationError)

    def test_rejects_envelope_without_delivery_id(self) -> None:
        """WebhookEvent.delivery_id is typed str, so a missing id is refused, not None."""
        body = json.dumps({"event": PAYLOAD["event"]}).encode()

        with pytest.raises(WebhookPayloadError, match="'delivery_id'") as excinfo:
            verify(body, headers_for(body), SECRET)

        assert not isinstance(excinfo.value, WebhookVerificationError)

    def test_passes_unknown_envelope_fields_through_untouched(self) -> None:
        """Fields the SDK does not know about survive on payload, so the shape can move."""
        body = json.dumps({**PAYLOAD, "unrecognised_field": {"added": "later"}}).encode()

        event = verify(body, headers_for(body), SECRET)

        assert event.payload["unrecognised_field"] == {"added": "later"}

    def test_reports_the_signature_failure_for_a_body_that_is_also_unparseable(self) -> None:
        """A bad signature is the complaint, even when the body would not parse either."""
        body = b"not json at all"

        with pytest.raises(WebhookVerificationError, match="signature does not match"):
            verify(body, headers_for(body, "a-different-secret"), SECRET)

    def test_does_not_parse_an_unverified_body(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The parser is never reached for a body whose signature did not check out.

        Asserting on the error message alone would not pin this: code that
        parses first and reports the signature failure afterwards produces the
        same message while still feeding untrusted bytes to the parser.
        """
        parsed: list[bytes] = []
        monkeypatch.setattr(webhooks, "_parse_payload", parsed.append)

        with pytest.raises(WebhookVerificationError, match="signature does not match"):
            verify(BODY, headers_for(BODY, "a-different-secret"), SECRET)

        assert parsed == []


class TestDeliveryMetadata:
    """Test failure mode 5: retries guarantee duplicates, so handlers need the id.

    The signature covers the body alone, which leaves X-Adaptyv-Event and
    X-Adaptyv-Delivery-Id unauthenticated. The event therefore reports the
    values carried inside the signed body, so a handler deduping on
    event.delivery_id is keyed on something a sender cannot forge.
    """

    def test_exposes_delivery_id_and_event_from_the_signed_body(self) -> None:
        """Body values win over the headers, which the signature does not cover."""
        headers = headers_for(BODY)
        headers["X-Adaptyv-Delivery-Id"] = "00000000-0000-0000-0000-000000000000"
        headers["X-Adaptyv-Event"] = "attacker_chosen_event"

        event = verify(BODY, headers, SECRET)

        assert event.delivery_id == PAYLOAD["delivery_id"]
        assert event.event == PAYLOAD["event"]


class TestHeaderLookup:
    """Test that header casing does not decide whether a delivery verifies."""

    def test_accepts_lowercased_header_names(self) -> None:
        """dict(request.headers) lowercases names in several frameworks."""
        headers = {name.lower(): value for name, value in headers_for(BODY).items()}

        assert verify(BODY, headers, SECRET).event == "experiment_update"
