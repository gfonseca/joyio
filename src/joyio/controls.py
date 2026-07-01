"""Canonical JoyIO control names for Linux hid-nintendo events."""

from __future__ import annotations

from typing import Literal

from evdev import ecodes


JoyConSide = Literal["left", "right"]


BUTTON_CONTROLS: dict[JoyConSide, dict[int, str]] = {
    "left": {
        ecodes.BTN_DPAD_UP: "dpad_up",
        ecodes.BTN_DPAD_DOWN: "dpad_down",
        ecodes.BTN_DPAD_LEFT: "dpad_left",
        ecodes.BTN_DPAD_RIGHT: "dpad_right",
        ecodes.BTN_TL: "l",
        ecodes.BTN_TL2: "zl",
        ecodes.BTN_SELECT: "minus",
        ecodes.BTN_THUMBL: "left_stick_press",
        ecodes.BTN_Z: "capture",
        # hid-nintendo uses the unused right-side shoulder codes for rail keys.
        ecodes.BTN_TR: "sl",
        ecodes.BTN_TR2: "sr",
    },
    "right": {
        ecodes.BTN_EAST: "a",
        ecodes.BTN_SOUTH: "b",
        ecodes.BTN_NORTH: "x",
        ecodes.BTN_WEST: "y",
        ecodes.BTN_TR: "r",
        ecodes.BTN_TR2: "zr",
        ecodes.BTN_START: "plus",
        ecodes.BTN_THUMBR: "right_stick_press",
        ecodes.BTN_MODE: "home",
        # hid-nintendo uses the unused left-side shoulder codes for rail keys.
        ecodes.BTN_TL: "sl",
        ecodes.BTN_TL2: "sr",
    },
}


AXIS_CONTROLS: dict[JoyConSide, dict[int, str]] = {
    "left": {
        ecodes.ABS_X: "left_stick_x",
        ecodes.ABS_Y: "left_stick_y",
    },
    "right": {
        ecodes.ABS_RX: "right_stick_x",
        ecodes.ABS_RY: "right_stick_y",
    },
}


def canonical_control(side: JoyConSide, event_type: int, code: int) -> str | None:
    """Translate a side-specific evdev code to a stable JoyIO name."""

    if event_type == ecodes.EV_KEY:
        return BUTTON_CONTROLS[side].get(code)
    if event_type == ecodes.EV_ABS:
        return AXIS_CONTROLS[side].get(code)
    return None
