from __future__ import annotations

from queue import Empty

import pytest

from joyio.config.models import (
    JoyIOConfig,
    KeyMapping,
    ReconnectConfig,
    RuntimeConfig,
    ToggleMapping,
)
from joyio.devices import InputDeviceError, JoyConInput
from joyio.events import NormalizedEvent
from joyio.events import DeviceStatusEvent
from joyio.mapping.actions import KeyAction
from joyio.mapping.engine import MappingEngine
from joyio.runtime import controller
from joyio.runtime.supervisor import run_with_reconnect


class RecordingOutput:
    def __init__(self) -> None:
        self.actions = []
        self.released = False
        self.closed = False

    def emit(self, actions) -> None:
        self.actions.extend(actions)

    def release_all(self) -> None:
        self.released = True

    def close(self) -> None:
        self.closed = True


class ControlQueue:
    def __init__(self, commands) -> None:
        self._commands = list(commands)

    def get_nowait(self):
        if not self._commands:
            raise Empty
        return self._commands.pop(0)


def test_runtime_releases_output_after_input_failure(monkeypatch) -> None:
    pressed = NormalizedEvent("button", "a", "test", "right", 0, 1.0, "pressed", 1.0)

    def failing_reader(inputs, **kwargs):
        yield pressed
        raise OSError("disconnect")

    monkeypatch.setattr(controller, "read_runtime_events", failing_reader)
    output = RecordingOutput()
    engine = MappingEngine(
        JoyIOConfig(version=1, buttons={"right.a": KeyMapping("KEY_A", "hold")})
    )
    inputs = (
        JoyConInput("left", "Joy-Con (L)", "11:22:33:44:55:01", "left"),
        JoyConInput("right", "Joy-Con (R)", "11:22:33:44:55:02", "right"),
    )

    with pytest.raises(OSError, match="disconnect"):
        controller.run_mapping(inputs, engine, output)

    assert output.released is True
    assert output.closed is True


def test_runtime_limits_ticks_during_event_bursts(monkeypatch) -> None:
    axis = NormalizedEvent("axis", "left_stick_x", "test", "left", 0, 0.5, None, 1.0)

    def burst_reader(inputs, **kwargs):
        yield from [axis] * 100

    class CountingEngine:
        def __init__(self) -> None:
            self.processed = 0
            self.ticks = 0
            self.reset_called = False
            self.enabled = True

        def process(self, event):
            self.processed += 1
            return []

        def tick(self, now):
            self.ticks += 1
            return []

        def reset(self):
            self.reset_called = True

    times = iter([0.0, *(index / 1000.0 for index in range(1, 101))])
    engine = CountingEngine()
    output = RecordingOutput()
    monkeypatch.setattr(controller, "read_runtime_events", burst_reader)

    controller.run_mapping((), engine, output, clock=lambda: next(times), tick_interval=0.01)

    assert engine.processed == 100
    assert 9 <= engine.ticks <= 11
    assert engine.reset_called is True


def test_supervisor_reconnects_after_session_disconnect() -> None:
    inputs = (
        JoyConInput("left", "Joy-Con (L)", "11:22:33:44:55:01", "left"),
        JoyConInput("right", "Joy-Con (R)", "11:22:33:44:55:02", "right"),
    )
    sessions = []
    sleeps = []
    retries = []

    def run_session(selected) -> None:
        sessions.append(selected)
        if len(sessions) == 1:
            raise InputDeviceError("desconectado")

    run_with_reconnect(
        lambda: inputs,
        run_session,
        ReconnectConfig(initial_delay=1.0, max_delay=10.0, multiplier=2.0),
        recoverable_errors=(InputDeviceError,),
        on_retry=lambda attempt, delay, error: retries.append(
            (attempt, delay, str(error))
        ),
        sleep=sleeps.append,
    )

    assert len(sessions) == 2
    assert sleeps == [1.0]
    assert retries == [(1, 1.0, "desconectado")]


def test_supervisor_applies_capped_backoff_to_acquisition_failures() -> None:
    attempts = 0
    sleeps = []

    def acquire():
        nonlocal attempts
        attempts += 1
        if attempts <= 3:
            raise InputDeviceError("ainda indisponível")
        return ()

    run_with_reconnect(
        acquire,
        lambda inputs: None,
        ReconnectConfig(initial_delay=1.0, max_delay=3.0, multiplier=2.0),
        recoverable_errors=(InputDeviceError,),
        sleep=sleeps.append,
    )

    assert attempts == 4
    assert sleeps == [1.0, 2.0, 3.0]


def test_supervisor_respects_disabled_reconnection() -> None:
    def fail():
        raise InputDeviceError("offline")

    with pytest.raises(InputDeviceError, match="offline"):
        run_with_reconnect(
            fail,
            lambda inputs: None,
            ReconnectConfig(enabled=False),
            recoverable_errors=(InputDeviceError,),
            sleep=lambda delay: pytest.fail("não deveria aguardar"),
        )


def test_supervisor_stops_after_max_attempts() -> None:
    sleeps = []

    def fail():
        raise InputDeviceError("offline")

    with pytest.raises(InputDeviceError, match="offline"):
        run_with_reconnect(
            fail,
            lambda inputs: None,
            ReconnectConfig(max_attempts=2),
            recoverable_errors=(InputDeviceError,),
            sleep=sleeps.append,
        )

    assert sleeps == [1.0, 2.0]


def test_managed_runtime_preserves_peer_and_releases_disconnected_side(
    monkeypatch,
) -> None:
    events = iter(
        [
            DeviceStatusEvent("left", "connected", "/left"),
            DeviceStatusEvent("right", "connected", "/right"),
            NormalizedEvent("button", "l", "test", "left", 0, 1.0, "pressed", 1.0),
            NormalizedEvent("button", "r", "test", "right", 0, 1.0, "pressed", 1.0),
            DeviceStatusEvent("left", "disconnected", "/left"),
            NormalizedEvent("button", "r", "test", "right", 0, 0.0, "released", 2.0),
        ]
    )
    monkeypatch.setattr(
        controller, "read_managed_events", lambda addresses, **kwargs: events
    )
    output = RecordingOutput()
    engine = MappingEngine(
        JoyIOConfig(
            version=1,
            buttons={
                "left.l": KeyMapping("KEY_A", "hold"),
                "right.r": KeyMapping("KEY_B", "hold"),
            },
        )
    )
    maintained = []
    statuses = []
    times = iter(index * 0.2 for index in range(20))

    controller.run_managed_mapping(
        {"left": "AA:01", "right": "AA:02"},
        engine,
        output,
        lambda sides: maintained.append(set(sides)),
        on_device_status=statuses.append,
        clock=lambda: next(times),
        maintenance_interval=0.1,
    )

    assert output.actions == [
        KeyAction("KEY_A", True),
        KeyAction("KEY_B", True),
        KeyAction("KEY_A", False),
        KeyAction("KEY_B", False),
    ]


def test_runtime_toggle_releases_outputs_and_recovers_without_restart(monkeypatch) -> None:
    events = iter(
        [
            NormalizedEvent("button", "a", "test", "right", 0, 1.0, "pressed", 1.0),
            NormalizedEvent(
                "button", "capture", "test", "left", 0, 1.0, "pressed", 1.1
            ),
            NormalizedEvent("button", "a", "test", "right", 0, 0.0, "released", 1.2),
            NormalizedEvent(
                "button", "capture", "test", "left", 0, 1.0, "pressed", 1.3
            ),
            NormalizedEvent("button", "a", "test", "right", 0, 1.0, "pressed", 1.4),
        ]
    )
    monkeypatch.setattr(controller, "read_runtime_events", lambda inputs, **kwargs: events)
    output = RecordingOutput()
    engine = MappingEngine(
        JoyIOConfig(
            version=1,
            buttons={
                "right.a": KeyMapping("KEY_A", "hold"),
                "left.capture": ToggleMapping(),
            },
        )
    )
    mode_changes = []

    controller.run_mapping(
        (),
        engine,
        output,
        on_mode_change=mode_changes.append,
        clock=lambda: 0.0,
    )

    assert output.actions == [
        KeyAction("KEY_A", True),
        KeyAction("KEY_A", False),
        KeyAction("KEY_A", True),
    ]
    assert mode_changes == [False, True]
    assert output.released is True
    assert output.closed is True


def test_runtime_consumes_tray_toggle_commands(monkeypatch) -> None:
    events = iter([None])
    monkeypatch.setattr(controller, "read_runtime_events", lambda inputs, **kwargs: events)
    output = RecordingOutput()
    engine = MappingEngine(JoyIOConfig(version=1))
    mode_changes = []

    controller.run_mapping(
        (),
        engine,
        output,
        on_mode_change=mode_changes.append,
        control_queue=ControlQueue(["toggle"]),
    )

    assert mode_changes == [False]
    assert output.closed is True


def test_runtime_consumes_tray_reload_commands(monkeypatch) -> None:
    events = iter([None])
    monkeypatch.setattr(controller, "read_runtime_events", lambda inputs, **kwargs: events)
    loaded = []
    monkeypatch.setattr(
        controller,
        "load_config",
        lambda path: loaded.append(path) or JoyIOConfig(
            version=1, runtime=RuntimeConfig(enabled=False)
        ),
    )
    output = RecordingOutput()
    engine = MappingEngine(JoyIOConfig(version=1))
    mode_changes = []

    controller.run_mapping(
        (),
        engine,
        output,
        on_mode_change=mode_changes.append,
        config_path="/tmp/joyio.yaml",
        config_watcher=type(
            "Watcher",
            (),
            {"consume": lambda self: False, "debounce": lambda self, now: False},
        )(),
        control_queue=ControlQueue(["reload"]),
    )

    assert mode_changes == [False]
    assert loaded == ["/tmp/joyio.yaml"]
    assert output.closed is True
