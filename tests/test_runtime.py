from __future__ import annotations

import pytest

from joyio.config.models import JoyIOConfig, KeyMapping
from joyio.devices import JoyConInput
from joyio.events import NormalizedEvent
from joyio.mapping.engine import MappingEngine
from joyio.runtime import controller


class RecordingOutput:
    def __init__(self) -> None:
        self.actions = []
        self.released = False
        self.closed = False

    def emit(self, actions) -> None:
        self.actions.extend(actions)

    def release_all(self) -> None:
        self.released = True

    def close(self) -> None:
        self.closed = True


def test_runtime_releases_output_after_input_failure(monkeypatch) -> None:
    pressed = NormalizedEvent("button", "a", "test", "right", 0, 1.0, "pressed", 1.0)

    def failing_reader(inputs):
        yield pressed
        raise OSError("disconnect")

    monkeypatch.setattr(controller, "read_runtime_events", failing_reader)
    output = RecordingOutput()
    engine = MappingEngine(
        JoyIOConfig(version=1, buttons={"right.a": KeyMapping("KEY_A", "hold")})
    )
    inputs = (
        JoyConInput("left", "Joy-Con (L)", "11:22:33:44:55:01", "left"),
        JoyConInput("right", "Joy-Con (R)", "11:22:33:44:55:02", "right"),
    )

    with pytest.raises(OSError, match="disconnect"):
        controller.run_mapping(inputs, engine, output)

    assert output.released is True
    assert output.closed is True
