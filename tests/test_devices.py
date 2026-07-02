from __future__ import annotations

import pytest
from evdev import InputEvent, ecodes

from joyio import devices


class FakeInputDevice:
    def __init__(self, events, *, failure: OSError | None = None, fd: int = 1) -> None:
        self.events = events
        self.failure = failure
        self.closed = False
        self.fd = fd

    def read_loop(self):
        yield from self.events
        if self.failure is not None:
            raise self.failure

    def absinfo(self, code):
        raise AssertionError("absinfo não era esperado neste teste")

    def read(self):
        events, self.events = self.events, []
        return events

    def close(self) -> None:
        self.closed = True


def test_reader_closes_device_after_normal_completion(monkeypatch) -> None:
    fake = FakeInputDevice(
        [InputEvent(1, 0, ecodes.EV_KEY, ecodes.BTN_SOUTH, 1)]
    )
    monkeypatch.setattr(devices, "InputDevice", lambda path: fake)

    events = list(devices.read_normalized_events("/dev/input/fake", "right"))

    assert events[0].control == "b"
    assert fake.closed is True


def test_runtime_reader_multiplexes_left_and_right(monkeypatch) -> None:
    left = FakeInputDevice(
        [InputEvent(1, 0, ecodes.EV_KEY, ecodes.BTN_DPAD_UP, 1)], fd=10
    )
    right = FakeInputDevice(
        [InputEvent(1, 0, ecodes.EV_KEY, ecodes.BTN_EAST, 1)], fd=11
    )
    devices_by_path = {"/left": left, "/right": right}
    monkeypatch.setattr(devices, "InputDevice", devices_by_path.__getitem__)
    monkeypatch.setattr(
        devices.select,
        "select",
        lambda readers, _writes, _errors, _timeout: (readers, [], []),
    )
    sources = (
        devices.JoyConInput("/left", "Joy-Con (L)", "00:00:00:00:00:01", "left"),
        devices.JoyConInput("/right", "Joy-Con (R)", "00:00:00:00:00:02", "right"),
    )

    reader = devices.read_runtime_events(sources)
    events = [next(reader), next(reader)]
    reader.close()

    assert [(event.side, event.control) for event in events if event] == [
        ("left", "dpad_up"),
        ("right", "a"),
    ]
    assert left.closed is True
    assert right.closed is True


def test_reader_closes_device_and_wraps_disconnect(monkeypatch) -> None:
    fake = FakeInputDevice([], failure=OSError("device vanished"))
    monkeypatch.setattr(devices, "InputDevice", lambda path: fake)

    with pytest.raises(devices.InputDeviceError, match="desconectado"):
        list(devices.read_normalized_events("/dev/input/fake", "left"))

    assert fake.closed is True
