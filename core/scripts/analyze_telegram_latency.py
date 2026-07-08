from __future__ import annotations

import argparse
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
    return float(value)


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


def format_summary(summary: TraceSummary) -> str:
    slowest = summary.slowest_event()
    slowest_text = (
        f"{slowest.label}:{_format_ms(slowest.elapsed_ms)}" if slowest else "-"
    )
    webhook_ack = summary.elapsed_for("timing:webhook_response_ready")
    background_total = summary.elapsed_for("timing:webhook_to_background_finished")
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
        f"sendMessage={_format_ms(send_message)} "
        f"answerCallbackQuery={_format_ms(answer_callback)} "
        f"slowest={slowest_text} "
        f"{cache}"
    )


def analyze_stream(stream: TextIO) -> list[str]:
    summaries = summarize_lines(stream)
    return [
        format_summary(summary)
        for _, summary in sorted(summaries.items(), key=lambda item: item[0])
    ]


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
    args = parser.parse_args(argv)

    stream = _open_input(args.logfile)
    try:
        for line in analyze_stream(stream):
            print(line)
    finally:
        if stream is not sys.stdin:
            stream.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
