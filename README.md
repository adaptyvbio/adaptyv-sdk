<p align="center">
  <img src="assets/sdk_hero.svg" width="560" alt="Adaptyv SDK">
</p>

<p align="center">
  Python SDK for AI-powered protein binding experiments
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

# Zero configuration - reads ADAPTYV_API_KEY and ADAPTYV_API_URL from environment

@lab.experiment(target="PD-L1")
def design_binders():
    return ["MVKVGVNG...", "MKVLVAG..."]

result = design_binders()
print(f"Experiment: {result.experiment_url}")
```

---

## Features

- **Zero-config initialization** - reads `ADAPTYV_API_KEY` and `ADAPTYV_API_URL` from environment
- **Automatic retry** - exponential backoff with jitter for rate limits and server errors
- **Type-safe** - full IDE support with type hints
- **Context manager support** - automatic resource cleanup

---

## Workflow

<p align="center">
  <img src="assets/api_flow.svg" width="550" alt="API Flow">
</p>

---

## Configuration

Set your credentials as environment variables:

```bash
export ADAPTYV_API_KEY=your_api_key
export ADAPTYV_API_URL=https://api.adaptyvbio.com
```

Or configure programmatically:

```python
from adaptyv import Lab

lab = Lab.setup(api_key="your_api_key", base_url="https://api.adaptyvbio.com")
```

---

## API Reference

### List Targets

```python
from adaptyv import lab

# Single page
targets = lab.list_targets()

# All targets with automatic pagination
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
    sequences=["MVKVGVNG...", "MKVLVAG..."],
    target_id="...",  # From targets catalog
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

# Waits for quote to be ready, then confirms
result = lab.confirm_experiment("experiment-uuid")
print(f"Confirmed at: {result.confirmed_at}")
```

---

## Examples

### Low-Level Client

For advanced usage, use the `FoundryClient` directly:

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
```

### Error Handling

```python
from adaptyv import lab, AuthenticationError, NotFoundError, RateLimitError

try:
    result = lab.create_experiment(...)
except AuthenticationError:
    print("Invalid API key")
except NotFoundError as e:
    print(f"Resource not found: {e}")
except RateLimitError as e:
    print(f"Rate limited, retry after {e.retry_after}s")
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

---

## License

MIT
