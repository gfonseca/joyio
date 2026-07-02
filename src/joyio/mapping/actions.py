"""Output-independent actions produced by the mapping engine."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Literal


@dataclass(frozen=True, slots=True)
class KeyAction:
    key: str
    pressed: bool
    type: Literal["key"] = "key"


@dataclass(frozen=True, slots=True)
class MouseButtonAction:
    button: str
    pressed: bool
    type: Literal["mouse_button"] = "mouse_button"


@dataclass(frozen=True, slots=True)
class MouseMoveAction:
    dx: int
    dy: int
    type: Literal["mouse_move"] = "mouse_move"


@dataclass(frozen=True, slots=True)
class MouseScrollAction:
    dx: int
    dy: int
    type: Literal["mouse_scroll"] = "mouse_scroll"


@dataclass(frozen=True, slots=True)
class ToggleAction:
    type: Literal["toggle"] = "toggle"


OutputAction = KeyAction | MouseButtonAction | MouseMoveAction | MouseScrollAction
ControlAction = ToggleAction
MappingAction = OutputAction | ControlAction


def action_json(action: OutputAction) -> str:
    if isinstance(action, KeyAction):
        data = {"key": action.key, "pressed": action.pressed, "type": action.type}
    elif isinstance(action, MouseButtonAction):
        data = {
            "button": action.button,
            "pressed": action.pressed,
            "type": action.type,
        }
    else:
        data = {"dx": action.dx, "dy": action.dy, "type": action.type}
    return json.dumps(
        data, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    )
