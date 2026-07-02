from __future__ import annotations

import json
from pathlib import Path

from joyio import cli
from joyio.bluetooth import BluetoothDevice
from joyio.devices import JoyConInput
from joyio.events import NormalizedEvent


def test_list_without_joycon_is_successful_and_actionable(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli, "list_paired_devices", lambda: [])

    exit_code = cli.main(["list"])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Nenhum Joy-Con" in output
    assert "bluetoothctl" in output


def test_inspect_rejects_unknown_selector(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli, "list_paired_devices", lambda: [])

    exit_code = cli.main(["inspect", "--device", "right"])

    assert exit_code == cli.EXIT_NOT_FOUND
    assert "nenhum Joy-Con pareado" in capsys.readouterr().err


def test_inspect_keeps_stdout_as_jsonl(monkeypatch, capsys) -> None:
    paired = BluetoothDevice(
        address="11:22:33:44:55:66", name="Joy-Con (R)", side="right"
    )
    input_device = JoyConInput(
        path="/dev/input/fake",
        name="Joy-Con (R)",
        address=paired.address,
        side="right",
    )
    event = NormalizedEvent(
        kind="button",
        control="a",
        source_control="BTN_EAST",
        side="right",
        code=305,
        value=1.0,
        state="pressed",
        timestamp=1.5,
    )
    monkeypatch.setattr(cli, "list_paired_devices", lambda: [paired])
    monkeypatch.setattr(cli, "connect_device", lambda address: False)
    monkeypatch.setattr(cli, "wait_for_input", lambda address, timeout: input_device)
    monkeypatch.setattr(
        cli, "read_normalized_events", lambda path, side: iter([event])
    )

    exit_code = cli.main(["inspect", "--device", "right"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert json.loads(captured.out) == json.loads(event.to_json())
    assert "Joy-Con selecionado" in captured.err
    assert "Lendo /dev/input/fake" in captured.err


def test_validate_config_command(capsys) -> None:
    exit_code = cli.main(["validate-config", "config.example.yaml"])

    assert exit_code == 0
    assert "schema v1" in capsys.readouterr().out


def test_validate_config_reports_precise_error(tmp_path: Path, capsys) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text("version: 1\nextra: true\n", encoding="utf-8")

    exit_code = cli.main(["validate-config", str(path)])

    assert exit_code == cli.EXIT_CONFIG
    assert "config.extra" in capsys.readouterr().err


def test_run_dry_run_wires_both_devices(monkeypatch, capsys) -> None:
    paired = (
        BluetoothDevice(
            address="11:22:33:44:55:01", name="Joy-Con (L)", side="left"
        ),
        BluetoothDevice(
            address="11:22:33:44:55:02", name="Joy-Con (R)", side="right"
        ),
    )
    inputs = (
        JoyConInput("/dev/input/left", "Joy-Con (L)", paired[0].address, "left"),
        JoyConInput("/dev/input/right", "Joy-Con (R)", paired[1].address, "right"),
    )
    called = []
    monkeypatch.setattr(cli, "list_paired_devices", lambda: list(paired))
    monkeypatch.setattr(cli, "connect_device", lambda address: False)
    by_address = {item.address: item for item in inputs}
    monkeypatch.setattr(
        cli, "wait_for_input", lambda address, timeout: by_address[address]
    )
    monkeypatch.setattr(
        cli,
        "run_mapping",
        lambda selected, engine, output: called.append((selected, output)),
    )

    exit_code = cli.main(
        [
            "run",
            "--config",
            "config.example.yaml",
            "--dry-run",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert tuple(item.side for item in called[0][0]) == ("left", "right")
    assert called[0][1].__class__.__name__ == "DryRunOutput"
    assert "dry-run" in captured.err


def test_run_requires_one_joycon_of_each_side(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        cli,
        "list_paired_devices",
        lambda: [
            BluetoothDevice(
                address="11:22:33:44:55:01", name="Joy-Con (L)", side="left"
            )
        ],
    )

    exit_code = cli.main(["run", "--config", "config.example.yaml", "--dry-run"])

    assert exit_code == cli.EXIT_NOT_FOUND
    assert "'right'" in capsys.readouterr().err
