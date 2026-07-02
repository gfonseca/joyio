"""Command-line entry point for JoyIO capture and mapping."""

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
from joyio.config import ConfigError, JoyIOConfig, load_config
from joyio.devices import InputDeviceError, read_normalized_events, wait_for_input
from joyio.mapping import MappingEngine
from joyio.output import DryRunOutput, OutputError, UInputOutput
from joyio.runtime import run_mapping


EXIT_OK = 0
EXIT_NOT_FOUND = 2
EXIT_BLUETOOTH = 3
EXIT_INPUT = 4
EXIT_CONFIG = 5
EXIT_OUTPUT = 6


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
    validate = commands.add_parser(
        "validate-config", help="valida um arquivo YAML sem conectar ao controle"
    )
    validate.add_argument("config", help="caminho do arquivo YAML")

    run = commands.add_parser(
        "run", help="aplica o mapeamento e emite teclado/mouse"
    )
    run.add_argument(
        "--left-device",
        help="endereço do Joy-Con L; sobrescreve devices.left.address do YAML",
    )
    run.add_argument(
        "--right-device",
        help="endereço do Joy-Con R; sobrescreve devices.right.address do YAML",
    )
    run.add_argument("--config", required=True, help="arquivo YAML de mapeamento")
    run.add_argument(
        "--dry-run",
        action="store_true",
        help="imprime ações JSONL sem criar dispositivo virtual",
    )
    run.add_argument(
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


def _select_pair(
    config: JoyIOConfig,
    devices: list[BluetoothDevice],
    left_override: str | None,
    right_override: str | None,
) -> tuple[BluetoothDevice, BluetoothDevice]:
    selectors = {
        "left": left_override or config.device.left_address or "left",
        "right": right_override or config.device.right_address or "right",
    }
    selected = {
        side: _select_device(selector, devices) for side, selector in selectors.items()
    }
    for side, device in selected.items():
        if device.side != side:
            raise ConfigError(
                f"Joy-Con configurado para {side} é do lado {device.side}: "
                f"{device.address}"
            )
    if selected["left"].address == selected["right"].address:
        raise ConfigError("os Joy-Cons esquerdo e direito não podem ter o mesmo endereço")
    return selected["left"], selected["right"]


def _validate_config_command(path: str) -> int:
    load_config(path)
    print(f"Configuração válida (schema v1): {path}")
    return EXIT_OK


def _run_command(
    path: str,
    left_selector: str | None,
    right_selector: str | None,
    timeout: float,
    dry_run: bool,
) -> int:
    config = load_config(path)
    selected = _select_pair(config, _paired_joycons(), left_selector, right_selector)
    for device in selected:
        print(
            f"Joy-Con {device.side}: {device.name} [{device.address}]", file=sys.stderr
        )
        changed = connect_device(device.address)
        status = "Conexão Bluetooth solicitada." if changed else "Já conectado."
        print(f"  {status}", file=sys.stderr)
    inputs = tuple(
        wait_for_input(device.address, timeout=timeout) for device in selected
    )
    output = DryRunOutput() if dry_run else UInputOutput(config)
    mode = "dry-run" if dry_run else "uinput"
    paths = ", ".join(f"{item.side}={item.path}" for item in inputs)
    print(
        f"Executando par Joy-Con ({paths}) em {mode}; Ctrl+C encerra.",
        file=sys.stderr,
    )
    try:
        run_mapping(
            inputs,
            MappingEngine(config),
            output,
        )
    except KeyboardInterrupt:
        print("\nEncerramento solicitado; entradas liberadas.", file=sys.stderr)
    return EXIT_OK


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        if arguments.command == "list":
            return _list_command()
        if arguments.command == "inspect":
            return _inspect_command(arguments.device, arguments.timeout)
        if arguments.command == "validate-config":
            return _validate_config_command(arguments.config)
        if arguments.command == "run":
            return _run_command(
                arguments.config,
                arguments.left_device,
                arguments.right_device,
                arguments.timeout,
                arguments.dry_run,
            )
    except ConfigError as error:
        print(f"Erro de configuração: {error}", file=sys.stderr)
        return EXIT_CONFIG
    except LookupError as error:
        print(str(error), file=sys.stderr)
        return EXIT_NOT_FOUND
    except BluetoothError as error:
        print(f"Erro de Bluetooth: {error}", file=sys.stderr)
        return EXIT_BLUETOOTH
    except InputDeviceError as error:
        print(f"Erro de entrada: {error}", file=sys.stderr)
        return EXIT_INPUT
    except OutputError as error:
        print(f"Erro de saída: {error}", file=sys.stderr)
        return EXIT_OUTPUT
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
