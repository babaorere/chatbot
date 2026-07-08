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
        "INFO [telegram_timing] trace=tg:1:2 stage=menu_stack_loaded_from_snapshot elapsed_ms=0.02 user=1\n",
        "INFO [telegram_api_timing] trace=tg:1:2 method=sendMessage elapsed_ms=180.21 status=200 ok=True\n",
        "INFO [telegram_cache] trace=tg:1:2 categories=1 category_buckets=1 products=3 version=4 age_seconds=6.70 user=1\n",
    ]

    summaries = summarize_lines(lines)

    summary = summaries["tg:1:2"]
    assert summary.elapsed_for("timing:webhook_response_ready") == 1.2
    assert summary.elapsed_for("timing:menu_stack_loaded_from_snapshot") == 0.02
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
                "INFO [telegram_timing] trace=tg:1:2 stage=callback_validated elapsed_ms=0.31 user=1",
                "INFO [telegram_timing] trace=tg:1:2 stage=menu_stack_loaded_from_snapshot elapsed_ms=0.01 user=1",
                "INFO [telegram_api_timing] trace=tg:1:2 method=answerCallbackQuery elapsed_ms=55.00 status=200 ok=True",
                "INFO [telegram_cache] trace=tg:1:2 categories=1 category_buckets=0 products=0 version=1 age_seconds=6.70 user=1",
            ]
        )
    )

    output = analyze_stream(stream)

    assert output == [
        "trace=tg:1:2 webhook_ack=0.71ms background_total=2.44ms "
        "callback_validated=0.31ms menu_stack_snapshot=0.01ms "
        "sendMessage=- answerCallbackQuery=55.00ms "
        "slowest=api:answerCallbackQuery:55.00ms cache=v1 age=6.70s"
    ]


def test_analyze_stream_with_aggregate_outputs_percentiles_by_stage() -> None:
    stream = StringIO(
        "\n".join(
            [
                "INFO [telegram_timing] trace=tg:1:1 stage=webhook_response_ready elapsed_ms=1.00 user=1",
                "INFO [telegram_timing] trace=tg:2:2 stage=webhook_response_ready elapsed_ms=2.00 user=2",
                "INFO [telegram_timing] trace=tg:3:3 stage=webhook_response_ready elapsed_ms=3.00 user=3",
                "INFO [telegram_api_timing] trace=tg:1:1 method=sendMessage elapsed_ms=100.00 status=200 ok=True",
                "INFO [telegram_api_timing] trace=tg:2:2 method=sendMessage elapsed_ms=200.00 status=200 ok=True",
                "INFO [telegram_api_timing] trace=tg:3:3 method=sendMessage elapsed_ms=300.00 status=200 ok=True",
            ]
        )
    )

    output = analyze_stream(stream, include_aggregate=True)

    assert output[-2:] == [
        "aggregate=api:sendMessage count=3 p50=200.00ms p95=300.00ms p99=300.00ms max=300.00ms",
        "aggregate=timing:webhook_response_ready count=3 p50=2.00ms p95=3.00ms p99=3.00ms max=3.00ms",
    ]
