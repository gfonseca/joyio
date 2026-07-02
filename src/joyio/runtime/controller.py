"""Orchestrate normalized input, mapping, and output lifecycle."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from queue import Empty
import sys
import time

from joyio.config import ConfigError, load_config
from joyio.controls import JoyConSide
from joyio.devices import JoyConInput, read_managed_events, read_runtime_events
from joyio.events import ConfigFileChanged, DeviceStatusEvent
from joyio.mapping.actions import ToggleAction
from joyio.mapping.engine import MappingEngine
from joyio.output.backends import OutputBackend


def _reload_config(
    path: str,
    engine: MappingEngine,
    output: OutputBackend,
    watcher: object | None = None,
    now: float = 0.0,
    *,
    force: bool = False,
) -> None:
    """Attempt atomic config reload; log result to stderr.

    *watcher* is a ConfigWatcher (or any object with ``debounce(now)``).
    When provided, reloads are gated on both filename-match (consume) and
    debounce timing.
    """
    if watcher is not None and not force:
        # consume() reads inotify events and returns True only when our
        # filename is among them (filters out unrelated directory noise).
        if hasattr(watcher, "consume"):
            if not watcher.consume():  # type: ignore[union-attr]
                return
        if hasattr(watcher, "debounce"):
            if not watcher.debounce(now):  # type: ignore[union-attr]
                return
    try:
        new_config = load_config(path)
    except ConfigError as error:
        print(f"  config: erro ao recarregar — {error}", file=sys.stderr)
        return
    actions = engine.reload(new_config)
    if actions:
        output.emit(actions)
    print(f"  config: recarregada — {path}", file=sys.stderr)


def _drain_control_queue(
    control_queue: object | None,
    engine: MappingEngine,
    output: OutputBackend,
    on_mode_change: Callable[[bool], None] | None,
    *,
    reload_path: str,
    config_watcher: object | None,
    now: float,
) -> bool:
    """Consume tray/control commands.

    Returns True when a quit request was received.
    """
    if control_queue is None:
        return False

    while True:
        try:
            command = control_queue.get_nowait()  # type: ignore[attr-defined]
        except Empty:
            return False

        if command == "toggle":
            changed = engine.set_enabled(not engine.enabled)
            if changed:
                output.emit(changed)
            if on_mode_change is not None:
                on_mode_change(engine.enabled)
        elif command == "reload":
            _reload_config(
                reload_path,
                engine,
                output,
                config_watcher,
                now,
                force=True,
            )
            if on_mode_change is not None:
                on_mode_change(engine.enabled)
        elif command == "quit":
            return True


def run_mapping(
    inputs: Sequence[JoyConInput],
    engine: MappingEngine,
    output: OutputBackend,
    *,
    on_mode_change: Callable[[bool], None] | None = None,
    clock: Callable[[], float] = time.monotonic,
    tick_interval: float = 1.0 / 120.0,
    config_fd: int | None = None,
    config_path: str = "",
    config_watcher: object | None = None,
    control_queue: object | None = None,
) -> None:
    """Run until interrupted or disconnected, always releasing held outputs."""

    try:
        next_tick = clock()
        for event in read_runtime_events(
            inputs,
            tick_interval=tick_interval,
            config_fd=config_fd,
            config_path=config_path,
        ):
            control_now = clock() if control_queue is not None else 0.0
            if _drain_control_queue(
                control_queue,
                engine,
                output,
                on_mode_change,
                reload_path=config_path,
                config_watcher=config_watcher,
                now=control_now,
            ):
                raise KeyboardInterrupt("tray requested quit")
            if isinstance(event, ConfigFileChanged):
                _reload_config(event.path, engine, output, config_watcher, clock())
                continue
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
    config_fd: int | None = None,
    config_path: str = "",
    config_watcher: object | None = None,
    control_queue: object | None = None,
) -> None:
    """Keep one output session while Joy-Con sides come and go independently."""

    active_sides: set[JoyConSide] = set()
    try:
        next_tick = clock()
        next_maintenance = next_tick
        for event in read_managed_events(
            addresses,
            tick_interval=tick_interval,
            config_fd=config_fd,
            config_path=config_path,
        ):
            now = clock()
            control_now = now if control_queue is not None else 0.0
            if _drain_control_queue(
                control_queue,
                engine,
                output,
                on_mode_change,
                reload_path=config_path,
                config_watcher=config_watcher,
                now=control_now,
            ):
                raise KeyboardInterrupt("tray requested quit")
            if isinstance(event, ConfigFileChanged):
                _reload_config(event.path, engine, output, config_watcher, now)
                continue
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
