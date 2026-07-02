"""BlueZ boundary for paired-device discovery and connection lifecycle.

The module intentionally shells out to bluetoothctl. A D-Bus adapter can replace
this implementation later without leaking BlueZ details into the input reader.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
import subprocess
import time
from typing import Callable, Mapping, Sequence

from joyio.config.models import ReconnectConfig
from joyio.controls import JoyConSide


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
StatusCallback = Callable[[JoyConSide, str, str], None]
PopenFactory = Callable[..., subprocess.Popen[str]]


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
    arguments: Sequence[str], *, runner: Runner = subprocess.run, timeout: float = 8
) -> str:
    command = ["bluetoothctl", *arguments]
    try:
        result = runner(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
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
    address: str, *, runner: Runner = subprocess.run, timeout: float = 8
) -> dict[str, str]:
    output = _run_bluetoothctl(["info", address], runner=runner, timeout=timeout)
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


@dataclass(slots=True)
class _ConnectAttempt:
    process: subprocess.Popen[str]
    started_at: float


class BluetoothConnector:
    """Maintain independent, non-blocking bluetoothctl attempts per side."""

    def __init__(
        self,
        addresses: Mapping[JoyConSide, str],
        policy: ReconnectConfig,
        *,
        timeout: float = 8.0,
        info_timeout: float = 1.0,
        clock: Callable[[], float] = time.monotonic,
        popen: PopenFactory = subprocess.Popen,
        on_status: StatusCallback | None = None,
        runner: Runner = subprocess.run,
    ) -> None:
        self._addresses = {
            side: address.upper() for side, address in addresses.items()
        }
        self._policy = policy
        self._timeout = timeout
        self._info_timeout = info_timeout
        self._clock = clock
        self._popen = popen
        self._on_status = on_status
        self._runner = runner
        self._attempts: dict[JoyConSide, _ConnectAttempt] = {}
        self._attempt_counts = {side: 0 for side in self._addresses}
        self._next_attempt = {side: 0.0 for side in self._addresses}
        self._last_status: dict[JoyConSide, tuple[str, str]] = {}

    def maintain(self, active_sides: set[JoyConSide]) -> None:
        """Poll current attempts and start due attempts without blocking input."""

        now = self._clock()
        for side, address in self._addresses.items():
            if side in active_sides:
                attempt = self._attempts.pop(side, None)
                if attempt is not None:
                    self._stop(attempt.process)
                self._attempt_counts[side] = 0
                self._next_attempt[side] = now
                self._status(side, "active", "evdev disponível")
                continue

            attempt = self._attempts.get(side)
            if attempt is not None:
                return_code = attempt.process.poll()
                if return_code is None and now - attempt.started_at < self._timeout:
                    continue
                self._attempts.pop(side)
                if return_code is None:
                    self._stop(attempt.process)
                    self._schedule(side, now, "timeout do bluetoothctl")
                    continue
                stdout, stderr = attempt.process.communicate()
                detail = "\n".join(
                    part.strip() for part in (stdout, stderr) if part.strip()
                )
                detail = detail or "sem detalhes"
                folded = detail.casefold()
                if return_code == 0 and (
                    "successful" in folded
                    or "already connected" in folded
                    or "connection successful" in folded
                ):
                    self._status(side, "bluetooth_ready", detail)
                    self._next_attempt[side] = now + self._policy.initial_delay
                elif "inprogress" in folded or "in progress" in folded:
                    # BlueZ is already connecting. Treat this as pending, not as
                    # a hard failure that would trigger a long global backoff.
                    self._next_attempt[side] = now + self._policy.initial_delay
                    self._status(side, "connecting", detail)
                else:
                    self._schedule(side, now, detail)
                continue

            if not self._policy.enabled or now < self._next_attempt[side]:
                continue
            try:
                info = get_device_info(
                    address, runner=self._runner, timeout=self._info_timeout
                )
            except BluetoothError:
                info = {}
            if info.get("Connected", "no").casefold() == "yes":
                self._attempt_counts[side] = 0
                self._next_attempt[side] = now + self._policy.initial_delay
                self._status(
                    side,
                    "bluetooth_ready",
                    f"Connected: {info.get('Connected', 'yes')}",
                )
                continue
            maximum = self._policy.max_attempts
            if maximum is not None and self._attempt_counts[side] >= maximum:
                self._status(side, "offline", "limite de tentativas atingido")
                continue
            try:
                process = self._popen(
                    ["bluetoothctl", "connect", address],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
            except FileNotFoundError as error:
                raise BluetoothError(
                    "bluetoothctl não foi encontrado; instale o pacote bluez."
                ) from error
            except OSError as error:
                raise BluetoothError(
                    f"não foi possível iniciar bluetoothctl: {error}"
                ) from error
            self._attempt_counts[side] += 1
            self._attempts[side] = _ConnectAttempt(process, now)
            self._status(
                side,
                "connecting",
                f"tentativa {self._attempt_counts[side]} para {address}",
            )

    def close(self) -> None:
        for attempt in self._attempts.values():
            self._stop(attempt.process)
        self._attempts.clear()

    def _schedule(
        self, side: JoyConSide, now: float, detail: str, *, report: bool = True
    ) -> None:
        attempts = max(1, self._attempt_counts[side])
        delay = self._policy.initial_delay
        for _ in range(attempts - 1):
            delay = min(self._policy.max_delay, delay * self._policy.multiplier)
            if delay >= self._policy.max_delay:
                break
        self._next_attempt[side] = now + delay
        if report:
            self._status(side, "offline", f"{detail}; nova tentativa em {delay:g}s")

    def _status(self, side: JoyConSide, state: str, detail: str) -> None:
        status = (state, detail)
        if self._last_status.get(side) == status:
            return
        self._last_status[side] = status
        if self._on_status is not None:
            self._on_status(side, state, detail)

    @staticmethod
    def _stop(process: subprocess.Popen[str]) -> None:
        if process.poll() is None:
            process.terminate()
            try:
                process.communicate(timeout=0.2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate()
        else:
            process.communicate()
