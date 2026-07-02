"""Command-line entry point for JoyIO capture and mapping."""

from __future__ import annotations

import argparse
import os
import pathlib
from queue import SimpleQueue
import shutil
import signal
import subprocess
import sys
from typing import Sequence

from joyio import __version__
from joyio.bluetooth import (
    BluetoothDevice,
    BluetoothConnector,
    BluetoothError,
    connect_device,
    list_paired_devices,
)
from joyio.config import ConfigError, JoyIOConfig, load_config
from joyio.devices import InputDeviceError, read_normalized_events, wait_for_input
from joyio.mapping import MappingEngine
from joyio.output import DryRunOutput, OutputError, UInputOutput
from joyio.runtime import run_managed_mapping, run_mapping
from joyio.runtime.watcher import ConfigWatcher
from joyio.tray import JoyIOTray


def _handle_terminate(signum: int, frame: object) -> None:
    """Convert SIGTERM (and SIGINT) into KeyboardInterrupt for clean shutdown.

    systemd sends SIGTERM on service stop; this ensures the runtime's
    finally blocks release uinput devices and holds before exiting.
    """
    raise KeyboardInterrupt(f"signal {signum} ({signal.Signals(signum).name})")


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
    run.add_argument(
        "--no-reconnect",
        action="store_true",
        help="encerra na primeira falha de Bluetooth ou evdev",
    )

    service = commands.add_parser(
        "service", help="gerencia o serviço systemd de usuário"
    )
    service_cmds = service.add_subparsers(dest="service_command", required=True)
    svc_install = service_cmds.add_parser(
        "install", help="instala e habilita o serviço de usuário"
    )
    svc_install.add_argument(
        "--config",
        required=True,
        help="arquivo YAML de mapeamento (será copiado para XDG_CONFIG_HOME/joyio/)",
    )
    svc_install.add_argument(
        "--enable",
        action="store_true",
        default=True,
        help="habilita início automático no login (padrão: true)",
    )
    svc_install.add_argument(
        "--no-enable",
        action="store_false",
        dest="enable",
        help="não habilita início automático",
    )
    svc_install.add_argument(
        "--start",
        action="store_true",
        help="inicia o serviço imediatamente após a instalação",
    )
    service_cmds.add_parser("uninstall", help="para, desabilita e remove o serviço")
    service_cmds.add_parser(
        "status", help="exibe o status do serviço via systemctl"
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
    no_reconnect: bool,
) -> int:
    config = load_config(path)
    selected = _select_pair(config, _paired_joycons(), left_selector, right_selector)
    for device in selected:
        print(
            f"Joy-Con {device.side}: {device.name} [{device.address}]", file=sys.stderr
        )
    mode = "dry-run" if dry_run else "uinput"
    watcher = _create_watcher(path)
    control_queue = None if dry_run else SimpleQueue()
    tray = (
        None
        if dry_run
        else JoyIOTray(
            str(pathlib.Path(path).resolve()),
            on_action=control_queue.put if control_queue is not None else None,
        )
    )
    try:
        config_fd = watcher.fd if watcher else None
        config_full_path = str(pathlib.Path(path).resolve())
        if no_reconnect or not config.reconnect.enabled:
            for device in selected:
                changed = connect_device(device.address)
                status = "Conexão solicitada." if changed else "Já conectado."
                print(f"  {device.side}: {status}", file=sys.stderr)
            inputs = tuple(
                wait_for_input(device.address, timeout=timeout) for device in selected
            )
            output = DryRunOutput() if dry_run else UInputOutput(config)
            paths = ", ".join(f"{item.side}={item.path}" for item in inputs)
            print(
                f"Executando par Joy-Con ({paths}) em {mode}; Ctrl+C encerra.",
                file=sys.stderr,
            )
            print(
                f"  mapping: {'enabled' if config.runtime.enabled else 'disabled'}",
                file=sys.stderr,
            )

            def report_mode(enabled: bool) -> None:
                state = "enabled" if enabled else "disabled"
                print(f"  mapping: {state}", file=sys.stderr)
                if tray is not None:
                    tray.set_mapping_enabled(enabled)

            if tray is not None:
                tray.start()
                tray.set_mapping_enabled(config.runtime.enabled)
            run_mapping(
                inputs,
                MappingEngine(config),
                output,
                on_mode_change=report_mode,
                config_fd=config_fd,
                config_path=config_full_path,
                config_watcher=watcher,
                control_queue=control_queue,
            )
        else:
            addresses = {device.side: device.address for device in selected}

            def report_connection(side: str, state: str, detail: str) -> None:
                print(f"  {side}: {state} — {detail}", file=sys.stderr)

            def report_device(event) -> None:
                state = "evdev_ready" if event.state == "connected" else "offline"
                print(f"  {event.side}: {state} — {event.path}", file=sys.stderr)

            connector = BluetoothConnector(
                addresses,
                config.reconnect,
                timeout=timeout,
                on_status=report_connection,
            )
            output = DryRunOutput() if dry_run else UInputOutput(config)
            print(
                f"Executando Joy-Cons independentes em {mode}; Ctrl+C encerra.",
                file=sys.stderr,
            )
            print(
                f"  mapping: {'enabled' if config.runtime.enabled else 'disabled'}",
                file=sys.stderr,
            )

            def report_mode(enabled: bool) -> None:
                state = "enabled" if enabled else "disabled"
                print(f"  mapping: {state}", file=sys.stderr)
                if tray is not None:
                    tray.set_mapping_enabled(enabled)

            try:
                if tray is not None:
                    tray.start()
                    tray.set_mapping_enabled(config.runtime.enabled)
                run_managed_mapping(
                    addresses,
                    MappingEngine(config),
                    output,
                    connector.maintain,
                    on_device_status=report_device,
                    on_mode_change=report_mode,
                    config_fd=config_fd,
                    config_path=config_full_path,
                    config_watcher=watcher,
                    control_queue=control_queue,
                )
            finally:
                connector.close()
    except KeyboardInterrupt:
        print("\nEncerramento solicitado; entradas liberadas.", file=sys.stderr)
    finally:
        if tray is not None:
            tray.stop()
        if watcher is not None:
            watcher.close()
    return EXIT_OK


# ---------------------------------------------------------------------------
# systemd user service helpers
# ---------------------------------------------------------------------------

_SERVICE_NAME = "joyio"
_SYSTEMD_USER_DIR = pathlib.Path.home() / ".config" / "systemd" / "user"
_JOYIO_CONFIG_DIR = (
    pathlib.Path(os.environ.get("XDG_CONFIG_HOME", pathlib.Path.home() / ".config"))
    / "joyio"
)


def _resolve_joyio_bin() -> pathlib.Path:
    """Return the absolute path to the joyio console script.

    When installed via pip (``pip install -e .`` or ``pip install joyio``),
    setuptools writes a console script next to the Python interpreter.
    We resolve it by deriving the path from ``sys.executable`` (always
    absolute in a venv), then falling back to PATH.
    """
    # The console script lives alongside the Python interpreter in a venv.
    bin_dir = pathlib.Path(sys.executable).parent
    candidate = bin_dir / "joyio"
    if candidate.exists():
        return candidate
    # Bare-metal install (pipx, system pip) — joyio is on PATH.
    which_bin = shutil.which("joyio")
    if which_bin is not None:
        return pathlib.Path(which_bin)
    raise LookupError(
        "não foi possível localizar o binário 'joyio'. "
        "Execute 'pip install -e .' no ambiente virtual."
    )


def _service_unit_content(bin_path: pathlib.Path, config_path: pathlib.Path) -> str:
    """Generate the systemd user unit file content."""
    return f"""[Unit]
Description=JoyIO — Joy-Con keyboard and mouse mapping
Documentation=https://github.com/joyio/joyio
After=graphical-session.target bluetooth.target
Wants=bluetooth.target
PartOf=graphical-session.target

[Service]
Type=simple
ExecStart={bin_path} run --config {config_path}
Restart=on-failure
RestartSec=3
StandardOutput=journal
StandardError=journal
SyslogIdentifier={_SERVICE_NAME}
KillSignal=SIGTERM
TimeoutStopSec=5

[Install]
WantedBy=graphical-session.target
"""


def _run_systemctl(*args: str) -> subprocess.CompletedProcess[str]:
    """Run ``systemctl --user`` and return the completed process."""
    return subprocess.run(
        ["systemctl", "--user", *args],
        capture_output=True,
        text=True,
        timeout=15,
    )


def _service_install(config_path: str, enable: bool, start: bool) -> int:
    """Install the systemd user service."""
    config_file = pathlib.Path(config_path).resolve()
    if not config_file.exists():
        print(f"Erro: arquivo de configuração não encontrado: {config_file}",
              file=sys.stderr)
        return EXIT_CONFIG

    # Validate the config before installing anything.
    try:
        load_config(str(config_file))
    except ConfigError as error:
        print(f"Erro de configuração: {error}", file=sys.stderr)
        return EXIT_CONFIG

    bin_path = _resolve_joyio_bin()
    unit_path = _SYSTEMD_USER_DIR / f"{_SERVICE_NAME}.service"

    # Ensure XDG directories exist.
    _JOYIO_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    _SYSTEMD_USER_DIR.mkdir(parents=True, exist_ok=True)

    # Copy config to XDG if it's not already there.
    target_config = _JOYIO_CONFIG_DIR / "config.yaml"
    if config_file != target_config.resolve():
        shutil.copy2(config_file, target_config)
        print(f"Configuração copiada para {target_config}", file=sys.stderr)

    # Write the unit file.
    unit_content = _service_unit_content(bin_path, target_config)
    unit_path.write_text(unit_content)
    print(f"Unidade systemd instalada em {unit_path}", file=sys.stderr)

    # Reload systemd user daemon.
    result = _run_systemctl("daemon-reload")
    if result.returncode != 0:
        print(f"Erro ao recarregar systemd: {result.stderr}", file=sys.stderr)
        return EXIT_CONFIG

    if enable:
        result = _run_systemctl("enable", _SERVICE_NAME)
        if result.returncode != 0:
            print(f"Erro ao habilitar serviço: {result.stderr}", file=sys.stderr)
            return EXIT_CONFIG
        print(f"Serviço habilitado para início automático no login.", file=sys.stderr)

    if start:
        result = _run_systemctl("start", _SERVICE_NAME)
        if result.returncode != 0:
            print(f"Erro ao iniciar serviço: {result.stderr}", file=sys.stderr)
            return EXIT_CONFIG
        print("Serviço iniciado.", file=sys.stderr)

    print(file=sys.stderr)
    print(f"✓ JoyIO instalado como serviço de usuário.", file=sys.stderr)
    print(f"  Binário:       {bin_path}", file=sys.stderr)
    print(f"  Configuração:  {target_config}", file=sys.stderr)
    print(f"  Unidade:       {unit_path}", file=sys.stderr)
    print(f"  Início auto:   {'sim' if enable else 'não'}", file=sys.stderr)
    print(f"  Status:        systemctl --user status {_SERVICE_NAME}", file=sys.stderr)
    return EXIT_OK


def _service_uninstall() -> int:
    """Stop, disable, and remove the systemd user service."""
    unit_path = _SYSTEMD_USER_DIR / f"{_SERVICE_NAME}.service"

    if not unit_path.exists():
        print(f"Serviço não está instalado ({unit_path} não encontrado).",
              file=sys.stderr)
        return EXIT_OK

    # Stop and disable.
    _run_systemctl("stop", _SERVICE_NAME)
    _run_systemctl("disable", _SERVICE_NAME)

    unit_path.unlink()
    print(f"Unidade removida: {unit_path}", file=sys.stderr)

    _run_systemctl("daemon-reload")
    print("Serviço desinstalado.", file=sys.stderr)
    return EXIT_OK


def _service_status() -> int:
    """Display the service status via systemctl."""
    result = subprocess.run(
        ["systemctl", "--user", "status", _SERVICE_NAME],
        text=True,
    )
    return EXIT_OK if result.returncode in (0, 3) else EXIT_CONFIG


def _create_watcher(config_path: str) -> ConfigWatcher | None:
    """Create an inotify watcher for config hot reload.

    Returns None when inotify is unavailable (e.g. kernel limit reached).
    Hot reload is a convenience feature — failure to watch should not
    prevent the main mapping loop from running.
    """
    try:
        return ConfigWatcher(config_path)
    except OSError as error:
        print(f"  config: hot reload desabilitado — {error}", file=sys.stderr)
        return None


def main(argv: Sequence[str] | None = None) -> int:
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, _handle_terminate)
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
                arguments.no_reconnect,
            )
        if arguments.command == "service":
            if arguments.service_command == "install":
                return _service_install(
                    arguments.config,
                    arguments.enable,
                    arguments.start,
                )
            if arguments.service_command == "uninstall":
                return _service_uninstall()
            if arguments.service_command == "status":
                return _service_status()
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
