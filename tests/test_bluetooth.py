from __future__ import annotations

import subprocess

import pytest

from joyio.bluetooth import (
    BluetoothError,
    connect_device,
    joycon_side,
    list_paired_devices,
    parse_device_lines,
)


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
