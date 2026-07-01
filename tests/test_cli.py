from __future__ import annotations

import json

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
