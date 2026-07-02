"""Linux evdev boundary for Joy-Con discovery and event inspection."""

from __future__ import annotations

from dataclasses import dataclass
import select
import time
from collections.abc import Callable, Iterator, Mapping, Sequence

from evdev import AbsInfo, InputDevice, InputEvent, ecodes, list_devices

from joyio.controls import JoyConSide
from joyio.events import DeviceStatusEvent, NormalizedEvent, normalize_event


NINTENDO_VENDOR_ID = 0x057E
JOYCON_PRODUCTS: dict[int, JoyConSide] = {
    0x2006: "left",
    0x2007: "right",
}


class InputDeviceError(RuntimeError):
    """A Joy-Con evdev node could not be found or read."""


@dataclass(frozen=True, slots=True)
class JoyConInput:
    path: str
    name: str
    address: str
    side: JoyConSide


def _cached_absinfo(
    device: InputDevice, cache: dict[int, AbsInfo | None], code: int
) -> AbsInfo | None:
    if code not in cache:
        try:
            cache[code] = device.absinfo(code)
        except OSError:
            cache[code] = None
    return cache[code]


def _is_joycon(device: InputDevice) -> bool:
    ids_match = (
        device.info.vendor == NINTENDO_VENDOR_ID
        and device.info.product in JOYCON_PRODUCTS
    )
    return ids_match or "joy-con" in device.name.casefold()


def _side(device: InputDevice) -> JoyConSide:
    by_id = JOYCON_PRODUCTS.get(device.info.product)
    if by_id is not None:
        return by_id
    name = device.name.casefold()
    if "left" in name or "(l)" in name:
        return "left"
    if "right" in name or "(r)" in name:
        return "right"
    raise InputDeviceError(f"não foi possível determinar o lado de {device.name!r}")


def list_joycon_inputs() -> list[JoyConInput]:
    found: list[JoyConInput] = []
    denied_paths: list[str] = []
    for path in list_devices():
        device: InputDevice | None = None
        try:
            device = InputDevice(path)
            if not _is_joycon(device):
                continue
            found.append(
                JoyConInput(
                    path=device.path,
                    name=device.name,
                    address=(device.uniq or "").upper(),
                    side=_side(device),
                )
            )
        except PermissionError:
            # Do not stop on the first protected keyboard/mouse. A targeted udev
            # rule may intentionally grant access only to the Joy-Con node.
            denied_paths.append(path)
        finally:
            if device is not None:
                device.close()
    if not found and denied_paths:
        raise InputDeviceError(
            "nenhum dispositivo de entrada acessível; verifique permissões udev "
            f"ou grupo input ({len(denied_paths)} nó(s) protegido(s))"
        )
    return found


def wait_for_input(address: str, timeout: float = 8.0) -> JoyConInput:
    normalized_address = address.upper()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        inputs = list_joycon_inputs()
        for candidate in inputs:
            if candidate.address == normalized_address:
                return candidate
        if len(inputs) == 1 and not inputs[0].address:
            return inputs[0]
        time.sleep(0.2)
    raise InputDeviceError(
        "Joy-Con conectado, mas nenhum evdev compatível apareceu. Verifique "
        "o módulo hid_nintendo, /dev/input e permissões udev."
    )


def read_normalized_events(
    device_path: str, side: JoyConSide
) -> Iterator[NormalizedEvent]:
    try:
        device = InputDevice(device_path)
    except (FileNotFoundError, PermissionError) as error:
        raise InputDeviceError(f"não foi possível abrir {device_path}: {error}") from error

    try:
        absinfo_cache: dict[int, AbsInfo | None] = {}
        for event in device.read_loop():
            absinfo = None
            if event.type == ecodes.EV_ABS:
                absinfo = _cached_absinfo(device, absinfo_cache, event.code)
            normalized = normalize_event(event, side=side, absinfo=absinfo)
            if normalized is not None:
                yield normalized
    except OSError as error:
        raise InputDeviceError(
            f"o dispositivo {device_path} foi desconectado ou falhou: {error}"
        ) from error
    finally:
        device.close()


def read_runtime_events(
    inputs: Sequence[JoyConInput],
    *,
    tick_interval: float = 1.0 / 120.0,
) -> Iterator[NormalizedEvent | None]:
    """Multiplex Joy-Con inputs and yield normalized events plus periodic ticks."""

    opened: dict[int, tuple[InputDevice, JoyConInput]] = {}
    absinfo_caches: dict[int, dict[int, AbsInfo | None]] = {}
    try:
        for source in inputs:
            try:
                device = InputDevice(source.path)
            except (FileNotFoundError, PermissionError) as error:
                raise InputDeviceError(
                    f"não foi possível abrir {source.path}: {error}"
                ) from error
            opened[device.fd] = (device, source)
            absinfo_caches[device.fd] = {}

        file_descriptors = tuple(opened)
        while True:
            readable, _, _ = select.select(file_descriptors, [], [], tick_interval)
            if not readable:
                yield None
                continue
            yielded = False
            for fd in readable:
                device, source = opened[fd]
                for event in device.read():
                    absinfo = None
                    if event.type == ecodes.EV_ABS:
                        absinfo = _cached_absinfo(
                            device, absinfo_caches[fd], event.code
                        )
                    normalized = normalize_event(
                        event, side=source.side, absinfo=absinfo
                    )
                    if normalized is not None:
                        yielded = True
                        yield normalized
            if not yielded:
                yield None
    except OSError as error:
        paths = ", ".join(source.path for source in inputs)
        raise InputDeviceError(
            f"um Joy-Con ({paths}) foi desconectado ou falhou: {error}"
        ) from error
    finally:
        for device, _ in opened.values():
            device.close()


Discovery = Callable[[], list[JoyConInput]]


def read_managed_events(
    expected_addresses: Mapping[JoyConSide, str],
    *,
    tick_interval: float = 1.0 / 120.0,
    discovery_interval: float = 0.5,
    discover: Discovery = list_joycon_inputs,
    clock: Callable[[], float] = time.monotonic,
) -> Iterator[NormalizedEvent | DeviceStatusEvent | None]:
    """Read nodes dynamically so either Joy-Con can disappear and return."""

    opened: dict[
        JoyConSide, tuple[InputDevice, JoyConInput, dict[int, AbsInfo | None]]
    ] = {}
    next_discovery = 0.0

    def detach(side: JoyConSide) -> DeviceStatusEvent:
        device, source, _ = opened.pop(side)
        device.close()
        return DeviceStatusEvent(side, "disconnected", source.path)

    try:
        while True:
            now = clock()
            missing = tuple(side for side in expected_addresses if side not in opened)
            if missing and now >= next_discovery:
                candidates = discover()
                for side in missing:
                    address = expected_addresses[side].upper()
                    matches = [
                        item
                        for item in candidates
                        if item.side == side
                        and (not item.address or item.address.upper() == address)
                    ]
                    if len(matches) != 1:
                        continue
                    source = matches[0]
                    try:
                        device = InputDevice(source.path)
                    except (FileNotFoundError, PermissionError, OSError):
                        # The node may vanish between discovery and open. The next
                        # short discovery pass will retry only this side.
                        continue
                    opened[side] = (device, source, {})
                    yield DeviceStatusEvent(side, "connected", source.path)
                next_discovery = clock() + discovery_interval

            now = clock()
            timeout = tick_interval
            if any(side not in opened for side in expected_addresses):
                timeout = min(timeout, max(0.0, next_discovery - now))
            by_fd = {
                device.fd: (side, device, source, cache)
                for side, (device, source, cache) in opened.items()
            }
            try:
                readable, _, _ = select.select(tuple(by_fd), [], [], timeout)
            except (OSError, ValueError):
                # A concurrently removed fd can make the grouped select fail.
                # Probe each descriptor separately and detach only invalid ones.
                readable = []
                invalid_sides: list[JoyConSide] = []
                for fd, (side, _, _, _) in by_fd.items():
                    try:
                        ready, _, _ = select.select((fd,), [], [], 0.0)
                        readable.extend(ready)
                    except (OSError, ValueError):
                        invalid_sides.append(side)
                for side in invalid_sides:
                    if side in opened:
                        yield detach(side)
                        next_discovery = 0.0
            if not readable:
                yield None
                continue

            yielded = False
            for fd in readable:
                entry = by_fd.get(fd)
                if entry is None:
                    continue
                side, device, source, cache = entry
                try:
                    events = device.read()
                except BlockingIOError:
                    continue
                except OSError:
                    if side in opened:
                        yielded = True
                        yield detach(side)
                        next_discovery = 0.0
                    continue
                try:
                    for event in events:
                        absinfo = None
                        if event.type == ecodes.EV_ABS:
                            absinfo = _cached_absinfo(device, cache, event.code)
                        normalized = normalize_event(
                            event, side=source.side, absinfo=absinfo
                        )
                        if normalized is not None:
                            yielded = True
                            yield normalized
                except OSError:
                    if side in opened:
                        yielded = True
                        yield detach(side)
                        next_discovery = 0.0
            if not yielded:
                yield None
    finally:
        for device, _, _ in opened.values():
            device.close()
