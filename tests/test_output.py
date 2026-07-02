from __future__ import annotations

from io import StringIO
import json

from evdev import ecodes

from joyio.config.models import JoyIOConfig, KeyMapping
from joyio.mapping.actions import (
    KeyAction,
    MouseButtonAction,
    MouseMoveAction,
    MouseScrollAction,
)
from joyio.output import DryRunOutput, UInputOutput
from joyio.output import backends


def test_dry_run_is_jsonl_and_releases_held_inputs() -> None:
    stream = StringIO()
    output = DryRunOutput(stream)
    output.emit([KeyAction("KEY_A", True), MouseButtonAction("left", True)])

    output.release_all()

    lines = [json.loads(line) for line in stream.getvalue().splitlines()]
    assert lines == [
        {"key": "KEY_A", "pressed": True, "type": "key"},
        {"button": "left", "pressed": True, "type": "mouse_button"},
        {"key": "KEY_A", "pressed": False, "type": "key"},
        {"button": "left", "pressed": False, "type": "mouse_button"},
    ]


class FakeUInput:
    def __init__(self, capabilities, name) -> None:
        self.capabilities = capabilities
        self.name = name
        self.writes = []
        self.syncs = 0
        self.closed = False

    def write(self, event_type, code, value) -> None:
        self.writes.append((event_type, code, value))

    def syn(self) -> None:
        self.syncs += 1

    def close(self) -> None:
        self.closed = True


def test_uinput_emits_keys_mouse_and_releases_holds(monkeypatch) -> None:
    created = []

    def factory(capabilities, name, **kwargs):
        device = FakeUInput(capabilities, name)
        created.append(device)
        return device

    monkeypatch.setattr(backends, "UInput", factory)
    output = UInputOutput(
        JoyIOConfig(version=1, buttons={"a": KeyMapping("KEY_A", "hold")})
    )
    output.emit(
        [
            KeyAction("KEY_A", True),
            MouseButtonAction("left", True),
            MouseMoveAction(3, -2),
            MouseScrollAction(1, -1),
        ]
    )
    output.release_all()
    output.close()

    device = created[0]
    assert (ecodes.EV_KEY, ecodes.KEY_A, 1) in device.writes
    assert (ecodes.EV_KEY, ecodes.BTN_LEFT, 1) in device.writes
    assert (ecodes.EV_REL, ecodes.REL_X, 3) in device.writes
    assert (ecodes.EV_REL, ecodes.REL_Y, -2) in device.writes
    assert (ecodes.EV_REL, ecodes.REL_HWHEEL, 1) in device.writes
    assert (ecodes.EV_REL, ecodes.REL_WHEEL, -1) in device.writes
    assert (ecodes.EV_KEY, ecodes.KEY_A, 0) in device.writes
    assert (ecodes.EV_KEY, ecodes.BTN_LEFT, 0) in device.writes
    assert device.closed is True


def test_uinput_reference_counts_shared_outputs(monkeypatch) -> None:
    created = []

    def factory(capabilities, name, **kwargs):
        device = FakeUInput(capabilities, name)
        created.append(device)
        return device

    monkeypatch.setattr(backends, "UInput", factory)
    output = UInputOutput(
        JoyIOConfig(version=1, buttons={"right.a": KeyMapping("KEY_A", "hold")})
    )

    output.emit([KeyAction("KEY_A", True), KeyAction("KEY_A", True)])
    output.emit([KeyAction("KEY_A", False)])
    assert created[0].writes == [(ecodes.EV_KEY, ecodes.KEY_A, 1)]

    output.emit([KeyAction("KEY_A", False)])
    assert created[0].writes[-1] == (ecodes.EV_KEY, ecodes.KEY_A, 0)


def test_uinput_groups_pointer_and_scroll_in_one_sync(monkeypatch) -> None:
    created = []

    def factory(capabilities, name, **kwargs):
        device = FakeUInput(capabilities, name)
        created.append(device)
        return device

    monkeypatch.setattr(backends, "UInput", factory)
    output = UInputOutput(JoyIOConfig(version=1))

    output.emit([MouseMoveAction(3, -2), MouseScrollAction(1, -1)])

    assert created[0].syncs == 1


def test_dry_run_reference_counts_shared_outputs() -> None:
    stream = StringIO()
    output = DryRunOutput(stream)

    output.emit([KeyAction("KEY_A", True), KeyAction("KEY_A", True)])
    output.emit([KeyAction("KEY_A", False)])
    output.emit([KeyAction("KEY_A", False)])

    lines = [json.loads(line) for line in stream.getvalue().splitlines()]
    assert lines == [
        {"key": "KEY_A", "pressed": True, "type": "key"},
        {"key": "KEY_A", "pressed": False, "type": "key"},
    ]
