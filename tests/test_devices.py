from __future__ import annotations

import pytest
from evdev import InputEvent, ecodes

from joyio import devices


class FakeInputDevice:
    def __init__(self, events, *, failure: OSError | None = None) -> None:
        self.events = events
        self.failure = failure
        self.closed = False

    def read_loop(self):
        yield from self.events
        if self.failure is not None:
            raise self.failure

    def absinfo(self, code):
        raise AssertionError("absinfo não era esperado neste teste")

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


def test_reader_closes_device_and_wraps_disconnect(monkeypatch) -> None:
    fake = FakeInputDevice([], failure=OSError("device vanished"))
    monkeypatch.setattr(devices, "InputDevice", lambda path: fake)

    with pytest.raises(devices.InputDeviceError, match="desconectado"):
        list(devices.read_normalized_events("/dev/input/fake", "left"))

    assert fake.closed is True
