"""Raw-file versus decision-relevant configuration freshness.

The built-in filesystem adapter deliberately treats every byte change as a
change. A custom adapter can instead canonicalize only the fields that
affected a decision. Parsing failures and missing declared fields are never
treated as current.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from freshctx import FreshnessState, MemoryStore, guard, observe, register_adapter
from freshctx.model import AdapterResult, ObservationToken


class SemanticPolicyAdapter:
    """Fingerprint selected JSON fields rather than the complete file."""

    name = "semantic_policy_example"
    thread_safe = True

    @staticmethod
    def _read_selected(path: Path, fields: tuple[str, ...]) -> dict[str, object]:
        document = json.loads(path.read_text(encoding="utf-8"))
        selected: dict[str, object] = {}
        for field in fields:
            value: object = document
            for part in field.split("."):
                if not isinstance(value, dict) or part not in value:
                    raise KeyError(field)
                value = value[part]
            selected[field] = value
        return selected

    @staticmethod
    def _fingerprint(selected: dict[str, object]) -> str:
        payload = json.dumps(
            selected, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    def observe(self, locator, *, fields):
        path = Path(locator).absolute()
        normalized_fields = tuple(sorted(set(str(field) for field in fields)))
        if not normalized_fields:
            raise ValueError("fields must contain at least one JSON path")
        selected = self._read_selected(path, normalized_fields)
        return ObservationToken(
            self.name,
            str(path),
            self._fingerprint(selected),
            metadata={"fields": list(normalized_fields)},
        )

    def validate(self, token):
        fields = tuple(str(field) for field in token.metadata.get("fields", ()))
        try:
            selected = self._read_selected(Path(token.locator), fields)
        except json.JSONDecodeError:
            return AdapterResult("indeterminate", error_code="invalid_json")
        except KeyError as error:
            return AdapterResult(
                "indeterminate",
                evidence={"missing_field": str(error.args[0])},
                error_code="missing_field",
            )
        except (OSError, UnicodeError, TypeError, ValueError) as error:
            return AdapterResult("indeterminate", error_code=type(error).__name__)

        fingerprint = self._fingerprint(selected)
        return AdapterResult(
            "equivalent" if fingerprint == token.fingerprint else "changed",
            evidence={"fields": list(fields), "fingerprint": fingerprint},
        )


register_adapter(SemanticPolicyAdapter.name, SemanticPolicyAdapter())


def _write_policy(path: Path, *, description: str, max_amount: int = 1000) -> None:
    path.write_text(
        json.dumps(
            {
                "policy": {
                    "approval_required": True,
                    "max_amount": max_amount,
                },
                "presentation": {"description": description},
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def run_scenario() -> dict[str, str]:
    with TemporaryDirectory() as directory:
        path = Path(directory) / "payment-policy.json"
        _write_policy(path, description="Initial wording")
        store = MemoryStore()

        with guard(store=store):
            raw_file = observe(path)
            selected_fields = observe(
                path,
                adapter=SemanticPolicyAdapter.name,
                fields=("policy.approval_required", "policy.max_amount"),
            )

        # A presentation-only edit changes the raw file but not the fields that
        # influenced the payment decision.
        _write_policy(path, description="Reworded for clarity")
        with guard(policy="allow", store=store) as ctx:
            raw_after_cosmetic_edit = ctx.check(raw_file).state
            selected_after_cosmetic_edit = ctx.check(selected_fields).state

        # A decision-relevant field changes.
        _write_policy(path, description="Reworded for clarity", max_amount=500)
        with guard(policy="allow", store=store) as ctx:
            selected_after_material_edit = ctx.check(selected_fields).state

        # Invalid syntax cannot be verified and must not pass as current.
        path.write_text("{not valid json", encoding="utf-8")
        with guard(policy="allow", store=store) as ctx:
            invalid_document = ctx.check(selected_fields).state

        # A valid document that omits a declared field is also unverifiable.
        path.write_text(
            json.dumps({"policy": {"approval_required": True}}),
            encoding="utf-8",
        )
        with guard(policy="allow", store=store) as ctx:
            missing_declared_field = ctx.check(selected_fields).state

        return {
            "raw_after_cosmetic_edit": raw_after_cosmetic_edit.value,
            "selected_after_cosmetic_edit": selected_after_cosmetic_edit.value,
            "selected_after_material_edit": selected_after_material_edit.value,
            "invalid_document": invalid_document.value,
            "missing_declared_field": missing_declared_field.value,
        }


if __name__ == "__main__":
    results = run_scenario()
    assert results == {
        "raw_after_cosmetic_edit": FreshnessState.STALE_SOURCE.value,
        "selected_after_cosmetic_edit": FreshnessState.CURRENT.value,
        "selected_after_material_edit": FreshnessState.STALE_SOURCE.value,
        "invalid_document": FreshnessState.UNVERIFIABLE.value,
        "missing_declared_field": FreshnessState.UNVERIFIABLE.value,
    }
    for name, state in results.items():
        print(f"{name}: {state}")
