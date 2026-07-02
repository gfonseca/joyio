from __future__ import annotations

import pytest
from evdev import AbsInfo, InputEvent, ecodes

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


def test_reader_caches_absinfo_per_axis(monkeypatch) -> None:
    fake = FakeInputDevice(
        [
            InputEvent(1, 0, ecodes.EV_ABS, ecodes.ABS_RX, 10),
            InputEvent(1, 1, ecodes.EV_ABS, ecodes.ABS_RX, 20),
        ]
    )
    calls = []

    def absinfo(code):
        calls.append(code)
        return AbsInfo(0, -100, 100, 0, 0, 0)

    fake.absinfo = absinfo
    monkeypatch.setattr(devices, "InputDevice", lambda path: fake)

    events = list(devices.read_normalized_events("/dev/input/fake", "right"))

    assert len(events) == 2
    assert calls == [ecodes.ABS_RX]


def test_managed_reader_disconnects_only_failed_side(monkeypatch) -> None:
    class DynamicDevice(FakeInputDevice):
        def read(self):
            if self.failure is not None:
                failure, self.failure = self.failure, None
                raise failure
            return super().read()

    left = DynamicDevice([], failure=OSError("left vanished"), fd=10)
    right = DynamicDevice(
        [InputEvent(1, 0, ecodes.EV_KEY, ecodes.BTN_EAST, 1)], fd=11
    )
    sources = [
        devices.JoyConInput("/left", "Joy-Con (L)", "AA:00:00:00:00:01", "left"),
        devices.JoyConInput("/right", "Joy-Con (R)", "AA:00:00:00:00:02", "right"),
    ]
    monkeypatch.setattr(
        devices, "InputDevice", {"/left": left, "/right": right}.__getitem__
    )
    monkeypatch.setattr(
        devices.select,
        "select",
        lambda readers, _writes, _errors, _timeout: (readers, [], []),
    )
    reader = devices.read_managed_events(
        {"left": sources[0].address, "right": sources[1].address},
        discover=lambda: sources,
    )

    connected = [next(reader), next(reader)]
    disconnected = next(reader)
    right_event = next(reader)
    reader.close()

    assert [(event.side, event.state) for event in connected] == [
        ("left", "connected"),
        ("right", "connected"),
    ]
    assert (disconnected.side, disconnected.state) == ("left", "disconnected")
    assert (right_event.side, right_event.control) == ("right", "a")
    assert left.closed is True
    assert right.closed is True


def test_managed_reader_handles_disconnect_during_iteration(monkeypatch) -> None:
    class FailingEvents:
        def __iter__(self):
            raise OSError("left vanished")

    left = FakeInputDevice(FailingEvents(), fd=10)
    right = FakeInputDevice(
        [InputEvent(1, 0, ecodes.EV_KEY, ecodes.BTN_EAST, 1)], fd=11
    )
    sources = [
        devices.JoyConInput("/left", "Joy-Con (L)", "AA:00:00:00:00:01", "left"),
        devices.JoyConInput("/right", "Joy-Con (R)", "AA:00:00:00:00:02", "right"),
    ]
    monkeypatch.setattr(
        devices, "InputDevice", {"/left": left, "/right": right}.__getitem__
    )
    monkeypatch.setattr(
        devices.select,
        "select",
        lambda readers, _writes, _errors, _timeout: (readers, [], []),
    )
    reader = devices.read_managed_events(
        {"left": sources[0].address, "right": sources[1].address},
        discover=lambda: sources,
    )

    connected = [next(reader), next(reader)]
    disconnected = next(reader)
    right_event = next(reader)
    reader.close()

    assert [(event.side, event.state) for event in connected] == [
        ("left", "connected"),
        ("right", "connected"),
    ]
    assert (disconnected.side, disconnected.state) == ("left", "disconnected")
    assert (right_event.side, right_event.control) == ("right", "a")
    assert left.closed is True
    assert right.closed is True


def test_managed_reader_reopens_side_at_new_event_path(monkeypatch) -> None:
    class DisconnectingDevice(FakeInputDevice):
        def read(self):
            raise OSError("vanished")

    old = DisconnectingDevice([], fd=10)
    new = FakeInputDevice(
        [InputEvent(1, 0, ecodes.EV_KEY, ecodes.BTN_DPAD_UP, 1)], fd=12
    )
    old_source = devices.JoyConInput(
        "/event10", "Joy-Con (L)", "AA:00:00:00:00:01", "left"
    )
    new_source = devices.JoyConInput(
        "/event12", "Joy-Con (L)", "AA:00:00:00:00:01", "left"
    )
    discoveries = iter([[old_source], [new_source]])
    monkeypatch.setattr(
        devices, "InputDevice", {"/event10": old, "/event12": new}.__getitem__
    )
    monkeypatch.setattr(
        devices.select,
        "select",
        lambda readers, _writes, _errors, _timeout: (readers, [], []),
    )
    reader = devices.read_managed_events(
        {"left": old_source.address},
        discover=lambda: next(discoveries),
        discovery_interval=0.0,
        clock=lambda: 0.0,
    )

    events = [next(reader) for _ in range(4)]
    reader.close()

    assert [(events[0].state, events[0].path), (events[1].state, events[1].path)] == [
        ("connected", "/event10"),
        ("disconnected", "/event10"),
    ]
    assert (events[2].state, events[2].path) == ("connected", "/event12")
    assert (events[3].side, events[3].control) == ("left", "dpad_up")
