"""Small BlueZ boundary used by the phase-zero proof of concept.

The module intentionally shells out to bluetoothctl. A D-Bus adapter can replace
this implementation later without leaking BlueZ details into the input reader.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
import subprocess
from typing import Callable, Sequence


JOYCON_NAMES = {
    "joy-con (l)": "left",
    "joy-con (r)": "right",
}

_DEVICE_LINE = re.compile(
    r"^Device\s+(?P<address>(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2})\s+(?P<name>.+)$"
)


class BluetoothError(RuntimeError):
    """BlueZ or bluetoothctl could not complete an operation."""


@dataclass(frozen=True, slots=True)
class BluetoothDevice:
    address: str
    name: str
    side: str | None

    @property
    def is_joycon(self) -> bool:
        return self.side is not None


Runner = Callable[..., subprocess.CompletedProcess[str]]


def joycon_side(name: str) -> str | None:
    """Return the side for an original Joy-Con Bluetooth product name."""

    return JOYCON_NAMES.get(name.strip().casefold())


def parse_device_lines(output: str) -> list[BluetoothDevice]:
    """Parse the stable, line-oriented output of bluetoothctl devices."""

    devices: list[BluetoothDevice] = []
    for line in output.splitlines():
        match = _DEVICE_LINE.match(line.strip())
        if match is None:
            continue
        name = match.group("name").strip()
        devices.append(
            BluetoothDevice(
                address=match.group("address").upper(),
                name=name,
                side=joycon_side(name),
            )
        )
    return devices


def _run_bluetoothctl(
    arguments: Sequence[str], *, runner: Runner = subprocess.run
) -> str:
    command = ["bluetoothctl", *arguments]
    try:
        result = runner(
            command,
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
    except FileNotFoundError as error:
        raise BluetoothError(
            "bluetoothctl não foi encontrado; instale o pacote bluez."
        ) from error
    except subprocess.TimeoutExpired as error:
        raise BluetoothError(
            f"bluetoothctl excedeu o timeout: {' '.join(command)}"
        ) from error

    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip() or "sem detalhes"
        raise BluetoothError(f"bluetoothctl falhou: {detail}")
    return result.stdout


def list_paired_devices(*, runner: Runner = subprocess.run) -> list[BluetoothDevice]:
    return parse_device_lines(
        _run_bluetoothctl(["devices", "Paired"], runner=runner)
    )


def get_device_info(
    address: str, *, runner: Runner = subprocess.run
) -> dict[str, str]:
    output = _run_bluetoothctl(["info", address], runner=runner)
    info: dict[str, str] = {}
    for line in output.splitlines()[1:]:
        key, separator, value = line.strip().partition(":")
        if separator:
            info[key.strip()] = value.strip()
    return info


def connect_device(address: str, *, runner: Runner = subprocess.run) -> bool:
    """Ensure a paired device is connected; return True if a connect was issued."""

    info = get_device_info(address, runner=runner)
    if info.get("Connected", "no").casefold() == "yes":
        return False
    output = _run_bluetoothctl(["connect", address], runner=runner)
    if "successful" not in output.casefold():
        raise BluetoothError(
            "BlueZ não confirmou a conexão. Coloque o Joy-Con em modo de "
            "sincronização e confirme o pareamento com bluetoothctl."
        )
    return True
