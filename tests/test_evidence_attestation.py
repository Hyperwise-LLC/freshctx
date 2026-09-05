from __future__ import annotations

import json
import unittest
from dataclasses import replace
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from freshctx import (
    ActionEvidenceCorrelation,
    ConfigurationError,
    FreshnessState,
    attest_correlation,
    verify_attestation,
)


ROOT = Path(__file__).resolve().parents[1]
KEY = b"freshctx-test-key-is-at-least-32-bytes"


def correlation() -> ActionEvidenceCorrelation:
    return ActionEvidenceCorrelation(
        correlation_id="correlation-1",
        run_id="run-1",
        runtime="mcp",
        execution_id="request-1",
        action="transfer_money",
        boundary="mcp.action:transfer_money",
        subject_id="reasoning-2",
        declared_dependency_ids=("reasoning-2",),
        reasoning_ids=("reasoning-1", "reasoning-2"),
        observation_ids=("observation-1",),
        unresolved_dependency_ids=(),
        freshness_state=FreshnessState.CURRENT,
        policy_decision="allow",
        boundary_outcome="allowed",
        checked_at="2026-09-05T10:00:00+00:00",
        created_at="2026-09-05T10:00:01+00:00",
    )


class EvidenceAttestationTests(unittest.TestCase):
    def test_exact_correlation_verifies_inside_the_time_bound(self):
        receipt = attest_correlation(
            correlation(),
            issuer="risk-control",
            key_id="local-key-1",
            key=KEY,
            ttl_seconds=300,
            now="2026-09-05T10:00:02+00:00",
        )
        result = verify_attestation(
            receipt,
            correlation(),
            key=KEY,
            now="2026-09-05T10:04:00+00:00",
        )
        self.assertTrue(result.valid)
        self.assertEqual(result.reason, "verified")

    def test_changed_action_or_evidence_fails_verification(self):
        original = correlation()
        receipt = attest_correlation(
            original,
            issuer="risk-control",
            key_id="local-key-1",
            key=KEY,
            ttl_seconds=300,
            now="2026-09-05T10:00:02+00:00",
        )
        changed = replace(original, action="issue_refund")
        result = verify_attestation(receipt, changed, key=KEY, now="2026-09-05T10:01:00+00:00")
        self.assertFalse(result.valid)
        self.assertEqual(result.reason, "payload_mismatch")

    def test_different_correlation_and_expiry_are_distinct_failures(self):
        original = correlation()
        receipt = attest_correlation(
            original,
            issuer="risk-control",
            key_id="local-key-1",
            key=KEY,
            ttl_seconds=60,
            now="2026-09-05T10:00:02+00:00",
        )
        mismatch = replace(original, correlation_id="correlation-2")
        self.assertEqual(
            verify_attestation(receipt, mismatch, key=KEY, now="2026-09-05T10:00:30+00:00").reason,
            "correlation_mismatch",
        )
        self.assertEqual(
            verify_attestation(receipt, original, key=KEY, now="2026-09-05T10:02:00+00:00").reason,
            "expired",
        )
        self.assertEqual(
            verify_attestation(receipt, original, key=KEY, now="2026-09-05T09:59:00+00:00").reason,
            "not_yet_valid",
        )

    def test_wrong_key_fails_and_key_is_not_serialized(self):
        receipt = attest_correlation(
            correlation(), issuer="risk-control", key_id="key-7", key=KEY,
            ttl_seconds=60, now="2026-09-05T10:00:02+00:00",
        )
        result = verify_attestation(
            receipt,
            correlation(),
            key=b"a-different-test-key-that-is-32-bytes",
            now="2026-09-05T10:00:30+00:00",
        )
        self.assertFalse(result.valid)
        self.assertEqual(result.reason, "signature_mismatch")
        self.assertNotIn(KEY.decode(), json.dumps(receipt.to_dict()))

    def test_configuration_is_bounded_and_schema_valid(self):
        with self.assertRaises(ConfigurationError):
            attest_correlation(
                correlation(), issuer="", key_id="key", key=KEY, ttl_seconds=60
            )
        with self.assertRaises(ConfigurationError):
            attest_correlation(
                correlation(), issuer="issuer", key_id="key", key=b"short", ttl_seconds=60
            )
        with self.assertRaises(ConfigurationError):
            attest_correlation(
                correlation(), issuer="issuer", key_id="key", key=KEY, ttl_seconds=0
            )
        receipt = attest_correlation(
            correlation(), issuer="issuer", key_id="key", key=KEY,
            ttl_seconds=60, now="2026-09-05T10:00:02+00:00",
        )
        schema = json.loads((ROOT / "schemas" / "evidence-attestation.schema.json").read_text())
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(receipt.to_dict())


if __name__ == "__main__":
    unittest.main()
