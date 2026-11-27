"""从已有发生记录构建受限、脱敏的模型输入。"""

import json
from collections.abc import Callable
from typing import Protocol

from autoloop.config.settings import ContextLimits
from autoloop.runtime.redaction import redact
from autoloop.schemas.diagnosis import DiagnosticContext, IncidentSummary, LogEvidence, OccurrenceSummary
from autoloop.schemas.incident import Incident, Occurrence


class OccurrenceReader(Protocol):
    def diagnostic_occurrences(self, incident_id: str, limit: int) -> list[Occurrence]: ...


def _candidate_key(item: OccurrenceSummary) -> tuple[str, str | None]:
    return item.source_file, item.stack_trace


def _text(record: dict[str, object], field: str, fallback: str) -> str:
    value = record.get(field)
    return value if isinstance(value, str) and value else fallback


def _shorten(value: str, maximum: int) -> str:
    if len(value) <= maximum:
        return value
    half = maximum // 2 - 1
    return f"{value[:half]}…{value[-half:]}"


class ContextBuilder:
    def __init__(self, reader: OccurrenceReader, limits: ContextLimits, secret: str = "") -> None:
        self.reader = reader
        self.limits = limits
        self.clean: Callable[[str], str] = lambda text: redact(text, secret)

    def build(self, incident: Incident) -> DiagnosticContext:
        records = self.reader.diagnostic_occurrences(incident.id, self.limits.sample_size)
        if not records:
            raise ValueError("该故障没有发生记录，无法建立诊断证据")
        candidates: list[tuple[OccurrenceSummary, LogEvidence]] = []
        for item in records:
            try:
                raw = json.loads(item.raw_log)
            except (ValueError, RecursionError):
                raw = {}
            if not isinstance(raw, dict):
                raw = {}
            message = self.clean(_text(raw, "exception_message", _text(raw, "message", incident.error_message)))
            source = self.clean(item.source_file)
            summary = OccurrenceSummary(
                occurrence_id=item.id, event_id=item.event_id, timestamp=item.timestamp,
                exception_type=self.clean(_text(raw, "exception_type", incident.error_type))[:160],
                message=_shorten(message, self.limits.text_chars),
                stack_trace=_shorten(self.clean(item.stacktrace), self.limits.stack_chars) if item.stacktrace else None,
                source_file=_shorten(source, 180), source_line=item.source_line,
            )
            evidence = LogEvidence(
                evidence_id=item.id, timestamp=item.timestamp,
                level=self.clean(_text(raw, "level", incident.severity.value))[:24],
                message=summary.message, source=f"{summary.source_file} 第 {item.source_line} 行",
                occurrence_id=item.id,
            )
            candidates.append((summary, evidence))

        selected = candidates[:2]
        keys = {_candidate_key(item) for item, _ in selected}
        for item, evidence in candidates[2:]:
            if len(selected) >= min(self.limits.occurrences, self.limits.evidence):
                break
            key = _candidate_key(item)
            if key not in keys:
                keys.add(key)
                selected.append((item, evidence))

        context = DiagnosticContext(
            incident=IncidentSummary(
                incident_id=incident.id, title=self.clean(incident.title)[:180],
                description=self.clean(incident.error_message)[:self.limits.text_chars],
                category=incident.category, fingerprint=incident.fingerprint, status=incident.status,
                occurrence_count=incident.occurrence_count, first_seen=incident.first_seen,
                last_seen=incident.last_seen,
            ),
            occurrences=[item for item, _ in selected], evidence=[item for _, item in selected],
        )
        seen: set[str] = set()
        for occurrence in context.occurrences:
            stack = occurrence.stack_trace
            if stack and stack in seen:
                occurrence.stack_trace = None
            elif stack:
                seen.add(stack)

        while len(context.model_dump_json().encode("utf-8")) > self.limits.context_bytes:
            if len(context.occurrences) > 2:
                context.occurrences.pop()
                context.evidence.pop()
                continue
            if all(len(item.message) <= 50 and len(item.stack_trace or "") <= 50
                   for item in context.occurrences):
                raise ValueError("诊断上下文超出大小限制")
            for item, evidence in zip(context.occurrences, context.evidence, strict=True):
                item.message = _shorten(item.message, max(50, len(item.message) // 2))
                evidence.message = item.message
                if item.stack_trace:
                    item.stack_trace = _shorten(item.stack_trace, max(50, len(item.stack_trace) // 2))
            context.incident.description = _shorten(context.incident.description, 120)
        return context
