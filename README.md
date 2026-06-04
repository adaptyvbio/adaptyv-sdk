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

