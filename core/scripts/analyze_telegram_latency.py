from __future__ import annotations

import argparse
import math
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, TextIO


_TRACE_RE = re.compile(r"\btrace=(?P<trace>\S+)")
_ELAPSED_RE = re.compile(r"\belapsed_ms=(?P<elapsed>-?\d+(?:\.\d+)?)")
_STAGE_RE = re.compile(r"\bstage=(?P<stage>\S+)")
_METHOD_RE = re.compile(r"\bmethod=(?P<method>\S+)")
_CACHE_VERSION_RE = re.compile(r"\bversion=(?P<version>-?\d+)")
_CACHE_AGE_RE = re.compile(r"\bage_seconds=(?P<age>-?\d+(?:\.\d+)?)")


@dataclass(frozen=True)
class LatencyEvent:
    trace: str
    source: str
    name: str
    elapsed_ms: float | None = None
    raw: str = ""

    @property
    def label(self) -> str:
        return f"{self.source}:{self.name}"


@dataclass
class TraceSummary:
    trace: str
    events: list[LatencyEvent] = field(default_factory=list)
    cache_version: int | None = None
    cache_age_seconds: float | None = None

    def add(self, event: LatencyEvent) -> None:
        self.events.append(event)

    def elapsed_for(self, label: str) -> float | None:
        for event in self.events:
            if event.label == label:
                return event.elapsed_ms
        return None

    def slowest_event(self) -> LatencyEvent | None:
        timed_events = [event for event in self.events if event.elapsed_ms is not None]
        if not timed_events:
            return None
        return max(timed_events, key=lambda event: event.elapsed_ms or 0.0)


def _match_text(pattern: re.Pattern[str], line: str, group: str) -> str | None:
    match = pattern.search(line)
    if match is None:
        return None
    return match.group(group)


def _match_float(pattern: re.Pattern[str], line: str, group: str) -> float | None:
    value = _match_text(pattern, line, group)
    if value is None:
        return None
    parsed = float(value)
    if not math.isfinite(parsed) or parsed < 0:
        return None
    return parsed


def parse_latency_event(line: str) -> LatencyEvent | None:
    trace = _match_text(_TRACE_RE, line, "trace")
    if trace is None or trace == "-":
        return None

    elapsed_ms = _match_float(_ELAPSED_RE, line, "elapsed")
    stripped = line.rstrip("\n")

    if "[telegram_timing]" in line:
        stage = _match_text(_STAGE_RE, line, "stage")
        if stage is None:
            return None
        return LatencyEvent(
            trace=trace,
            source="timing",
            name=stage,
            elapsed_ms=elapsed_ms,
            raw=stripped,
        )

    if "[telegram_api_timing]" in line:
        method = _match_text(_METHOD_RE, line, "method")
        if method is None:
            return None
        return LatencyEvent(
            trace=trace,
            source="api",
            name=method,
            elapsed_ms=elapsed_ms,
            raw=stripped,
        )

    if "[telegram_cache]" in line:
        return LatencyEvent(
            trace=trace,
            source="cache",
            name="snapshot",
            elapsed_ms=None,
            raw=stripped,
        )

    return None


def summarize_lines(lines: Iterable[str]) -> dict[str, TraceSummary]:
    summaries: dict[str, TraceSummary] = {}
    for line in lines:
        event = parse_latency_event(line)
        if event is None:
            continue

        summary = summaries.setdefault(event.trace, TraceSummary(trace=event.trace))
        summary.add(event)

        if event.source == "cache":
            version = _match_text(_CACHE_VERSION_RE, event.raw, "version")
            age = _match_float(_CACHE_AGE_RE, event.raw, "age")
            if version is not None:
                summary.cache_version = int(version)
            if age is not None:
                summary.cache_age_seconds = age

    return summaries


def _format_ms(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value:.2f}ms"


def _percentile(sorted_values: list[float], percentile: float) -> float:
    if not sorted_values:
        raise ValueError("percentile requires at least one value")
    if len(sorted_values) == 1:
        return sorted_values[0]
    index = math.ceil(len(sorted_values) * percentile) - 1
    index = max(0, min(index, len(sorted_values) - 1))
    return sorted_values[index]


def format_summary(summary: TraceSummary) -> str:
    slowest = summary.slowest_event()
    slowest_text = (
        f"{slowest.label}:{_format_ms(slowest.elapsed_ms)}" if slowest else "-"
    )
    webhook_ack = summary.elapsed_for("timing:webhook_response_ready")
    background_total = summary.elapsed_for("timing:webhook_to_background_finished")
    callback_validated = summary.elapsed_for("timing:callback_validated")
    menu_stack = summary.elapsed_for("timing:menu_stack_loaded_from_snapshot")
    send_message = summary.elapsed_for("api:sendMessage")
    answer_callback = summary.elapsed_for("api:answerCallbackQuery")
    cache = (
        f"cache=v{summary.cache_version} age={summary.cache_age_seconds:.2f}s"
        if summary.cache_version is not None and summary.cache_age_seconds is not None
        else "cache=-"
    )
    return (
        f"trace={summary.trace} "
        f"webhook_ack={_format_ms(webhook_ack)} "
        f"background_total={_format_ms(background_total)} "
        f"callback_validated={_format_ms(callback_validated)} "
        f"menu_stack_snapshot={_format_ms(menu_stack)} "
        f"sendMessage={_format_ms(send_message)} "
        f"answerCallbackQuery={_format_ms(answer_callback)} "
        f"slowest={slowest_text} "
        f"{cache}"
    )


def format_aggregate_summaries(summaries: dict[str, TraceSummary]) -> list[str]:
    stage_values: dict[str, list[float]] = {}
    for summary in summaries.values():
        for event in summary.events:
            if event.elapsed_ms is None:
                continue
            stage_values.setdefault(event.label, []).append(event.elapsed_ms)

    lines: list[str] = []
    for label, values in sorted(stage_values.items()):
        sorted_values = sorted(values)
        count = len(sorted_values)
        lines.append(
            f"aggregate={label} count={count} "
            f"p50={_format_ms(_percentile(sorted_values, 0.50))} "
            f"p95={_format_ms(_percentile(sorted_values, 0.95))} "
            f"p99={_format_ms(_percentile(sorted_values, 0.99))} "
            f"max={_format_ms(sorted_values[-1])}"
        )
    return lines


def analyze_stream(stream: TextIO, *, include_aggregate: bool = False) -> list[str]:
    summaries = summarize_lines(stream)
    lines = [
        format_summary(summary)
        for _, summary in sorted(summaries.items(), key=lambda item: item[0])
    ]
    if include_aggregate:
        lines.extend(format_aggregate_summaries(summaries))
    return lines


def _open_input(path: str | None) -> TextIO:
    if path is None or path == "-":
        return sys.stdin
    return Path(path).open("r", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Analyze Telegram latency logs grouped by trace id."
    )
    parser.add_argument(
        "logfile",
        nargs="?",
        default="-",
        help="Log file path. Use '-' or omit to read stdin.",
    )
    parser.add_argument(
        "--aggregate",
        action="store_true",
        help="Append p50/p95/p99/max latency summaries grouped by stage.",
    )
    args = parser.parse_args(argv)

    stream = _open_input(args.logfile)
    try:
        for line in analyze_stream(stream, include_aggregate=args.aggregate):
            print(line)
    finally:
        if stream is not sys.stdin:
            stream.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
