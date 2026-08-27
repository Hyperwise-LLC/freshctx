"""Controlled, executable FreshCtx acceptance scenarios for business workflows.

These are reference simulations, not claims about customer production deployments.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from freshctx import (
    FreshnessBlocked,
    FreshnessState,
    MemoryStore,
    ObservationToken,
    guard,
    observe,
    reasoning,
    register_adapter,
)
from freshctx.model import AdapterResult


def _fingerprint(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


class MutableBusinessAdapter:
    """Safe deterministic adapter used to model mutable enterprise records."""

    def __init__(self, name: str, records: dict[str, Any], availability: dict[str, bool] | None = None):
        self.name = name
        self.records = records
        self.availability = availability or {key: True for key in records}

    def observe(self, locator: str, **_options) -> ObservationToken:
        if not self.availability.get(locator, False):
            raise ConnectionError(f"{locator} unavailable")
        return ObservationToken(
            self.name,
            locator,
            _fingerprint(self.records[locator]),
            metadata={"record_type": locator.split(":", 1)[0]},
        )

    def validate(self, token: ObservationToken) -> AdapterResult:
        if not self.availability.get(token.locator, False):
            return AdapterResult("indeterminate", error_code="ConnectionError")
        current = _fingerprint(self.records[token.locator])
        return AdapterResult(
            "equivalent" if current == token.fingerprint else "changed",
            evidence={"record_type": token.metadata["record_type"], "fingerprint": current},
        )


@dataclass
class ScenarioResult:
    case_id: str
    domain: str
    protected_action: str
    changed_source: str
    changed_source_state: str
    decision_state: str
    unaffected_source_state: str
    action_blocked: bool
    action_executed: bool
    audit_event_count: int
    expected_control_result: str

    def to_dict(self):
        return self.__dict__.copy()


def _changed_record_scenario(
    *,
    case_id: str,
    domain: str,
    protected_action: str,
    records: dict[str, Any],
    decision_sources: list[str],
    changed_source: str,
    changed_value: Any,
    unaffected_source: str,
) -> ScenarioResult:
    adapter_name = f"success-{case_id}"
    availability = {key: True for key in records}
    adapter = MutableBusinessAdapter(adapter_name, records, availability)
    register_adapter(adapter_name, adapter)
    executed: list[str] = []

    with tempfile.TemporaryDirectory() as directory:
        audit = Path(directory) / "audit.jsonl"
        store = MemoryStore()
        with guard(store=store, audit_path=audit):
            tokens = {key: observe(key, adapter=adapter_name) for key in records}
            with reasoning(f"{case_id}-decision", [tokens[key] for key in decision_sources]) as decision:
                pass

        records[changed_source] = changed_value

        with guard(policy="allow", store=store, audit_path=audit) as ctx:
            source_state = ctx.check(tokens[changed_source]).state
            decision_state = ctx.check(decision).state
            unaffected_state = ctx.check(tokens[unaffected_source]).state

        blocked = False
        try:
            with guard(store=store, audit_path=audit) as ctx:
                ctx.run(lambda: executed.append(protected_action), depends_on=[decision])
        except FreshnessBlocked:
            blocked = True

        with audit.open(encoding="utf-8") as audit_file:
            event_count = sum(1 for _ in audit_file)

    return ScenarioResult(
        case_id=case_id,
        domain=domain,
        protected_action=protected_action,
        changed_source=changed_source,
        changed_source_state=source_state.value,
        decision_state=decision_state.value,
        unaffected_source_state=unaffected_state.value,
        action_blocked=blocked,
        action_executed=bool(executed),
        audit_event_count=event_count,
        expected_control_result="changed evidence invalidated dependent reasoning and blocked the action",
    )


def banking_payment_release() -> ScenarioResult:
    return _changed_record_scenario(
        case_id="banking-payment-release",
        domain="banking and payments",
        protected_action="release a $240,000 supplier wire",
        records={
            "account:operating-4471": {"status": "active", "available": "812450.00", "legal_hold": False},
            "beneficiary:supplier-882": {"status": "verified", "country": "US", "account_version": 7},
            "risk:wire-2026-10419": {"decision": "allow", "model_version": "wire-risk-12", "score": 18},
            "approval:wire-2026-10419": {"treasury": "approved", "controller": "approved", "version": 3},
        },
        decision_sources=[
            "account:operating-4471",
            "beneficiary:supplier-882",
            "risk:wire-2026-10419",
            "approval:wire-2026-10419",
        ],
        changed_source="account:operating-4471",
        changed_value={"status": "frozen", "available": "812450.00", "legal_hold": True},
        unaffected_source="beneficiary:supplier-882",
    )


def ecommerce_order_fulfillment() -> ScenarioResult:
    return _changed_record_scenario(
        case_id="ecommerce-order-fulfillment",
        domain="e-commerce",
        protected_action="reserve and release 12 units for same-day fulfillment",
        records={
            "inventory:SKU-7842:DFW": {"available": 24, "reserved": 7, "version": 901},
            "price:SKU-7842": {"amount": "189.00", "currency": "USD", "promotion": "B2B-AUG"},
            "fraud:order-733104": {"decision": "allow", "score": 11, "address_match": True},
            "shipping:order-733104": {"service": "same-day", "cutoff": "14:00", "capacity": True},
        },
        decision_sources=[
            "inventory:SKU-7842:DFW",
            "price:SKU-7842",
            "fraud:order-733104",
            "shipping:order-733104",
        ],
        changed_source="inventory:SKU-7842:DFW",
        changed_value={"available": 3, "reserved": 28, "version": 902},
        unaffected_source="fraud:order-733104",
    )


def insurance_claim_settlement() -> ScenarioResult:
    return _changed_record_scenario(
        case_id="insurance-claim-settlement",
        domain="insurance",
        protected_action="issue a $38,400 property-claim settlement",
        records={
            "policy:HOME-99182": {"status": "active", "coverage_version": 12, "limit": "500000.00"},
            "claim:CLM-44017": {"status": "approved", "estimate": "38400.00", "version": 9},
            "fraud:CLM-44017": {"decision": "clear", "score": 7},
            "approval:CLM-44017": {"adjuster": "approved", "supervisor": "approved"},
        },
        decision_sources=["policy:HOME-99182", "claim:CLM-44017", "fraud:CLM-44017", "approval:CLM-44017"],
        changed_source="policy:HOME-99182",
        changed_value={"status": "suspended-review", "coverage_version": 13, "limit": "500000.00"},
        unaffected_source="fraud:CLM-44017",
    )


def procurement_purchase_order() -> ScenarioResult:
    return _changed_record_scenario(
        case_id="procurement-purchase-order",
        domain="enterprise procurement",
        protected_action="issue a $186,000 infrastructure purchase order",
        records={
            "vendor:V-1832": {"status": "approved", "risk_tier": "medium", "insurance_current": True},
            "quote:Q-88210": {"amount": "186000.00", "expires": "2026-08-31", "version": 4},
            "budget:CC-710": {"available": "250000.00", "period": "2026-Q3", "version": 21},
            "approval:PO-draft-994": {"director": "approved", "finance": "approved", "threshold": "200000.00"},
        },
        decision_sources=["vendor:V-1832", "quote:Q-88210", "budget:CC-710", "approval:PO-draft-994"],
        changed_source="quote:Q-88210",
        changed_value={"amount": "214000.00", "expires": "2026-08-31", "version": 5},
        unaffected_source="vendor:V-1832",
    )


def customer_service_refund() -> ScenarioResult:
    return _changed_record_scenario(
        case_id="customer-service-refund",
        domain="customer service",
        protected_action="issue a $1,249 duplicate-shipment refund",
        records={
            "order:ORD-557201": {"status": "delivered", "paid": "1249.00", "version": 18},
            "return:RMA-7741": {"status": "received", "condition": "unopened", "version": 5},
            "refund-ledger:ORD-557201": {"refunds": [], "version": 2},
            "policy:high-value-refund": {"version": 6, "supervisor_required": True},
        },
        decision_sources=[
            "order:ORD-557201",
            "return:RMA-7741",
            "refund-ledger:ORD-557201",
            "policy:high-value-refund",
        ],
        changed_source="refund-ledger:ORD-557201",
        changed_value={"refunds": [{"amount": "1249.00", "status": "issued", "channel": "phone-agent"}], "version": 3},
        unaffected_source="return:RMA-7741",
    )


def legal_record_disposition() -> ScenarioResult:
    return _changed_record_scenario(
        case_id="legal-record-disposition",
        domain="legal and contract operations",
        protected_action="dispose of expired contract records",
        records={
            "contract:MSA-2019-448": {"status": "expired", "version": 17, "retention_end": "2026-08-01"},
            "legal-hold:MATTER-884": {"active": False, "scope": [], "version": 2},
            "retention-policy:contracts": {"version": 11, "period_years": 7},
            "approval:disposition-batch-91": {"records": "approved", "legal": "approved"},
        },
        decision_sources=[
            "contract:MSA-2019-448",
            "legal-hold:MATTER-884",
            "retention-policy:contracts",
            "approval:disposition-batch-91",
        ],
        changed_source="legal-hold:MATTER-884",
        changed_value={"active": True, "scope": ["MSA-2019-448"], "version": 3},
        unaffected_source="retention-policy:contracts",
    )


def healthcare_authorization_outage() -> ScenarioResult:
    case_id = "healthcare-authorization-outage"
    adapter_name = f"success-{case_id}"
    records = {
        "authorization:AUTH-77421": {"status": "approved", "service": "outpatient-imaging", "version": 8},
        "schedule:SLOT-2026-09-02-1030": {"available": True, "facility": "north-campus", "version": 31},
        "provider:RAD-204": {"status": "active", "credential_version": 14},
    }
    availability = {key: True for key in records}
    adapter = MutableBusinessAdapter(adapter_name, records, availability)
    register_adapter(adapter_name, adapter)
    executed: list[str] = []

    with tempfile.TemporaryDirectory() as directory:
        audit = Path(directory) / "audit.jsonl"
        store = MemoryStore()
        with guard(store=store, audit_path=audit):
            tokens = {key: observe(key, adapter=adapter_name) for key in records}
            with reasoning("schedule-authorized-service", list(tokens.values())) as decision:
                pass
        availability["authorization:AUTH-77421"] = False
        with guard(policy="allow", store=store, audit_path=audit) as ctx:
            source_state = ctx.check(tokens["authorization:AUTH-77421"]).state
            decision_state = ctx.check(decision).state
            unaffected_state = ctx.check(tokens["provider:RAD-204"]).state
        blocked = False
        try:
            with guard(store=store, audit_path=audit) as ctx:
                ctx.run(lambda: executed.append("scheduled"), depends_on=[decision])
        except FreshnessBlocked:
            blocked = True
        with audit.open(encoding="utf-8") as audit_file:
            event_count = sum(1 for _ in audit_file)

    return ScenarioResult(
        case_id=case_id,
        domain="healthcare operations",
        protected_action="confirm an authorization-dependent outpatient appointment",
        changed_source="authorization:AUTH-77421",
        changed_source_state=source_state.value,
        decision_state=decision_state.value,
        unaffected_source_state=unaffected_state.value,
        action_blocked=blocked,
        action_executed=bool(executed),
        audit_event_count=event_count,
        expected_control_result="unreachable authorization remained UNVERIFIABLE and blocked scheduling",
    )


def audit_selective_finding_invalidation() -> ScenarioResult:
    case_id = "audit-selective-finding-invalidation"
    executed: list[str] = []
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        store = MemoryStore()
        audit_path = root / "freshctx-audit.jsonl"
        access = root / "access-review.json"
        retention = root / "retention-policy.md"
        payment_sample = root / "payment-sample.csv"
        access.write_text('{"population": 4821, "exceptions": 3, "extract_version": 17}', encoding="utf-8")
        retention.write_text("Policy version 8\nRetention: 7 years\n", encoding="utf-8")
        payment_sample.write_text("sample_id,exceptions\n2026-Q3,0\n", encoding="utf-8")

        with guard(store=store, audit_path=audit_path):
            access_token = observe(access)
            retention_token = observe(retention)
            payment_token = observe(payment_sample)
            with reasoning("access-control-finding", [access_token]) as access_finding:
                pass
            with reasoning("record-retention-finding", [retention_token]) as retention_finding:
                pass
            with reasoning("payment-control-finding", [payment_token]) as payment_finding:
                pass

        retention.write_text("Policy version 9\nRetention: 10 years\nLegal approval required.\n", encoding="utf-8")
        with guard(policy="allow", store=store, audit_path=audit_path) as ctx:
            source_state = ctx.check(retention_token).state
            decision_state = ctx.check(retention_finding).state
            access_state = ctx.check(access_finding).state
            payment_state = ctx.check(payment_finding).state

        blocked = False
        try:
            with guard(store=store, audit_path=audit_path) as ctx:
                ctx.run(
                    lambda: executed.append("audit-pack-issued"),
                    depends_on=[access_finding, retention_finding, payment_finding],
                )
        except FreshnessBlocked:
            blocked = True
        with audit_path.open(encoding="utf-8") as audit_file:
            event_count = sum(1 for _ in audit_file)

    assert access_state is FreshnessState.CURRENT
    assert payment_state is FreshnessState.CURRENT
    return ScenarioResult(
        case_id=case_id,
        domain="audit and assurance",
        protected_action="issue a three-finding audit pack",
        changed_source="retention-policy.md",
        changed_source_state=source_state.value,
        decision_state=decision_state.value,
        unaffected_source_state=access_state.value,
        action_blocked=blocked,
        action_executed=bool(executed),
        audit_event_count=event_count,
        expected_control_result="only the retention finding became stale; unrelated findings remained current",
    )


def it_security_firewall_change() -> ScenarioResult:
    case_id = "it-security-firewall-change"
    executed: list[str] = []
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        repo = root / "security-repo"
        repo.mkdir()
        audit_path = root / "freshctx-audit.jsonl"
        store = MemoryStore()

        def git(*args):
            return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True).stdout.strip()

        git("init", "-q")
        git("config", "user.email", "freshctx@example.invalid")
        git("config", "user.name", "FreshCtx Success Cases")
        (repo / "policies").mkdir()
        (repo / "runbooks").mkdir()
        (repo / "policies" / "firewall.yaml").write_text("version: 41\nallow_admin_cidr: 10.24.0.0/16\n", encoding="utf-8")
        (repo / "runbooks" / "incident.md").write_text("Escalate severity-one incidents.\n", encoding="utf-8")
        (repo / "README.md").write_text("Security automation repository.\n", encoding="utf-8")
        git("add", ".")
        git("commit", "-qm", "initial policy")

        with guard(store=store, audit_path=audit_path):
            policy = observe(repo, adapter="git", scope="path", path="policies/firewall.yaml")
            runbook = observe(repo, adapter="git", scope="path", path="runbooks/incident.md")
            with reasoning("approve-firewall-remediation", [policy, runbook]) as decision:
                pass

        (repo / "README.md").write_text("Security automation and control repository.\n", encoding="utf-8")
        git("add", "README.md")
        git("commit", "-qm", "unrelated documentation")
        with guard(policy="allow", store=store, audit_path=audit_path) as ctx:
            after_unrelated = ctx.check(policy).state

        (repo / "policies" / "firewall.yaml").write_text("version: 42\nallow_admin_cidr: 10.42.0.0/16\nemergency_change: true\n", encoding="utf-8")
        git("add", "policies/firewall.yaml")
        git("commit", "-qm", "emergency firewall update")
        with guard(policy="allow", store=store, audit_path=audit_path) as ctx:
            source_state = ctx.check(policy).state
            decision_state = ctx.check(decision).state
            unaffected_state = ctx.check(runbook).state

        blocked = False
        try:
            with guard(store=store, audit_path=audit_path) as ctx:
                ctx.run(lambda: executed.append("firewall-applied"), depends_on=[decision])
        except FreshnessBlocked:
            blocked = True
        with audit_path.open(encoding="utf-8") as audit_file:
            event_count = sum(1 for _ in audit_file)

    assert after_unrelated is FreshnessState.CURRENT
    return ScenarioResult(
        case_id=case_id,
        domain="IT and security operations",
        protected_action="apply a firewall remediation plan",
        changed_source="policies/firewall.yaml",
        changed_source_state=source_state.value,
        decision_state=decision_state.value,
        unaffected_source_state=unaffected_state.value,
        action_blocked=blocked,
        action_executed=bool(executed),
        audit_event_count=event_count,
        expected_control_result="unrelated Git change stayed current; policy change invalidated remediation and blocked execution",
    )


SCENARIOS = [
    banking_payment_release,
    ecommerce_order_fulfillment,
    audit_selective_finding_invalidation,
    insurance_claim_settlement,
    healthcare_authorization_outage,
    procurement_purchase_order,
    customer_service_refund,
    it_security_firewall_change,
    legal_record_disposition,
]


def run_all() -> list[ScenarioResult]:
    return [scenario() for scenario in SCENARIOS]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    results = run_all()
    payload = {
        "schema_version": 1,
        "method": "controlled FreshCtx acceptance scenarios; not production customer deployments",
        "passed": sum(
            result.action_blocked
            and not result.action_executed
            and result.unaffected_source_state == FreshnessState.CURRENT.value
            for result in results
        ),
        "total": len(results),
        "results": [result.to_dict() for result in results],
    }
    encoded = json.dumps(payload, indent=2, sort_keys=True)
    print(encoded)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded + "\n", encoding="utf-8")
    return 0 if payload["passed"] == payload["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
