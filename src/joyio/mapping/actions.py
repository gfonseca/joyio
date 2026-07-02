"""Output-independent actions produced by the mapping engine."""

from __future__ import annotations

from dataclasses import asdict, dataclass
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


OutputAction = KeyAction | MouseButtonAction | MouseMoveAction | MouseScrollAction


def action_json(action: OutputAction) -> str:
    return json.dumps(asdict(action), ensure_ascii=False, sort_keys=True)
