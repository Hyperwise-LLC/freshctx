# Adapter contract

An adapter exposes `observe(locator, **options) -> ObservationToken` and `validate(token) -> AdapterResult`. Validation must be read-only, bounded by a timeout where external I/O is involved, deterministic for equivalent evidence, and return only `equivalent`, `changed`, or `indeterminate`.

Adapters must not persist plaintext credentials in tokens or audit events. A missing credential, unavailable validator, timeout, permission error, malformed response, unsafe/non-idempotent MCP operation, or unsupported state returns `indeterminate`; it must not be treated as current. Adapter implementations own canonicalization and evidence-specific equivalence rules.

## Minimal implementation

```python
import hashlib

from freshctx import ObservationToken, register_adapter
from freshctx.model import AdapterResult


class KeyValueAdapter:
    name = "key_value"

    def __init__(self, reader):
        self.reader = reader

    @staticmethod
    def fingerprint(value: bytes) -> str:
        return hashlib.sha256(value).hexdigest()

    def observe(self, locator, **_options):
        value = self.reader(locator)
        return ObservationToken(self.name, str(locator), self.fingerprint(value))

    def validate(self, token):
        try:
            current = self.fingerprint(self.reader(token.locator))
        except (OSError, TimeoutError) as error:
            return AdapterResult("indeterminate", error_code=type(error).__name__)
        outcome = "equivalent" if current == token.fingerprint else "changed"
        return AdapterResult(outcome, evidence={"fingerprint": current})


register_adapter("key_value", KeyValueAdapter(my_read_only_reader))
```

The registration name, adapter `name`, and the name passed to `observe(..., adapter="key_value")` should match. `observe()` may raise when the initial source cannot be read; `validate()` must convert expected operational failures into `indeterminate`. Do not return `equivalent` from an exception path.

## Compatibility checklist

An adapter is compatible when tests demonstrate:

- the same evidence returns `equivalent`;
- changed evidence returns `changed`;
- lost connectivity, timeout, permission loss, and malformed evidence return `indeterminate`;
- observation and validation are read-only;
- locators, metadata, evidence, and audit events contain no credentials;
- validation completes within a documented timeout;
- registration works through the public `register_adapter()` API.
