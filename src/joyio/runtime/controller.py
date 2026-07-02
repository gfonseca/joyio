"""Orchestrate normalized input, mapping, and output lifecycle."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
import time

from joyio.controls import JoyConSide
from joyio.devices import JoyConInput, read_managed_events, read_runtime_events
from joyio.events import DeviceStatusEvent
from joyio.mapping.actions import ToggleAction
from joyio.mapping.engine import MappingEngine
from joyio.output.backends import OutputBackend


def run_mapping(
    inputs: Sequence[JoyConInput],
    engine: MappingEngine,
    output: OutputBackend,
    *,
    on_mode_change: Callable[[bool], None] | None = None,
    clock: Callable[[], float] = time.monotonic,
    tick_interval: float = 1.0 / 120.0,
) -> None:
    """Run until interrupted or disconnected, always releasing held outputs."""

    try:
        next_tick = clock()
        for event in read_runtime_events(inputs, tick_interval=tick_interval):
            if event is not None:
                actions = engine.process(event)
                output_actions = []
                for action in actions:
                    if isinstance(action, ToggleAction):
                        changed = engine.set_enabled(not engine.enabled)
                        if changed:
                            output.emit(changed)
                        if on_mode_change is not None:
                            on_mode_change(engine.enabled)
                    else:
                        output_actions.append(action)
                if output_actions:
                    output.emit(output_actions)
            now = clock()
            if now >= next_tick:
                actions = engine.tick(now)
                if actions:
                    output.emit(actions)
                next_tick = now + tick_interval
    finally:
        try:
            output.release_all()
        finally:
            output.close()
            engine.reset()


def run_managed_mapping(
    addresses: Mapping[JoyConSide, str],
    engine: MappingEngine,
    output: OutputBackend,
    maintain_connections: Callable[[set[JoyConSide]], None],
    *,
    on_device_status: Callable[[DeviceStatusEvent], None] | None = None,
    on_mode_change: Callable[[bool], None] | None = None,
    clock: Callable[[], float] = time.monotonic,
    tick_interval: float = 1.0 / 120.0,
    maintenance_interval: float = 0.1,
) -> None:
    """Keep one output session while Joy-Con sides come and go independently."""

    active_sides: set[JoyConSide] = set()
    try:
        next_tick = clock()
        next_maintenance = next_tick
        for event in read_managed_events(addresses, tick_interval=tick_interval):
            now = clock()
            if isinstance(event, DeviceStatusEvent):
                if event.state == "connected":
                    active_sides.add(event.side)
                else:
                    active_sides.discard(event.side)
                    actions = engine.release_side(event.side)
                    if actions:
                        output.emit(actions)
                if on_device_status is not None:
                    on_device_status(event)
            elif event is not None:
                actions = engine.process(event)
                output_actions = []
                for action in actions:
                    if isinstance(action, ToggleAction):
                        changed = engine.set_enabled(not engine.enabled)
                        if changed:
                            output.emit(changed)
                        if on_mode_change is not None:
                            on_mode_change(engine.enabled)
                    else:
                        output_actions.append(action)
                if output_actions:
                    output.emit(output_actions)

            if now >= next_tick:
                actions = engine.tick(now)
                if actions:
                    output.emit(actions)
                next_tick = now + tick_interval
            if now >= next_maintenance:
                maintain_connections(active_sides)
                next_maintenance = now + maintenance_interval
    finally:
        try:
            output.release_all()
        finally:
            output.close()
            engine.reset()
