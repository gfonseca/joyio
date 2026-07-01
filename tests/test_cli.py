from __future__ import annotations

from joyio import cli


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
