"""Normalization of Linux input events into canonical JoyIO events."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import json
from typing import Any, Literal

from evdev import AbsInfo, InputEvent, ecodes

from joyio.controls import JoyConSide, canonical_control


_BUTTON_STATES = {0: "released", 1: "pressed", 2: "repeat"}
_GAMEPAD_DIRECTIONS = frozenset(
    {"BTN_SOUTH", "BTN_EAST", "BTN_NORTH", "BTN_WEST"}
)


@dataclass(frozen=True, slots=True)
class NormalizedEvent:
    kind: str
    control: str
    source_control: str
    side: JoyConSide
    code: int
    value: float
    state: str | None
    timestamp: float

    def to_json(self) -> str:
        return json.dumps(
            {
                "code": self.code,
                "control": self.control,
                "kind": self.kind,
                "side": self.side,
                "source_control": self.source_control,
                "state": self.state,
                "timestamp": self.timestamp,
                "value": self.value,
            },
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )


@dataclass(frozen=True, slots=True)
class DeviceStatusEvent:
    """Report one Joy-Con evdev node entering or leaving the runtime."""

    side: JoyConSide
    state: Literal["connected", "disconnected"]
    path: str


@lru_cache(maxsize=None)
def event_code_name(event_type: int, code: int) -> str:
    names: Any = ecodes.bytype.get(event_type, {}).get(code)
    if names is None:
        return f"UNKNOWN_{code}"
    if isinstance(names, tuple):
        for name in names:
            if name in _GAMEPAD_DIRECTIONS:
                return str(name)
        return str(names[-1])
    return str(names)


def normalize_axis(value: int, info: AbsInfo) -> float:
    """Normalize an evdev absolute axis around its midpoint to [-1.0, 1.0]."""

    minimum = info.min
    maximum = info.max
    if maximum <= minimum:
        return 0.0
    center = (minimum + maximum) / 2.0
    if value >= center:
        denominator = maximum - center
    else:
        denominator = center - minimum
    if denominator <= 0:
        return 0.0
    normalized = (value - center) / denominator
    return max(-1.0, min(1.0, normalized))


def normalize_event(
    event: InputEvent,
    *,
    side: JoyConSide,
    absinfo: AbsInfo | None = None,
) -> NormalizedEvent | None:
    source_control = event_code_name(event.type, event.code)
    control = canonical_control(side, event.type, event.code)
    if control is None:
        control = f"unmapped:{source_control.casefold()}"
    if event.type == ecodes.EV_KEY:
        return NormalizedEvent(
            kind="button",
            control=control,
            source_control=source_control,
            side=side,
            code=event.code,
            value=float(event.value),
            state=_BUTTON_STATES.get(event.value, "unknown"),
            timestamp=event.timestamp(),
        )
    if event.type == ecodes.EV_ABS and absinfo is not None:
        return NormalizedEvent(
            kind="axis",
            control=control,
            source_control=source_control,
            side=side,
            code=event.code,
            value=normalize_axis(event.value, absinfo),
            state=None,
            timestamp=event.timestamp(),
        )
    return None
