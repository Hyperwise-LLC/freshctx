# Contributing to FreshCtx

FreshCtx is owned and stewarded by Hyperwise LLC and welcomes focused contributions that preserve its core guarantees: explicit freshness states, deterministic evaluation, safe validation, local-first operation, and no required telemetry. Contributors retain rights to their contributions. By submitting a contribution, you agree that it is accepted under the project's Apache License 2.0. FreshCtx v0.1 does not require a Contributor License Agreement (CLA) or Developer Certificate of Origin (DCO).

## Contribution licensing

The same Apache-2.0 terms apply to project code and accepted contributions. Hyperwise LLC does not require contributors to grant separate proprietary relicensing rights for v0.1. Commercial services and possible future products remain separate from FreshCtx core.

If Hyperwise LLC later considers a genuine dual-licensing model, it will publish and review any proposed contribution terms before accepting code that would need those additional rights. Existing contributions will not silently receive new terms.

The Apache-2.0 software license does not grant rights to use FreshCtx™ names, logos, or branding beyond truthful reference to the project. See `TRADEMARKS.md`.

## Development setup

1. Use Python 3.10 or newer.
2. Create and activate a virtual environment.
3. Install the development dependencies in editable mode.
4. Run the test suite before submitting changes.

```console
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
python -m unittest discover -s tests -v
```

## Contribution requirements

- Add tests for behavioral changes.
- Preserve the normative requirements in the versioned `SPEC.md`.
- Treat validation as side-effect free.
- Never treat an unknown or failed check as `CURRENT`.
- Do not persist credentials or enable telemetry by default.
- Keep model and agent-framework integrations optional.

Open an issue before making a breaking API or data-schema change.

See `CODE_OF_CONDUCT.md`, `SECURITY.md`, and `SUPPORT.md` for the correct private reporting and support routes.
