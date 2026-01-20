# Adaptyv SDK

Python SDK for the Adaptyv Foundry API - design and test protein binders with BindCraft, Germinal, and Design-A-Protein workflows.

## Installation

```bash
pip install adaptyv-sdk
```

## Quick Start

```python
from adaptyv import Lab

# Initialize with API key from environment
lab = Lab.setup()

# Create an experiment with the decorator pattern
@lab.experiment(target="PD-L1", workflow="bindcraft")
def design_binders():
    return ["MVKVGVNG...", "MKVLVAG..."]

result = design_binders()
print(f"Experiment: {result.experiment_url}")

# Or create directly
result = lab.create_experiment(
    name="My Experiment",
    sequences=["MVKVGVNG...", "MKVLVAG..."],
    target_id="target-uuid",
)
```

## Configuration

Set these environment variables:

```bash
export ADAPTYV_API_KEY=your_api_key_here
# Optional
export ADAPTYV_ORGANIZATION_ID=your_org_uuid
```

## Features

- **Lab Interface**: High-level `Lab.setup()` and `@lab.experiment` decorator
- **Foundry Client**: Low-level API client with retry and error handling
- **Workflows**: BindCraft, Germinal, and Design-A-Protein workflow adapters
- **Storage**: Local SQLite and Supabase storage adapters
- **Results**: Data package parsing and failure tracking

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
mise run test:fast

# Lint and format
mise run lint
mise run format

# Type check
mise run typecheck
```

## License

MIT
