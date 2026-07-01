"""Command-line entry point for JoyIO input inspection."""

from __future__ import annotations

import argparse
import sys
from typing import Sequence

from joyio import __version__
from joyio.bluetooth import (
    BluetoothDevice,
    BluetoothError,
    connect_device,
    list_paired_devices,
)
from joyio.devices import InputDeviceError, read_normalized_events, wait_for_input


EXIT_OK = 0
EXIT_NOT_FOUND = 2
EXIT_BLUETOOTH = 3
EXIT_INPUT = 4


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="joyio", description="JoyIO — captura canônica de eventos Joy-Con"
    )
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list", help="lista Joy-Cons previamente pareados")

    inspect = commands.add_parser(
        "inspect", help="conecta e imprime eventos normalizados"
    )
    inspect.add_argument(
        "--device", required=True, help="endereço Bluetooth ou left/right"
    )
    inspect.add_argument(
        "--timeout", type=float, default=8.0, help="espera pelo evdev em segundos"
    )
    return parser


def _paired_joycons() -> list[BluetoothDevice]:
    return [device for device in list_paired_devices() if device.is_joycon]


def _select_device(selector: str, devices: list[BluetoothDevice]) -> BluetoothDevice:
    normalized = selector.strip().casefold()
    matches = [
        device
        for device in devices
        if device.address.casefold() == normalized or device.side == normalized
    ]
    if not matches:
        raise LookupError(
            f"nenhum Joy-Con pareado corresponde a {selector!r}; execute 'joyio list'"
        )
    if len(matches) > 1:
        raise LookupError(
            f"{selector!r} é ambíguo; informe o endereço Bluetooth exibido por 'joyio list'"
        )
    return matches[0]


def _list_command() -> int:
    devices = _paired_joycons()
    if not devices:
        print(
            "Nenhum Joy-Con previamente pareado foi encontrado.\n"
            "Coloque o controle em modo de sincronização, use bluetoothctl para "
            "scan/pair/trust e execute novamente."
        )
        return EXIT_OK
    for device in devices:
        print(f"{device.address}\t{device.side}\t{device.name}")
    return EXIT_OK


def _inspect_command(selector: str, timeout: float) -> int:
    try:
        device = _select_device(selector, _paired_joycons())
    except LookupError as error:
        print(str(error), file=sys.stderr)
        return EXIT_NOT_FOUND

    print(
        f"Joy-Con selecionado: {device.name} [{device.address}]", file=sys.stderr
    )
    changed = connect_device(device.address)
    print(
        "Conexão Bluetooth solicitada." if changed else "Joy-Con já conectado.",
        file=sys.stderr,
    )
    input_device = wait_for_input(device.address, timeout=timeout)
    print(
        f"Lendo {input_device.path} ({input_device.name}). "
        "Pressione botões/mova o analógico; Ctrl+C encerra.",
        file=sys.stderr,
    )
    try:
        for event in read_normalized_events(input_device.path, input_device.side):
            print(event.to_json(), flush=True)
    except KeyboardInterrupt:
        print("\nEncerramento solicitado; leitor fechado.", file=sys.stderr)
    return EXIT_OK


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        if arguments.command == "list":
            return _list_command()
        if arguments.command == "inspect":
            return _inspect_command(arguments.device, arguments.timeout)
    except BluetoothError as error:
        print(f"Erro de Bluetooth: {error}", file=sys.stderr)
        return EXIT_BLUETOOTH
    except InputDeviceError as error:
        print(f"Erro de entrada: {error}", file=sys.stderr)
        return EXIT_INPUT
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
