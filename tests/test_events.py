from __future__ import annotations

import pytest
from evdev import AbsInfo, InputEvent, ecodes

from joyio.events import normalize_axis, normalize_event


AXIS_INFO = AbsInfo(value=128, min=0, max=255, fuzz=0, flat=8, resolution=0)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (0, -1.0),
        (255, 1.0),
        (127, pytest.approx(-0.0039215686)),
        (128, pytest.approx(0.0039215686)),
    ],
)
def test_normalize_axis(raw: int, expected: float) -> None:
    assert normalize_axis(raw, AXIS_INFO) == expected


def test_normalize_axis_clamps_values() -> None:
    assert normalize_axis(-100, AXIS_INFO) == -1.0
    assert normalize_axis(500, AXIS_INFO) == 1.0


def test_normalize_button_preserves_press_and_release() -> None:
    pressed = InputEvent(10, 250_000, ecodes.EV_KEY, ecodes.BTN_SOUTH, 1)
    released = InputEvent(11, 0, ecodes.EV_KEY, ecodes.BTN_SOUTH, 0)

    pressed_result = normalize_event(pressed, side="right")
    released_result = normalize_event(released, side="right")

    assert pressed_result is not None
    assert pressed_result.kind == "button"
    assert pressed_result.control == "b"
    assert pressed_result.source_control == "BTN_SOUTH"
    assert pressed_result.side == "right"
    assert pressed_result.state == "pressed"
    assert pressed_result.timestamp == 10.25
    assert released_result is not None
    assert released_result.state == "released"


def test_normalize_absolute_axis() -> None:
    event = InputEvent(1, 0, ecodes.EV_ABS, ecodes.ABS_X, 255)

    result = normalize_event(event, side="left", absinfo=AXIS_INFO)

    assert result is not None
    assert result.kind == "axis"
    assert result.control == "left_stick_x"
    assert result.source_control == "ABS_X"
    assert result.value == 1.0


def test_ignores_sync_events() -> None:
    event = InputEvent(1, 0, ecodes.EV_SYN, ecodes.SYN_REPORT, 0)
    assert normalize_event(event, side="left") is None


def test_unknown_control_is_explicitly_marked() -> None:
    event = InputEvent(1, 0, ecodes.EV_KEY, ecodes.BTN_TRIGGER_HAPPY1, 1)

    result = normalize_event(event, side="right")

    assert result is not None
    assert result.control.startswith("unmapped:")
