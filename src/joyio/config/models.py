"""Typed configuration models used by the mapping engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


ButtonMode = Literal["tap", "hold"]
MouseButton = Literal["left", "middle", "right"]


@dataclass(frozen=True, slots=True)
class KeyMapping:
    key: str
    mode: ButtonMode
    type: Literal["key"] = "key"


@dataclass(frozen=True, slots=True)
class KeyChordMapping:
    keys: tuple[str, ...]
    mode: ButtonMode
    type: Literal["key_chord"] = "key_chord"


@dataclass(frozen=True, slots=True)
class MouseButtonMapping:
    button: MouseButton
    mode: ButtonMode
    type: Literal["mouse_button"] = "mouse_button"


@dataclass(frozen=True, slots=True)
class ToggleMapping:
    type: Literal["toggle"] = "toggle"


ButtonMapping = KeyMapping | KeyChordMapping | MouseButtonMapping | ToggleMapping


@dataclass(frozen=True, slots=True)
class DeviceConfig:
    left_address: str | None = None
    right_address: str | None = None


@dataclass(frozen=True, slots=True)
class ReconnectConfig:
    enabled: bool = True
    initial_delay: float = 1.0
    max_delay: float = 30.0
    multiplier: float = 2.0
    max_attempts: int | None = None


@dataclass(frozen=True, slots=True)
class RuntimeConfig:
    enabled: bool = True


@dataclass(frozen=True, slots=True)
class MouseConfig:
    stick: Literal["left_stick", "right_stick"]
    dead_zone: float = 0.12
    sensitivity: float = 900.0
    acceleration: float = 1.4
    max_speed: float = 1800.0
    invert_x: bool = False
    invert_y: bool = True


@dataclass(frozen=True, slots=True)
class ScrollConfig:
    stick: Literal["left_stick", "right_stick"]
    dead_zone: float = 0.18
    sensitivity: float = 18.0
    acceleration: float = 1.3
    max_speed: float = 30.0
    invert_x: bool = False
    invert_y: bool = True


@dataclass(frozen=True, slots=True)
class JoyIOConfig:
    version: Literal[1]
    device: DeviceConfig = field(default_factory=DeviceConfig)
    reconnect: ReconnectConfig = field(default_factory=ReconnectConfig)
    runtime: RuntimeConfig = field(default_factory=RuntimeConfig)
    mouse: MouseConfig | None = None
    scroll: ScrollConfig | None = None
    buttons: dict[str, ButtonMapping] = field(default_factory=dict)
