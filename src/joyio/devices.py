"""Linux evdev boundary for Joy-Con discovery and event inspection."""

from __future__ import annotations

from contextlib import suppress
from dataclasses import dataclass
import time
from typing import Iterator

from evdev import InputDevice, InputEvent, ecodes, list_devices

from joyio.events import NormalizedEvent, normalize_event


NINTENDO_VENDOR_ID = 0x057E
JOYCON_PRODUCTS = {
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
    side: str


def _is_joycon(device: InputDevice) -> bool:
    ids_match = (
        device.info.vendor == NINTENDO_VENDOR_ID
        and device.info.product in JOYCON_PRODUCTS
    )
    return ids_match or "joy-con" in device.name.casefold()


def _side(device: InputDevice) -> str:
    by_id = JOYCON_PRODUCTS.get(device.info.product)
    if by_id is not None:
        return by_id
    name = device.name.casefold()
    if "left" in name or "(l)" in name:
        return "left"
    if "right" in name or "(r)" in name:
        return "right"
    return "unknown"


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


def read_normalized_events(device_path: str) -> Iterator[NormalizedEvent]:
    try:
        device = InputDevice(device_path)
    except (FileNotFoundError, PermissionError) as error:
        raise InputDeviceError(f"não foi possível abrir {device_path}: {error}") from error

    try:
        for event in device.read_loop():
            absinfo = None
            if event.type == ecodes.EV_ABS:
                with suppress(OSError):
                    absinfo = device.absinfo(event.code)
            normalized = normalize_event(event, absinfo=absinfo)
            if normalized is not None:
                yield normalized
    except OSError as error:
        raise InputDeviceError(
            f"o dispositivo {device_path} foi desconectado ou falhou: {error}"
        ) from error
    finally:
        device.close()
