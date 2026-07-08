from __future__ import annotations

from io import StringIO

from scripts.analyze_telegram_latency import (
    analyze_stream,
    parse_latency_event,
    summarize_lines,
)


def test_parse_latency_event_telegram_timing_extracts_stage_and_elapsed() -> None:
    line = (
        "INFO:controllers.telegram_controller:[telegram_timing] "
        "trace=tg:777002:9002 stage=webhook_response_ready "
        "elapsed_ms=0.71 user=777002 detail=scheduled kind=callback"
    )

    event = parse_latency_event(line)

    assert event is not None
    assert event.trace == "tg:777002:9002"
    assert event.label == "timing:webhook_response_ready"
    assert event.elapsed_ms == 0.71


def test_summarize_lines_groups_api_and_cache_events_by_trace() -> None:
    lines = [
        "INFO [telegram_timing] trace=tg:1:2 stage=webhook_response_ready elapsed_ms=1.20 user=1\n",
        "INFO [telegram_timing] trace=tg:1:2 stage=webhook_to_background_finished elapsed_ms=8.40 user=1\n",
        "INFO [telegram_api_timing] trace=tg:1:2 method=sendMessage elapsed_ms=180.21 status=200 ok=True\n",
        "INFO [telegram_cache] trace=tg:1:2 categories=1 category_buckets=1 products=3 version=4 age_seconds=6.70 user=1\n",
    ]

    summaries = summarize_lines(lines)

    summary = summaries["tg:1:2"]
    assert summary.elapsed_for("timing:webhook_response_ready") == 1.2
    assert summary.elapsed_for("api:sendMessage") == 180.21
    assert summary.cache_version == 4
    assert summary.cache_age_seconds == 6.7
    assert summary.slowest_event() is not None
    assert summary.slowest_event().label == "api:sendMessage"


def test_analyze_stream_outputs_one_summary_per_trace() -> None:
    stream = StringIO(
        "\n".join(
            [
                "INFO [telegram_timing] trace=tg:1:2 stage=webhook_response_ready elapsed_ms=0.71 user=1",
                "INFO [telegram_timing] trace=tg:1:2 stage=webhook_to_background_finished elapsed_ms=2.44 user=1",
                "INFO [telegram_api_timing] trace=tg:1:2 method=answerCallbackQuery elapsed_ms=55.00 status=200 ok=True",
                "INFO [telegram_cache] trace=tg:1:2 categories=1 category_buckets=0 products=0 version=1 age_seconds=6.70 user=1",
            ]
        )
    )

    output = analyze_stream(stream)

    assert output == [
        "trace=tg:1:2 webhook_ack=0.71ms background_total=2.44ms "
        "sendMessage=- answerCallbackQuery=55.00ms "
        "slowest=api:answerCallbackQuery:55.00ms cache=v1 age=6.70s"
    ]
