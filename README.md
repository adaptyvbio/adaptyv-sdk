<p align="center">
  <img src="assets/sdk_hero.svg" width="560" alt="Adaptyv SDK">
</p>

<p align="center">
  Run protein binding experiments from Python
</p>

<p align="center">
  <a href="#quick-start">Quick start</a> •
  <a href="#features">Features</a> •
  <a href="#api-reference">API reference</a> •
  <a href="#examples">Examples</a>
</p>

---

## Quick start

<p align="center">
  <img src="assets/cli_demo_quickstart.svg" width="650" alt="Quickstart">
</p>

```bash
git clone https://github.com/adaptyvbio/adaptyv-sdk.git
cd adaptyv-sdk
pip install -e .
```

```python
from adaptyv import lab

# Uses ADAPTYV_API_KEY and ADAPTYV_API_URL from your environment

@lab.experiment(target="PD-L1")
def design_binders():
    return {
        "design_a": "MVKVGVNG...",
        "design_b": "MKVLVAG...",
    }

result = design_binders()
print(f"Experiment: {result.experiment_url}")

# Additional decorator parameters:
# @lab.experiment(
#     target="PD-L1",
#     auto_confirm=True,              # Auto-confirm quote
#     experiment_type="screening",    # screening/affinity/thermostability/fluorescence/expression
#     method="bli",                   # bli/spr
#     n_replicates=3,                 # Number of replicates
# )
```

---

## Features

- Picks up `ADAPTYV_API_KEY` and `ADAPTYV_API_URL` from environment
- Retries on failure with exponential backoff
- Signature verification for incoming webhooks
- Type hints throughout
- Context managers for cleanup
- Requires Python 3.11+

---

## Configuration

Set your credentials as environment variables:

```bash
export ADAPTYV_API_KEY=your_api_key
export ADAPTYV_API_URL=https://foundry-api-public.adaptyvbio.com/api/v1
export ADAPTYV_ORGANIZATION_ID=your_org_id  # Optional
```

Or configure programmatically:

```python
from adaptyv import Lab

lab = Lab.setup(
    api_key="your_api_key",
    base_url="https://foundry-api-public.adaptyvbio.com/api/v1",
    organization_id="your_org_id",  # Optional
)
```

---

## API reference

### List targets

```python
from adaptyv import lab

# Single page
targets = lab.list_targets()

# Iterate through all pages
for target in lab.list_all_targets():
    print(target["name"])

# Search
results = lab.search_targets("PD-L1")
```

### Create experiment

```python
from adaptyv import lab

result = lab.create_experiment(
    name="My Experiment",
    sequences={
        "clone_1": "MVKVGVNG...",
        "clone_2": "MKVLVAG...",
    },
    target_id="...",  # from targets list
    experiment_type="screening",
)

print(f"Created: {result.experiment_url}")
```

### Get experiment status

```python
from adaptyv import lab

result = lab.get_experiment("experiment-uuid")
print(f"Status: {result.status}")
```

### Confirm experiment

```python
from adaptyv import lab

# Waits for quote, then confirms
result = lab.confirm_experiment("experiment-uuid")
print(f"Confirmed at: {result.confirmed_at}")
```

### Get results

```python
from adaptyv import FoundryClient

client = FoundryClient(api_key="...", base_url="https://foundry-api-public.adaptyvbio.com/api/v1")

# Retrieve results for a completed experiment
results = client.experiments.get_results("experiment-uuid")
for result in results.items:
    print(f"{result.title}: {result.result_type}")
```

### Verify webhooks

Pass a `webhook_url` when you create an experiment and Foundry POSTs status updates
to it instead of making you poll. Every delivery is signed, so check the signature
before trusting the payload:

```python
from adaptyv.exceptions import WebhookPayloadError, WebhookVerificationError
from adaptyv.webhooks import verify

try:
    # raw_body must be the bytes that arrived, not a parsed or re-serialized payload
    event = verify(raw_body, request_headers, WEBHOOK_SECRET)
except WebhookVerificationError:
    ...  # not from Foundry, or damaged in transit: reject it
except WebhookPayloadError:
    ...  # signed by Foundry, but the envelope did not parse: log it, let it retry

print(event.event)        # "experiment_update"
print(event.delivery_id)  # "019b8da3-4a91-16c6-fa94-619212bee6a6"
print(event.payload["data"]["experiment_code"])
```

`verify` never returns a boolean. It raises, and which exception it raises is what
you branch on:

| Exception | Meaning | Answer with |
| --- | --- | --- |
| `WebhookVerificationError` | A missing or malformed `X-Adaptyv-Signature`, a signature that does not match the body, an empty secret, or a body that is not raw bytes. The delivery never proved it came from Foundry. | 4xx |
| `WebhookPayloadError` | The signature checked out, but the envelope was not readable JSON carrying an `event` and a `delivery_id`. | 5xx, or accept and log |

The split matters because 4xx is permanent in the retry model. Answering 4xx to a
genuinely signed delivery whose shape you did not expect throws away a real event and
tells Foundry never to send it again. The two are siblings rather than parent and
child, so catching one cannot swallow the other by accident.

`event.payload` is the whole envelope exactly as it arrived, so fields the SDK does
not know about pass through untouched.

With FastAPI:

```python
import logging
import os

from fastapi import FastAPI, Request, Response

from adaptyv.exceptions import WebhookPayloadError, WebhookVerificationError
from adaptyv.webhooks import verify

app = FastAPI()
WEBHOOK_SECRET = os.environ["WEBHOOK_SECRET"]


@app.post("/foundry-hook")
async def foundry_hook(request: Request) -> Response:
    try:
        event = verify(await request.body(), request.headers, WEBHOOK_SECRET)
    except WebhookVerificationError:
        return Response(status_code=400)  # permanent, and correctly so
    except WebhookPayloadError:
        logging.exception("unreadable webhook envelope")
        return Response(status_code=500)  # genuinely ours, so let it come back

    handle(event)  # your code, keyed on event.delivery_id
    return Response(status_code=200)
```

`await request.body()` hands back the raw bytes. Reading `await request.json()` and
re-serializing it produces different bytes than the ones that were signed, so the
signature would never match. The equivalent accessor is `request.get_data()` on
Flask and `request.body` on Django.

**Handlers have to be idempotent.** A delivery is retried up to three times with
exponential backoff on network errors and 5xx responses, so a handler that fails
once is guaranteed to see the same event again. `event.delivery_id` is stable across
those attempts, which makes it the key to deduplicate on in whatever store you
already have. The SDK deliberately does not keep one for you. Return 2xx to
acknowledge a delivery; a 4xx tells Foundry the failure is permanent and stops the
retries.

---

## Examples

### Using the client directly

```python
from adaptyv import FoundryClient

client = FoundryClient(api_key="...", base_url="https://foundry-api-public.adaptyvbio.com/api/v1")

# List experiments (paginated; iterate .items)
experiments = client.experiments.list()
for exp in experiments.items:
    print(exp.code, exp.status)

# Filter and sort (grammar: eq(field,value), in(field,a,b), and(...), or(...))
done = client.experiments.list(filter="eq(status,done)", sort="-created_at")

# Get cost estimate before creating
estimate = client.experiments.cost_estimate({
    "experiment_type": "screening",
    "target_id": "...",
    "sequences": {"seq1": "MVKVG..."},
})

# Get experiment quote
quote = client.experiments.get_quote("experiment-uuid")

# Get invoice
invoice = client.experiments.get_invoice("experiment-uuid")

# List status updates
updates = client.experiments.list_updates("experiment-uuid")
```

---

## Development

```bash
# Install dependencies (uses uv)
uv sync --extra dev

# Run all checks (lint, type-check, fast tests)
mise run check

# Or run individually
uv run pytest
uv run ruff check src tests
uv run mypy src
```

### Staying in sync with the API

The SDK is pegged to the deployed OpenAPI spec
(`https://foundry-api-public.adaptyvbio.com/api/v1/openapi.json`):

- `src/adaptyv/types/generated.py` is generated from the spec — don't edit it by
  hand; run `mise run gen:types` to rebuild it (output is deterministic).
- `mise run gen:check` regenerates and diffs, failing if the committed types are
  stale versus the live spec.
- `FOUNDRY_SPEC_VERSION` records the targeted `info.version`. The contract tests
  in `tests/test_spec_contract.py` assert the deployed version still matches and
  that the client implements exactly the spec's endpoints.
- CI runs the offline checks on every push and the drift checks on a schedule,
  so an API change surfaces as a failed build instead of silent drift. When it
  fires: run `mise run gen:types`, bump `FOUNDRY_SPEC_VERSION`, add any new
  client method, and commit.
