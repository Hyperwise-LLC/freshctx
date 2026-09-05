"""Observed source-read provenance kept separate from freshness decisions."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Iterable
from uuid import uuid4

from .model import ActionEvidenceCorrelation, FreshnessStatus, utcnow


PROVENANCE_SCHEMA_VERSION = "freshctx.observed_evidence_provenance.v1"


class ProvenanceAssessment(str, Enum):
    """Result of an application-declared provenance policy."""

    CONSISTENT = "CONSISTENT"
    INCONSISTENT = "INCONSISTENT"
    NOT_ASSESSED = "NOT_ASSESSED"


@dataclass(frozen=True)
class SourceReadEvent:
    """Metadata proving that a read hook successfully opened one source."""

    event_id: str
    source_id: str
    accessed_at: str = field(default_factory=utcnow)

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class ObservedEvidenceReceipt:
    """Links observed reads and declared use without judging source truth."""

    receipt_id: str
    correlation_id: str
    observation_ids: tuple[str, ...]
    candidate_sources: tuple[str, ...]
    inspected_sources: tuple[str, ...]
    selected_source: str | None
    cited_sources: tuple[str, ...]
    required_sources: tuple[str, ...]
    read_events: tuple[SourceReadEvent, ...]
    freshness_state: FreshnessStatus
    provenance_assessment: ProvenanceAssessment
    assessment_reasons: tuple[str, ...]
    created_at: str = field(default_factory=utcnow)
    schema_version: str = PROVENANCE_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["freshness_state"] = self.freshness_state.value
        value["provenance_assessment"] = self.provenance_assessment.value
        value["observation_ids"] = list(self.observation_ids)
        value["candidate_sources"] = list(self.candidate_sources)
        value["inspected_sources"] = list(self.inspected_sources)
        value["cited_sources"] = list(self.cited_sources)
        value["required_sources"] = list(self.required_sources)
        value["assessment_reasons"] = list(self.assessment_reasons)
        value["read_events"] = [event.to_dict() for event in self.read_events]
        return value


class ObservedReadCapture:
    """Read files through a bounded hook and retain metadata, never contents."""

    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self._events: list[SourceReadEvent] = []

    @property
    def events(self) -> tuple[SourceReadEvent, ...]:
        return tuple(self._events)

    @property
    def inspected_sources(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(event.source_id for event in self._events))

    def _resolve(self, source: str | Path) -> tuple[Path, str]:
        requested = Path(source)
        path = requested.resolve() if requested.is_absolute() else (self.root / requested).resolve()
        try:
            source_id = path.relative_to(self.root).as_posix()
        except ValueError as error:
            raise ValueError("source must remain inside the configured read root") from error
        return path, source_id

    def read_text(self, source: str | Path, *, encoding: str = "utf-8") -> str:
        """Read one file and record its root-relative identity after success."""

        path, source_id = self._resolve(source)
        content = path.read_text(encoding=encoding)
        self._events.append(SourceReadEvent(str(uuid4()), source_id))
        return content

    def receipt(
        self,
        correlation: ActionEvidenceCorrelation,
        *,
        candidate_sources: Iterable[str] = (),
        selected_source: str | None = None,
        cited_sources: Iterable[str] = (),
        required_sources: Iterable[str] | None = None,
    ) -> ObservedEvidenceReceipt:
        """Build an independent provenance assessment linked to a guard check."""

        candidates = tuple(dict.fromkeys(candidate_sources))
        cited = tuple(dict.fromkeys(cited_sources))
        required = None if required_sources is None else tuple(dict.fromkeys(required_sources))
        inspected = self.inspected_sources
        reasons: list[str] = []

        if required is None:
            assessment = ProvenanceAssessment.NOT_ASSESSED
            reasons.append("no_provenance_policy_declared")
            required_value: tuple[str, ...] = ()
        else:
            required_value = required
            if selected_source is not None and selected_source not in inspected:
                reasons.append("selected_source_not_inspected")
            if any(source not in inspected for source in cited):
                reasons.append("cited_source_not_inspected")
            if any(source not in inspected for source in required):
                reasons.append("required_source_not_inspected")
            assessment = (
                ProvenanceAssessment.INCONSISTENT
                if reasons
                else ProvenanceAssessment.CONSISTENT
            )
            if not reasons:
                reasons.append("declared_provenance_policy_satisfied")

        return ObservedEvidenceReceipt(
            receipt_id=str(uuid4()),
            correlation_id=correlation.correlation_id,
            observation_ids=correlation.observation_ids,
            candidate_sources=candidates,
            inspected_sources=inspected,
            selected_source=selected_source,
            cited_sources=cited,
            required_sources=required_value,
            read_events=self.events,
            freshness_state=correlation.freshness_state,
            provenance_assessment=assessment,
            assessment_reasons=tuple(reasons),
        )
