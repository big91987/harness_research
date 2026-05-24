from __future__ import annotations

from harness.event_bus import EventBus
from harness.trace import TraceRecorder


def test_event_bus_publishes_to_matching_subscribers() -> None:
    bus = EventBus()
    seen: list[dict] = []

    bus.subscribe("tool_call", seen.append)
    bus.publish("turn_start", session_id="s1")
    bus.publish("tool_call", session_id="s1", name="read_file")

    assert [event["type"] for event in seen] == ["tool_call"]
    assert seen[0]["name"] == "read_file"
    assert bus.history(event_type="tool_call")[0]["session_id"] == "s1"


def test_trace_recorder_publishes_events_to_bus(tmp_path) -> None:  # noqa: ANN001
    bus = EventBus()
    seen: list[dict] = []
    bus.subscribe("*", seen.append)
    trace = TraceRecorder(tmp_path / "trace.jsonl", event_bus=bus)

    trace.record("turn_start", session_id="s1")

    assert seen[0]["type"] == "turn_start"
    assert seen[0]["session_id"] == "s1"
    assert trace.read_events()[0]["type"] == "turn_start"
