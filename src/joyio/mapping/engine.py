"""Stateful mapping engine with time-based analog mouse integration."""

from __future__ import annotations

import math

from joyio.config.models import (
    JoyIOConfig,
    KeyChordMapping,
    KeyMapping,
    MouseButtonMapping,
    MouseConfig,
    ScrollConfig,
)
from joyio.events import NormalizedEvent
from joyio.mapping.actions import (
    KeyAction,
    MouseButtonAction,
    MouseMoveAction,
    MouseScrollAction,
    OutputAction,
)


class MappingEngine:
    """Convert normalized Joy-Con events into output-independent actions."""

    def __init__(self, config: JoyIOConfig) -> None:
        self.config = config
        self._axes: dict[str, float] = {}
        self._last_tick: float | None = None
        self._mouse_residual = (0.0, 0.0)
        self._scroll_residual = (0.0, 0.0)
        self._held_controls: set[tuple[str, str]] = set()

    def process(self, event: NormalizedEvent) -> list[OutputAction]:
        if event.kind == "axis":
            self._update_axis(event)
            return []
        if event.kind != "button" or event.state not in {"pressed", "released"}:
            return []
        control_id = (event.side, event.control)
        mapping = self.config.buttons.get(f"{event.side}.{event.control}")
        if mapping is None:
            return []
        pressed = event.state == "pressed"
        if pressed and control_id in self._held_controls:
            return []
        if not pressed and control_id not in self._held_controls:
            return []
        if pressed:
            self._held_controls.add(control_id)
        else:
            self._held_controls.remove(control_id)

        if mapping.mode == "tap":
            return self._tap(mapping) if pressed else []
        return self._transition(mapping, pressed)

    def tick(self, now: float) -> list[OutputAction]:
        """Integrate stick velocity using monotonic seconds."""

        previous = self._last_tick
        self._last_tick = now
        if previous is None:
            return []
        # A stalled process must not turn one late tick into a pointer jump.
        elapsed = max(0.0, min(now - previous, 0.1))
        actions: list[OutputAction] = []
        if self.config.mouse is not None:
            dx, dy, self._mouse_residual = self._integrate(
                self.config.mouse, elapsed, self._mouse_residual
            )
            if dx or dy:
                actions.append(MouseMoveAction(dx=dx, dy=dy))
        if self.config.scroll is not None:
            dx, dy, self._scroll_residual = self._integrate(
                self.config.scroll, elapsed, self._scroll_residual
            )
            if dx or dy:
                actions.append(MouseScrollAction(dx=dx, dy=dy))
        return actions

    def reset(self) -> None:
        self._axes.clear()
        self._last_tick = None
        self._mouse_residual = (0.0, 0.0)
        self._scroll_residual = (0.0, 0.0)
        self._held_controls.clear()

    def _update_axis(self, event: NormalizedEvent) -> None:
        self._axes[event.control] = event.value

    def _velocity(self, config: MouseConfig | ScrollConfig) -> tuple[float, float]:
        axis_x = self._axes.get(f"{config.stick}_x", 0.0)
        axis_y = self._axes.get(f"{config.stick}_y", 0.0)
        x = -axis_x if config.invert_x else axis_x
        y = -axis_y if config.invert_y else axis_y
        magnitude = math.hypot(x, y)
        if magnitude <= config.dead_zone or magnitude == 0.0:
            return 0.0, 0.0
        direction_x = x / magnitude
        direction_y = y / magnitude
        scaled = min(
            1.0, (magnitude - config.dead_zone) / (1.0 - config.dead_zone)
        )
        speed = min(
            config.max_speed, config.sensitivity * scaled**config.acceleration
        )
        return direction_x * speed, direction_y * speed

    def _integrate(
        self,
        config: MouseConfig | ScrollConfig,
        elapsed: float,
        residual: tuple[float, float],
    ) -> tuple[int, int, tuple[float, float]]:
        vx, vy = self._velocity(config)
        total_x = vx * elapsed + residual[0]
        total_y = vy * elapsed + residual[1]
        dx = math.trunc(total_x)
        dy = math.trunc(total_y)
        return dx, dy, (total_x - dx, total_y - dy)

    @staticmethod
    def _transition(
        mapping: KeyMapping | KeyChordMapping | MouseButtonMapping, pressed: bool
    ) -> list[OutputAction]:
        if isinstance(mapping, KeyMapping):
            return [KeyAction(mapping.key, pressed)]
        if isinstance(mapping, MouseButtonMapping):
            return [MouseButtonAction(mapping.button, pressed)]
        keys = mapping.keys if pressed else tuple(reversed(mapping.keys))
        return [KeyAction(key, pressed) for key in keys]

    @classmethod
    def _tap(
        cls, mapping: KeyMapping | KeyChordMapping | MouseButtonMapping
    ) -> list[OutputAction]:
        return cls._transition(mapping, True) + cls._transition(mapping, False)
