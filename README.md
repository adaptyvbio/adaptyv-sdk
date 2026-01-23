<p align="center">
  <img src="assets/sdk_hero.svg" width="560" alt="Adaptyv SDK">
</p>

<p align="center">
  Run protein binding experiments from Python
</p>

<p align="center">
  <a href="#quick-start">Quick Start</a> •
  <a href="#features">Features</a> •
  <a href="#api-reference">API Reference</a> •
  <a href="#examples">Examples</a>
</p>

---

## Quick Start

<p align="center">
  <img src="assets/cli_demo_quickstart.svg" width="650" alt="Quickstart">
</p>

```bash
pip install adaptyv-sdk
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

---

## Configuration

Set your credentials as environment variables:

```bash
export ADAPTYV_API_KEY=your_api_key
export ADAPTYV_API_URL=https://api.adaptyvbio.com
export ADAPTYV_ORGANIZATION_ID=your_org_id  # Optional
```

Or configure programmatically:

```python
from adaptyv import Lab

lab = Lab.setup(
    api_key="your_api_key",
    base_url="https://api.adaptyvbio.com",
    organization_id="your_org_id",  # Optional
)
```

---

## API Reference

### List Targets

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

### Create Experiment

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

### Get Experiment Status

```python
from adaptyv import lab

result = lab.get_experiment("experiment-uuid")
print(f"Status: {result.status}")
```

### Confirm Experiment

```python
from adaptyv import lab

# Waits for quote, then confirms
result = lab.confirm_experiment("experiment-uuid")
print(f"Confirmed at: {result.confirmed_at}")
```

### Get Results

```python
from adaptyv import FoundryClient

client = FoundryClient(api_key="...", base_url="https://api.adaptyvbio.com")

# Retrieve results for a completed experiment
results = client.experiments.get_results("experiment-uuid")
for result in results.results:
    print(f"{result.title}: {result.result_type}")
```

---

## Examples

### Using the client directly

```python
from adaptyv import FoundryClient

client = FoundryClient(api_key="...", base_url="https://api.adaptyvbio.com")

# List experiments
experiments = client.experiments.list()

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
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Lint and format
ruff check src tests
ruff format src tests

# Type check
mypy src
```

