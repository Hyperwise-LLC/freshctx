# Contributing to FreshCtx

FreshCtx welcomes focused contributions that preserve its core guarantees: explicit freshness states, deterministic evaluation, safe validation, local-first operation, and no required telemetry.

## Development setup

1. Use Python 3.10 or newer.
2. Create and activate a virtual environment.
3. Install the package in editable mode.
4. Run the test suite before submitting changes.

```console
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
python -m unittest discover -s tests -v
```

## Contribution requirements

- Add tests for behavioral changes.
- Preserve the normative requirements in `docs/FreshCtx_v0.1_Technical_Specification.docx`.
- Treat validation as side-effect free.
- Never treat an unknown or failed check as `CURRENT`.
- Do not persist credentials or enable telemetry by default.
- Keep model and agent-framework integrations optional.

Open an issue before making a breaking API or data-schema change.
