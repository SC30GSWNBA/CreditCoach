"""Observability (Task 26): every request is one OpenTelemetry trace, and every step in it is a span.

``agent.pipeline.answer`` opens the trace. Everything that happens for that question is recorded under it, with the
same trace ID:

    Span                  Opened by                    What it records
    creditcoach.answer    agent.pipeline.answer        user, memory session, question, answer, guardrail action,
                                                       cache status, model; an exception if the answer failed
    guardrail.input       agent.pipeline               input rails; a ``guardrail.trigger`` event per finding
    retrieval             agent.pipeline               passage ids, categories and scores
    memory.context        agent.pipeline               building the MEMORY section (only with a memory session)
    memory.recall         agent.pipeline               stored goal, earlier sessions
    context.build         agent.pipeline               the user's profile and the prompt (data backend, history)
    llm.chat              llm._complete                model asked for and used, tokens, cost; ``llm.fallback`` event
    tool.<name>           agent.mcp_host.McpHost.call  arguments, ok, error code, attempts, cached; a failed call
                          (and memory tools)           has ERROR status and a ``tool.failure`` event
    guardrail.output      agent.pipeline               passed / reframed / blocked; ``guardrail.trigger`` events
    (events)              cache._note                  every cache lookup as a ``cache`` event on the current span

Where spans go:
    Local file   Always, unless ``CREDITCOACH_TRACES=off``: one JSON line per span in ``.traces/<UTC date>.jsonl``
                 (git-ignored). ``load(trace_id)`` reads one request back, and ``scripts/task26_trace_export.py``
                 exports one.
    Langfuse     When ``LANGFUSE_PUBLIC_KEY`` and ``LANGFUSE_SECRET_KEY`` are set, spans are also sent over OTLP to
                 ``LANGFUSE_HOST`` (default https://cloud.langfuse.com). The ``langfuse.*`` and ``gen_ai.*`` attributes
                 make model calls show as generations with token counts and cost, and tools as tool observations.
    Other OTLP   Without Langfuse keys, ``OTEL_EXPORTER_OTLP_ENDPOINT`` (and ``OTEL_EXPORTER_OTLP_HEADERS``) sends
                 spans to any OpenTelemetry collector.

CreditCoach keeps its own tracer provider instead of setting the global one, so libraries that also use
OpenTelemetry (Chroma, NeMo Guardrails) don't add their spans to ours. Recording never raises: a failing exporter is
logged by the SDK and the answer goes on.

Questions are recorded after the input rails mask personal identifiers (S3), so a PAN or card number never reaches a
trace. Long text (model messages, answers, tool results) is cut at ``MAX_TEXT`` characters.

Example:
    >>> from creditcoach import observability as obs
    >>> with obs.span("creditcoach.answer", root=True, **{"user.id": "USR-001"}) as s:
    ...     with obs.span("retrieval", passages=3):
    ...         obs.event("cache", layer="retrieval", result="hit")
    ...     trace_id = obs.trace_id()
    >>> [s["name"] for s in obs.load(trace_id)]
    ['retrieval', 'creditcoach.answer']
"""

import atexit
import base64
import contextvars
import json
import logging
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import (BatchSpanProcessor, SimpleSpanProcessor, SpanExporter,
                                            SpanExportResult)
from opentelemetry.trace import Status, StatusCode

from creditcoach import config

log = logging.getLogger(__name__)

SERVICE = "creditcoach"
MAX_TEXT = 8000  # characters kept of any one text attribute

_lock = threading.Lock()
_provider: TracerProvider | None = None
_tracer: trace.Tracer | None = None
_carried: contextvars.ContextVar[dict] = contextvars.ContextVar("carried_attributes", default={})


class FileExporter(SpanExporter):
    """Writes each finished span as one JSON line to ``<folder>/<UTC date>.jsonl``."""

    def __init__(self, folder: Path):
        self.folder = Path(folder)
        self._lock = threading.Lock()

    def export(self, spans) -> SpanExportResult:
        try:
            self.folder.mkdir(parents=True, exist_ok=True)
            lines = [json.dumps(as_dict(s), ensure_ascii=False) + "\n" for s in spans]
            with self._lock, open(self.folder / f"{datetime.now(UTC):%Y-%m-%d}.jsonl", "a", encoding="utf-8") as f:
                f.writelines(lines)
            return SpanExportResult.SUCCESS
        except Exception:
            log.exception("Couldn't write %d span(s) to %s", len(spans), self.folder)
            return SpanExportResult.FAILURE


def langfuse_exporter() -> SpanExporter | None:
    """An OTLP exporter for Langfuse if its keys are set, else for ``OTEL_EXPORTER_OTLP_ENDPOINT`` if that is set,
    else None."""
    if config.LANGFUSE_PUBLIC_KEY and config.LANGFUSE_SECRET_KEY:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

        auth = base64.b64encode(f"{config.LANGFUSE_PUBLIC_KEY}:{config.LANGFUSE_SECRET_KEY}".encode()).decode()
        return OTLPSpanExporter(endpoint=config.LANGFUSE_HOST.rstrip("/") + "/api/public/otel/v1/traces",
                                headers={"Authorization": f"Basic {auth}"})
    if config.OTLP_ENDPOINT:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

        return OTLPSpanExporter()  # reads the endpoint and headers from the OTEL_EXPORTER_OTLP_* variables
    return None


def configure(exporters: list[SpanExporter] | None = None) -> TracerProvider:
    """Build the tracer provider. With ``exporters`` (tests), spans go only to those, synchronously; without, to the
    local file and, if configured, Langfuse or another OTLP endpoint. Replaces any provider built before."""
    global _provider, _tracer
    with _lock:
        if _provider is not None:
            _provider.shutdown()
        provider = TracerProvider(resource=Resource.create({"service.name": SERVICE,
                                                            "deployment.environment": config.ENVIRONMENT}))
        if exporters is not None:
            for e in exporters:
                provider.add_span_processor(SimpleSpanProcessor(e))
        else:
            if config.TRACES != "off":
                provider.add_span_processor(SimpleSpanProcessor(FileExporter(config.TRACES_DIR)))
            remote = langfuse_exporter()
            if remote is not None:
                provider.add_span_processor(BatchSpanProcessor(remote))
        _provider, _tracer = provider, provider.get_tracer(SERVICE)
        return provider


def tracer() -> trace.Tracer:
    if _tracer is None:
        configure()
    return _tracer


def flush(timeout_ms: int = 10_000) -> None:
    """Send every finished span now (scripts call this before exiting; the app's exporters flush on their own)."""
    if _provider is not None:
        _provider.force_flush(timeout_ms)


atexit.register(flush)


def _value(v):
    """An attribute value OpenTelemetry accepts: str, bool, int, float or a list of one of those; else JSON text."""
    if isinstance(v, (bool, int, float)):
        return v
    if isinstance(v, str):
        return v if len(v) <= MAX_TEXT else v[:MAX_TEXT] + f"… [{len(v) - MAX_TEXT} more characters]"
    if isinstance(v, (list, tuple)) and v and all(isinstance(x, str) for x in v):
        return [_value(x) for x in v]
    if isinstance(v, (list, tuple)) and v and (all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in v)):
        return list(v)
    return _value(json.dumps(v, ensure_ascii=False, default=str))


def attributes(**attrs) -> dict:
    """Keyword attributes as span attributes, without ``None`` values. Pass dotted names as ``**{"user.id": ...}``."""
    return {k: _value(v) for k, v in attrs.items() if v is not None}


@contextmanager
def span(name: str, root: bool = False, carry: dict | None = None, **attrs) -> Iterator[trace.Span]:
    """Open a span as a child of the current one (or a new trace with ``root``), with the given attributes.

    ``carry`` attributes go on this span and on every span opened inside it, for example the user and session, which
    Langfuse reads from each span to filter by user. An exception raised inside is recorded on the span, which gets
    ERROR status, and then re-raised.
    """
    carried = {**_carried.get(), **attributes(**(carry or {}))}
    context = trace.set_span_in_context(trace.INVALID_SPAN) if root else None
    token = _carried.set(carried)
    try:
        with tracer().start_as_current_span(name, context=context,
                                            attributes={**carried, **attributes(**attrs)}) as s:
            yield s
    finally:
        _carried.reset(token)


def current() -> trace.Span:
    return trace.get_current_span()


def annotate(**attrs) -> None:
    """Add attributes to the current span."""
    s = current()
    if s.is_recording():
        s.set_attributes(attributes(**attrs))


def event(name: str, **attrs) -> None:
    """Add an event to the current span (a no-op outside a trace)."""
    s = current()
    if s.is_recording():
        s.add_event(name, attributes(**attrs))


def fail(message: str, **attrs) -> None:
    """Mark the current span as failed, with a reason the dashboards can show."""
    s = current()
    if s.is_recording():
        s.set_status(Status(StatusCode.ERROR, message))
        s.set_attributes(attributes(**{"langfuse.observation.level": "ERROR",
                                       "langfuse.observation.status_message": message, **attrs}))


def trace_id() -> str | None:
    """The current trace's ID as 32 hex characters, or None outside a trace."""
    ctx = current().get_span_context()
    return format(ctx.trace_id, "032x") if ctx.is_valid else None


def as_dict(s: ReadableSpan) -> dict:
    """A finished span as plain JSON-ready data (the local file's format)."""
    ctx = s.get_span_context()
    return {"trace_id": format(ctx.trace_id, "032x"), "span_id": format(ctx.span_id, "016x"),
            "parent_id": format(s.parent.span_id, "016x") if s.parent else None, "name": s.name,
            "start": datetime.fromtimestamp(s.start_time / 1e9, UTC).isoformat(timespec="microseconds"),
            "ms": round((s.end_time - s.start_time) / 1e6, 2),
            "status": s.status.status_code.name, "status_message": s.status.description,
            "attributes": dict(s.attributes or {}),
            "events": [{"name": e.name, "ms": round((e.timestamp - s.start_time) / 1e6, 2),
                        "attributes": dict(e.attributes or {})} for e in s.events]}


def load(trace_id: str, folder: Path | None = None) -> list[dict]:
    """Every recorded span of one trace from the local files, in the order they finished."""
    folder = Path(folder or config.TRACES_DIR)
    spans = []
    for path in sorted(folder.glob("*.jsonl")):
        with open(path, encoding="utf-8") as f:
            spans += [d for d in map(json.loads, f) if d["trace_id"] == trace_id]
    return spans
