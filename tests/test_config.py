from __future__ import annotations

from pathlib import Path

import pytest

from joyio.config import ConfigError, load_config
from joyio.config.models import BoostMapping, KeyChordMapping, MouseButtonMapping
from joyio.config.models import ToggleMapping
from joyio.controls import BUTTON_CONTROLS


def write_config(tmp_path: Path, content: str) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text(content, encoding="utf-8")
    return path


def test_loads_example_configuration() -> None:
    config = load_config("config.example.yaml")

    assert config.version == 1
    assert config.device.left_address is None
    assert config.device.right_address is None
    assert config.reconnect.enabled is True
    assert config.reconnect.initial_delay == 1.0
    assert config.reconnect.max_delay == 30.0
    assert config.reconnect.multiplier == 2.0
    assert config.reconnect.max_attempts is None
    assert config.runtime.enabled is True
    assert config.mouse is not None
    assert config.mouse.stick == "left_stick"
    assert config.scroll is not None
    assert config.scroll.stick == "right_stick"
    assert isinstance(config.buttons["right.a"], MouseButtonMapping)
    assert isinstance(config.buttons["right.x"], KeyChordMapping)
    assert isinstance(config.buttons["left.minus"], BoostMapping)
    assert config.buttons["left.zl"] == MouseButtonMapping("left", "hold")
    assert config.buttons["left.l"] == MouseButtonMapping("right", "hold")
    assert config.buttons["right.zr"] == MouseButtonMapping("right", "hold")
    assert config.buttons["right.r"] == MouseButtonMapping("left", "hold")
    assert config.buttons["left.capture"] == ToggleMapping()
    assert "left.dpad_up" in config.buttons
    expected_buttons = {
        f"{side}.{control}"
        for side, controls in BUTTON_CONTROLS.items()
        for control in controls.values()
    }
    assert set(config.buttons) == expected_buttons


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("version: 2\n", "somente a versão 1"),
        ("version: 1\nunknown: true\n", "config.unknown"),
        (
            "version: 1\n"
            "mappings: {buttons: {right: {b: {type: key, key: KEY_NOT_REAL}}}}\n",
            "mappings.buttons.right.b.key",
        ),
        (
            "version: 1\ndevices: {left: {address: invalid}}\n",
            "devices.left.address",
        ),
        (
            "version: 1\n"
            "mappings: {buttons: {right: {dpad_up: {type: key, key: KEY_UP}}}}\n",
            "desconhecido para right",
        ),
        (
            "version: 1\nreconnect: {initial_delay: 5, max_delay: 1}\n",
            "reconnect.max_delay",
        ),
        (
            "version: 1\nreconnect: {max_attempts: 0}\n",
            "reconnect.max_attempts",
        ),
        (
            "version: 1\nruntime: {enabled: maybe}\n",
            "runtime.enabled",
        ),
        (
            "version: 1\nmappings: {buttons: {left: {minus: {type: boost, factor: 0.5}}}}\n",
            "mappings.buttons.left.minus.factor",
        ),
        (
            "version: 1\nmappings: {buttons: {left: {capture: {type: toggle, extra: true}}}}\n",
            "mappings.buttons.left.capture.extra",
        ),
    ],
)
def test_rejects_invalid_config(tmp_path: Path, content: str, message: str) -> None:
    with pytest.raises(ConfigError, match=message):
        load_config(write_config(tmp_path, content))


def test_reports_invalid_yaml(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="YAML inválido"):
        load_config(write_config(tmp_path, "version: [\n"))
