from __future__ import annotations

import json
from pathlib import Path

import pytest
from evdev import ecodes

from joyio.controls import AXIS_CONTROLS, BUTTON_CONTROLS, canonical_control
from joyio.events import event_code_name


EXPECTED_LEFT_BUTTONS = {
    ecodes.BTN_DPAD_UP: "dpad_up",
    ecodes.BTN_DPAD_DOWN: "dpad_down",
    ecodes.BTN_DPAD_LEFT: "dpad_left",
    ecodes.BTN_DPAD_RIGHT: "dpad_right",
    ecodes.BTN_TL: "l",
    ecodes.BTN_TL2: "zl",
    ecodes.BTN_SELECT: "minus",
    ecodes.BTN_THUMBL: "left_stick_press",
    ecodes.BTN_Z: "capture",
    ecodes.BTN_TR: "sl",
    ecodes.BTN_TR2: "sr",
}

EXPECTED_RIGHT_BUTTONS = {
    ecodes.BTN_EAST: "a",
    ecodes.BTN_SOUTH: "b",
    ecodes.BTN_NORTH: "x",
    ecodes.BTN_WEST: "y",
    ecodes.BTN_TR: "r",
    ecodes.BTN_TR2: "zr",
    ecodes.BTN_START: "plus",
    ecodes.BTN_THUMBR: "right_stick_press",
    ecodes.BTN_MODE: "home",
    ecodes.BTN_TL: "sl",
    ecodes.BTN_TL2: "sr",
}


def test_all_button_mappings_are_explicit() -> None:
    assert BUTTON_CONTROLS["left"] == EXPECTED_LEFT_BUTTONS
    assert BUTTON_CONTROLS["right"] == EXPECTED_RIGHT_BUTTONS
    assert len(set(BUTTON_CONTROLS["left"].values())) == len(BUTTON_CONTROLS["left"])
    assert len(set(BUTTON_CONTROLS["right"].values())) == len(
        BUTTON_CONTROLS["right"]
    )


def test_all_axis_mappings_are_explicit() -> None:
    assert AXIS_CONTROLS == {
        "left": {ecodes.ABS_X: "left_stick_x", ecodes.ABS_Y: "left_stick_y"},
        "right": {
            ecodes.ABS_RX: "right_stick_x",
            ecodes.ABS_RY: "right_stick_y",
        },
    }


@pytest.mark.parametrize(
    "fixture_name", ["joycon_left_observed.jsonl", "joycon_right_observed.jsonl"]
)
def test_observed_hardware_fixture_matches_contract(fixture_name: str) -> None:
    fixture = Path(__file__).parent / "fixtures" / fixture_name
    records = [json.loads(line) for line in fixture.read_text().splitlines()]

    assert records
    for record in records:
        event_type = ecodes.EV_KEY if record["kind"] == "button" else ecodes.EV_ABS
        assert (
            canonical_control(record["side"], event_type, record["code"])
            == record["control"]
        )
        assert event_code_name(event_type, record["code"]) == record["source_control"]
