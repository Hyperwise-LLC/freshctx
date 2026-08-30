# Bounded external validation reports

Use `ValidationReport` and `schemas/validation-report.schema.json` to record what an external test actually establishes.

Required fields identify the scenario, FreshCtx version, installation source, environment, expected and observed outcomes, verdict, limitations, and evidence locations. A report is evidence for that bounded scenario only; it is not a production, security, or compliance certification.

```python
from freshctx import ValidationReport

report = ValidationReport(
    scenario="approval changes before payment",
    freshctx_version="0.2.1",
    installation="pypi",
    environment={"python": "3.12", "os": "linux"},
    expected="payment is blocked",
    observed="STALE_REASONING; action not called",
    verdict="pass",
    limitations=("synthetic payment source",),
    evidence=("audit.jsonl",),
)
```

Publish negative and inconclusive outcomes as well as passes. Never merge a source reproduction and a clean PyPI installation into one claim.
