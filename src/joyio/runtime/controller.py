"""Orchestrate normalized input, mapping, and output lifecycle."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from queue import Empty
import sys
import time

from joyio.config import ConfigError, load_config
from joyio.controls import JoyConSide
from joyio.devices import JoyConInput, read_managed_events, read_runtime_events, set_grabbed
from joyio.events import ConfigFileChanged, DeviceStatusEvent, NormalizedEvent
from joyio.mapping.actions import ToggleAction
from joyio.mapping.engine import MappingEngine
from joyio.output.backends import OutputBackend
from joyio.output.gamepad import GamepadError, VirtualGamepad


# ── gamepad mode helpers ──────────────────────────────────────────────

def _switch_gamepad(
    gamepad_ref: list[VirtualGamepad | None],
    enabled: bool,
) -> None:
    """Create or close the VirtualGamepad when toggling between modes.

    * enabled = True  → keyboard/mouse mode (close gamepad)
    * enabled = False → gamepad mode (create gamepad)
    """
    if not enabled and gamepad_ref[0] is None:
        try:
            gamepad_ref[0] = VirtualGamepad()
            print("  gamepad: criado — JoyIO Virtual Gamepad", file=sys.stderr)
        except GamepadError as error:
            print(f"  gamepad: erro ao criar — {error}", file=sys.stderr)
    elif enabled and gamepad_ref[0] is not None:
        gamepad_ref[0].close()
        gamepad_ref[0] = None
        print("  gamepad: fechado", file=sys.stderr)


def _route_to_gamepad(
    gamepad: VirtualGamepad | None,
    event: NormalizedEvent,
) -> None:
    """Forward a normalized Joy-Con event to the virtual gamepad."""
    if gamepad is None:
        return
    if event.kind == "button":
        gamepad.emit_joyio_button(
            event.side, event.control, event.state == "pressed"
        )
    elif event.kind == "axis":
        gamepad.emit_joyio_axis(event.side, event.control, event.value)


def _release_gamepad_side(
    gamepad: VirtualGamepad | None,
    side: JoyConSide,
) -> None:
    """Release all held buttons for *side* on the gamepad."""
    if gamepad is None:
        return
    # Release all possible buttons for this side (idempotent — the gamepad
    # tracks press counts internally and ignores redundant releases).
    controls: dict[JoyConSide, list[str]] = {
        "left": [
            "dpad_up", "dpad_down", "dpad_left", "dpad_right",
            "l", "zl", "minus", "left_stick_press", "capture",
            "sl", "sr",
        ],
        "right": [
            "a", "b", "x", "y", "r", "zr", "plus",
            "right_stick_press", "home",
            "sl", "sr",
        ],
    }
    for control in controls.get(side, []):
        gamepad.emit_joyio_button(side, control, False)


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
    gamepad_ref: list[VirtualGamepad | None] | None = None,
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
            prev_enabled = engine.enabled
            actions = engine.set_enabled(not engine.enabled)
            if engine.enabled != prev_enabled:
                if actions:
                    output.emit(actions)
                _switch_gamepad(gamepad_ref, engine.enabled)
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
            _switch_gamepad(gamepad_ref, engine.enabled)
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
    grabbed_devices: list | None = None,
) -> None:
    """Run until interrupted or disconnected, always releasing held outputs.

    Routes Joy-Con events to the keyboard/mouse engine when enabled, or to
    a combined VirtualGamepad when disabled (gamepad mode).
    """

    gamepad_ref: list[VirtualGamepad | None] = [None]

    # Create gamepad immediately if starting in gamepad mode.
    _switch_gamepad(gamepad_ref, engine.enabled)

    try:
        next_tick = clock()
        for event in read_runtime_events(
            inputs,
            tick_interval=tick_interval,
            config_fd=config_fd,
            config_path=config_path,
            grabbed=grabbed_devices,
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
                gamepad_ref=gamepad_ref,
            ):
                raise KeyboardInterrupt("tray requested quit")
            if isinstance(event, ConfigFileChanged):
                _reload_config(event.path, engine, output, config_watcher, clock())
                _switch_gamepad(gamepad_ref, engine.enabled)
                continue
            if event is not None:
                # Always let the engine inspect the event first — toggle
                # buttons must work in both modes (the engine always
                # processes ToggleMapping regardless of enabled state).
                actions = engine.process(event)
                toggled = False
                output_actions = []
                for action in actions:
                    if isinstance(action, ToggleAction):
                        prev_enabled = engine.enabled
                        release_actions = engine.set_enabled(
                            not engine.enabled
                        )
                        if engine.enabled != prev_enabled:
                            if release_actions:
                                output.emit(release_actions)
                            _switch_gamepad(gamepad_ref, engine.enabled)
                        if on_mode_change is not None:
                            on_mode_change(engine.enabled)
                        toggled = True
                    elif engine.enabled:
                        output_actions.append(action)
                if output_actions:
                    output.emit(output_actions)
                # In gamepad mode, forward non-toggle events to the
                # virtual gamepad (engine.process returns [] for them).
                if not engine.enabled and not toggled and actions == []:
                    _route_to_gamepad(gamepad_ref[0], event)
            now = clock()
            if now >= next_tick:
                if engine.enabled:
                    actions = engine.tick(now)
                    if actions:
                        output.emit(actions)
                next_tick = now + tick_interval
    finally:
        try:
            set_grabbed(grabbed_devices, False)
            if gamepad_ref[0] is not None:
                gamepad_ref[0].close()
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
    grabbed_devices: dict | None = None,
) -> None:
    """Keep one output session while Joy-Con sides come and go independently.

    Routes Joy-Con events to the keyboard/mouse engine when enabled, or to
    a combined VirtualGamepad when disabled (gamepad mode).
    """

    gamepad_ref: list[VirtualGamepad | None] = [None]

    # Create gamepad immediately if starting in gamepad mode.
    _switch_gamepad(gamepad_ref, engine.enabled)

    active_sides: set[JoyConSide] = set()
    try:
        next_tick = clock()
        next_maintenance = next_tick
        for event in read_managed_events(
            addresses,
            tick_interval=tick_interval,
            config_fd=config_fd,
            config_path=config_path,
            grabbed=grabbed_devices,
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
                gamepad_ref=gamepad_ref,
            ):
                raise KeyboardInterrupt("tray requested quit")
            if isinstance(event, ConfigFileChanged):
                _reload_config(event.path, engine, output, config_watcher, now)
                _switch_gamepad(gamepad_ref, engine.enabled)
                continue
            if isinstance(event, DeviceStatusEvent):
                if event.state == "connected":
                    active_sides.add(event.side)
                else:
                    active_sides.discard(event.side)
                    if engine.enabled:
                        actions = engine.release_side(event.side)
                        if actions:
                            output.emit(actions)
                    else:
                        _release_gamepad_side(gamepad_ref[0], event.side)
                if on_device_status is not None:
                    on_device_status(event)
            elif event is not None:
                # Always let the engine inspect the event first — toggle
                # buttons must work in both modes (the engine always
                # processes ToggleMapping regardless of enabled state).
                actions = engine.process(event)
                toggled = False
                output_actions = []
                for action in actions:
                    if isinstance(action, ToggleAction):
                        prev_enabled = engine.enabled
                        release_actions = engine.set_enabled(
                            not engine.enabled
                        )
                        if engine.enabled != prev_enabled:
                            if release_actions:
                                output.emit(release_actions)
                            _switch_gamepad(gamepad_ref, engine.enabled)
                        if on_mode_change is not None:
                            on_mode_change(engine.enabled)
                        toggled = True
                    elif engine.enabled:
                        output_actions.append(action)
                if output_actions:
                    output.emit(output_actions)
                # In gamepad mode, forward non-toggle events to the
                # virtual gamepad (engine.process returns [] for them).
                if not engine.enabled and not toggled and actions == []:
                    _route_to_gamepad(gamepad_ref[0], event)

            if now >= next_tick:
                if engine.enabled:
                    actions = engine.tick(now)
                    if actions:
                        output.emit(actions)
                next_tick = now + tick_interval
            if now >= next_maintenance:
                maintain_connections(active_sides)
                next_maintenance = now + maintenance_interval
    finally:
        try:
            set_grabbed(grabbed_devices, False)
            if gamepad_ref[0] is not None:
                gamepad_ref[0].close()
            output.release_all()
        finally:
            output.close()
            engine.reset()
