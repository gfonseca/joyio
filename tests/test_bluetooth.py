from __future__ import annotations

import subprocess

import pytest

from joyio.bluetooth import (
    BluetoothConnector,
    BluetoothError,
    connect_device,
    joycon_side,
    list_paired_devices,
    parse_device_lines,
)
from joyio.config.models import ReconnectConfig


def completed(stdout: str = "", stderr: str = "", returncode: int = 0):
    return subprocess.CompletedProcess(
        args=["bluetoothctl"], returncode=returncode, stdout=stdout, stderr=stderr
    )


def test_parse_device_lines_filters_noise_and_identifies_sides() -> None:
    devices = parse_device_lines(
        """Controller AA:BB:CC:DD:EE:FF host [default]
Device 11:22:33:44:55:66 Joy-Con (L)
Device AA:BB:CC:DD:EE:01 Joy-Con (R)
Device AA:BB:CC:DD:EE:02 Headphones
"""
    )

    assert [(item.address, item.side) for item in devices] == [
        ("11:22:33:44:55:66", "left"),
        ("AA:BB:CC:DD:EE:01", "right"),
        ("AA:BB:CC:DD:EE:02", None),
    ]


@pytest.mark.parametrize(
    ("name", "side"),
    [("Joy-Con (L)", "left"), ("joy-con (r)", "right"), ("Pro Controller", None)],
)
def test_joycon_side(name: str, side: str | None) -> None:
    assert joycon_side(name) == side


def test_list_paired_devices_invokes_bluetoothctl() -> None:
    calls: list[list[str]] = []

    def runner(command, **kwargs):
        calls.append(command)
        return completed("Device 11:22:33:44:55:66 Joy-Con (L)\n")

    devices = list_paired_devices(runner=runner)

    assert calls == [["bluetoothctl", "devices", "Paired"]]
    assert devices[0].side == "left"


def test_connect_skips_device_that_is_already_connected() -> None:
    calls: list[list[str]] = []

    def runner(command, **kwargs):
        calls.append(command)
        return completed("Device 11:22:33:44:55:66\n\tConnected: yes\n")

    assert connect_device("11:22:33:44:55:66", runner=runner) is False
    assert calls == [["bluetoothctl", "info", "11:22:33:44:55:66"]]


def test_connect_issues_command_when_disconnected() -> None:
    responses = iter(
        [
            completed("Device 11:22:33:44:55:66\n\tConnected: no\n"),
            completed("Connection successful\n"),
        ]
    )
    calls: list[list[str]] = []

    def runner(command, **kwargs):
        calls.append(command)
        return next(responses)

    assert connect_device("11:22:33:44:55:66", runner=runner) is True
    assert calls[-1] == ["bluetoothctl", "connect", "11:22:33:44:55:66"]


def test_bluetooth_failure_is_actionable() -> None:
    def runner(command, **kwargs):
        return completed(stderr="No default controller available", returncode=1)

    with pytest.raises(BluetoothError, match="No default controller"):
        list_paired_devices(runner=runner)


class FakeProcess:
    def __init__(self, stdout="Connection successful\n", stderr="", returncode=None):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode
        self.terminated = False

    def poll(self):
        return self.returncode

    def communicate(self, timeout=None):
        return self.stdout, self.stderr

    def terminate(self):
        self.terminated = True
        self.returncode = -15

    def kill(self):
        self.returncode = -9


def test_connector_attempt_is_non_blocking_and_becomes_active() -> None:
    now = [0.0]
    processes = []
    statuses = []

    def popen(command, **kwargs):
        process = FakeProcess()
        processes.append((command, process))
        return process

    connector = BluetoothConnector(
        {"left": "11:22:33:44:55:66"},
        ReconnectConfig(),
        clock=lambda: now[0],
        popen=popen,
        on_status=lambda *status: statuses.append(status),
    )

    connector.maintain(set())
    assert processes[0][0] == [
        "bluetoothctl",
        "connect",
        "11:22:33:44:55:66",
    ]
    assert statuses[-1][1] == "connecting"

    processes[0][1].returncode = 0
    connector.maintain(set())
    assert statuses[-1][1] == "bluetooth_ready"

    connector.maintain({"left"})
    assert statuses[-1][1] == "active"


def test_connector_treats_bluez_inprogress_as_pending() -> None:
    now = [0.0]
    process = FakeProcess(stderr="org.bluez.Error.InProgress", returncode=None)
    connector = BluetoothConnector(
        {"right": "11:22:33:44:55:77"},
        ReconnectConfig(initial_delay=1.0),
        clock=lambda: now[0],
        popen=lambda command, **kwargs: process,
    )

    connector.maintain(set())
    process.returncode = 1
    connector.maintain(set())
    now[0] = 0.5
    connector.maintain(set())

    # No new process is started before the short pending interval expires.
    assert connector._attempt_counts["right"] == 1


def test_connector_respects_bluez_connected_state_before_reconnecting(
    monkeypatch,
) -> None:
    now = [0.0]
    processes = []
    statuses = []

    def popen(command, **kwargs):
        process = FakeProcess()
        processes.append((command, process))
        return process

    monkeypatch.setattr(
        "joyio.bluetooth.get_device_info",
        lambda address, **kwargs: {"Connected": "yes"},
    )

    connector = BluetoothConnector(
        {"left": "11:22:33:44:55:66"},
        ReconnectConfig(initial_delay=1.0),
        clock=lambda: now[0],
        popen=popen,
        on_status=lambda *status: statuses.append(status),
    )

    connector.maintain(set())
    now[0] = 1.5
    connector.maintain(set())
    connector.maintain({"left"})

    assert processes == []
    assert statuses[0] == ("left", "bluetooth_ready", "Connected: yes")
    assert statuses[-1] == ("left", "active", "evdev disponível")
