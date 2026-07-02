"""Stateful mapping engine with time-based analog mouse integration."""

from __future__ import annotations

import math

from joyio.controls import JoyConSide
from joyio.config.models import (
    BoostMapping,
    JoyIOConfig,
    KeyChordMapping,
    KeyMapping,
    MouseButtonMapping,
    MouseConfig,
    ScrollConfig,
    ToggleMapping,
)
from joyio.events import NormalizedEvent
from joyio.mapping.actions import (
    ControlAction,
    KeyAction,
    MouseButtonAction,
    MouseMoveAction,
    MouseScrollAction,
    MappingAction,
    OutputAction,
    ToggleAction,
)


class MappingEngine:
    """Convert normalized Joy-Con events into output-independent actions."""

    def __init__(self, config: JoyIOConfig) -> None:
        self.config = config
        self._enabled = config.runtime.enabled
        self._axes: dict[str, float] = {}
        self._mouse_controls = self._axis_controls(config.mouse)
        self._scroll_controls = self._axis_controls(config.scroll)
        self._mouse_velocity = (0.0, 0.0)
        self._scroll_velocity = (0.0, 0.0)
        self._last_tick: float | None = None
        self._mouse_residual = (0.0, 0.0)
        self._scroll_residual = (0.0, 0.0)
        self._held_controls: set[tuple[str, str]] = set()
        self._boost_controls: dict[tuple[str, str], float] = {}
        self._mouse_boost = 1.0

    @property
    def enabled(self) -> bool:
        return self._enabled

    def set_enabled(self, enabled: bool) -> list[OutputAction]:
        if self._enabled == enabled:
            return []
        self._enabled = enabled
        if enabled:
            self._last_tick = None
            return []
        actions = self.release_all()
        self._last_tick = None
        return actions

    def process(self, event: NormalizedEvent) -> list[MappingAction]:
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
        if isinstance(mapping, ToggleMapping):
            if pressed and control_id in self._held_controls:
                return []
            if not pressed and control_id not in self._held_controls:
                return []
            if pressed:
                self._held_controls.add(control_id)
            else:
                self._held_controls.remove(control_id)
            return [ToggleAction()] if pressed else []
        if isinstance(mapping, BoostMapping):
            if not self._enabled:
                return []
            if pressed and control_id in self._held_controls:
                return []
            if not pressed and control_id not in self._held_controls:
                return []
            if pressed:
                self._held_controls.add(control_id)
                self._boost_controls[control_id] = mapping.factor
            else:
                self._held_controls.remove(control_id)
                self._boost_controls.pop(control_id, None)
            self._recompute_boost()
            return []
        if not self._enabled:
            return []
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
        if not self._enabled:
            return []
        if previous is None:
            return []
        # A stalled process must not turn one late tick into a pointer jump.
        elapsed = max(0.0, min(now - previous, 0.1))
        actions: list[OutputAction] = []
        if self.config.mouse is not None:
            boosted_velocity = (
                self._mouse_velocity[0] * self._mouse_boost,
                self._mouse_velocity[1] * self._mouse_boost,
            )
            dx, dy, self._mouse_residual = self._integrate(
                boosted_velocity, elapsed, self._mouse_residual
            )
            if dx or dy:
                actions.append(MouseMoveAction(dx=dx, dy=dy))
        if self.config.scroll is not None:
            dx, dy, self._scroll_residual = self._integrate(
                self._scroll_velocity, elapsed, self._scroll_residual
            )
            if dx or dy:
                actions.append(MouseScrollAction(dx=dx, dy=dy))
        return actions

    def reload(self, config: JoyIOConfig) -> list[OutputAction]:
        """Atomically swap to a new configuration, releasing stale holds.

        Returns actions for any holds that were released because their
        mapping changed type, mode, or was removed from the new config.
        """
        # Release holds whose mapping changed or vanished.
        actions: list[OutputAction] = []
        stale: set[tuple[str, str]] = set()
        for side, control in sorted(self._held_controls):
            mapping_id = f"{side}.{control}"
            old = self.config.buttons.get(mapping_id)
            new = config.buttons.get(mapping_id)
            if self._mapping_changed(old, new):
                stale.add((side, control))
                if old is not None and not isinstance(old, (ToggleMapping, BoostMapping)):
                    if old.mode == "hold":
                        actions.extend(self._transition(old, False))
                self._boost_controls.pop((side, control), None)
        self._held_controls -= stale

        # Swap config and recompute derived state.
        prev_enabled = self._enabled
        self.config = config
        self._enabled = config.runtime.enabled
        self._mouse_controls = self._axis_controls(config.mouse)
        self._scroll_controls = self._axis_controls(config.scroll)

        if config.mouse is not None:
            self._mouse_velocity = self._velocity(config.mouse)
        else:
            self._mouse_velocity = (0.0, 0.0)
            self._mouse_residual = (0.0, 0.0)
        if config.scroll is not None:
            self._scroll_velocity = self._velocity(config.scroll)
        else:
            self._scroll_velocity = (0.0, 0.0)
            self._scroll_residual = (0.0, 0.0)

        self._recompute_boost()
        if prev_enabled != self._enabled:
            self._last_tick = None
        return actions

    @staticmethod
    def _mapping_changed(
        old: object | None, new: object | None
    ) -> bool:
        """Two mappings are the same if they have identical type and semantics."""
        if old is None or new is None:
            return True
        if type(old) is not type(new):
            return True
        # Compare by dataclass fields — all mapping types are frozen.
        if isinstance(old, KeyMapping) and isinstance(new, KeyMapping):
            return old.key != new.key or old.mode != new.mode
        if isinstance(old, KeyChordMapping) and isinstance(new, KeyChordMapping):
            return old.keys != new.keys or old.mode != new.mode
        if isinstance(old, MouseButtonMapping) and isinstance(new, MouseButtonMapping):
            return old.button != new.button or old.mode != new.mode
        if isinstance(old, BoostMapping) and isinstance(new, BoostMapping):
            return old.factor != new.factor
        # ToggleMapping has no fields.
        return False

    def reset(self) -> None:
        self._enabled = self.config.runtime.enabled
        self._axes.clear()
        self._mouse_velocity = (0.0, 0.0)
        self._scroll_velocity = (0.0, 0.0)
        self._last_tick = None
        self._mouse_residual = (0.0, 0.0)
        self._scroll_residual = (0.0, 0.0)
        self._held_controls.clear()
        self._boost_controls.clear()
        self._mouse_boost = 1.0

    def release_all(self) -> list[OutputAction]:
        actions: list[OutputAction] = []
        controls = sorted(self._held_controls)
        for side, control in controls:
            mapping = self.config.buttons.get(f"{side}.{control}")
            if mapping is not None and not isinstance(mapping, (ToggleMapping, BoostMapping)):
                if mapping.mode == "hold":
                    actions.extend(self._transition(mapping, False))
        self._held_controls.clear()
        self._mouse_velocity = (0.0, 0.0)
        self._scroll_velocity = (0.0, 0.0)
        self._mouse_residual = (0.0, 0.0)
        self._scroll_residual = (0.0, 0.0)
        self._boost_controls.clear()
        self._mouse_boost = 1.0
        return actions

    def release_side(self, side: JoyConSide) -> list[OutputAction]:
        """Release only state originating from a disconnected Joy-Con."""

        actions: list[OutputAction] = []
        controls = sorted(item for item in self._held_controls if item[0] == side)
        for control_id in controls:
            mapping = self.config.buttons.get(f"{control_id[0]}.{control_id[1]}")
            if mapping is not None and not isinstance(mapping, (ToggleMapping, BoostMapping)):
                if mapping.mode == "hold":
                    actions.extend(self._transition(mapping, False))
            self._boost_controls.pop(control_id, None)
            self._held_controls.remove(control_id)

        stick = "left_stick" if side == "left" else "right_stick"
        changed = False
        for suffix in ("_x", "_y"):
            control = f"{stick}{suffix}"
            if self._axes.pop(control, None) is not None:
                changed = True
        if changed:
            if self.config.mouse is not None and self.config.mouse.stick == stick:
                self._mouse_velocity = (0.0, 0.0)
                self._mouse_residual = (0.0, 0.0)
            if self.config.scroll is not None and self.config.scroll.stick == stick:
                self._scroll_velocity = (0.0, 0.0)
                self._scroll_residual = (0.0, 0.0)
        self._recompute_boost()
        return actions

    def _update_axis(self, event: NormalizedEvent) -> None:
        if self._axes.get(event.control) == event.value:
            return
        self._axes[event.control] = event.value
        if self.config.mouse is not None and event.control in self._mouse_controls:
            self._mouse_velocity = self._velocity(self.config.mouse)
        if self.config.scroll is not None and event.control in self._scroll_controls:
            self._scroll_velocity = self._velocity(self.config.scroll)

    @staticmethod
    def _axis_controls(config: MouseConfig | ScrollConfig | None) -> frozenset[str]:
        if config is None:
            return frozenset()
        return frozenset({f"{config.stick}_x", f"{config.stick}_y"})

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
        velocity: tuple[float, float],
        elapsed: float,
        residual: tuple[float, float],
    ) -> tuple[int, int, tuple[float, float]]:
        vx, vy = velocity
        total_x = vx * elapsed + residual[0]
        total_y = vy * elapsed + residual[1]
        dx = math.trunc(total_x)
        dy = math.trunc(total_y)
        return dx, dy, (total_x - dx, total_y - dy)

    def _recompute_boost(self) -> None:
        self._mouse_boost = max(self._boost_controls.values(), default=1.0)

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
