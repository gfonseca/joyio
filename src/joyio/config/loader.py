"""Strict YAML loader for the JoyIO version 1 schema."""

from __future__ import annotations

from pathlib import Path
import re
from typing import Any, Mapping

from evdev import ecodes
import yaml

from joyio.config.models import (
    ButtonMapping,
    BoostMapping,
    DeviceConfig,
    JoyIOConfig,
    KeyChordMapping,
    KeyMapping,
    MouseButtonMapping,
    MouseConfig,
    ReconnectConfig,
    RuntimeConfig,
    ScrollConfig,
    ToggleMapping,
)
from joyio.controls import BUTTON_CONTROLS


class ConfigError(ValueError):
    """The configuration is invalid and must not be partially applied."""


_ADDRESS = re.compile(r"^(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$")
_BUTTONS_BY_SIDE = {
    side: frozenset(controls.values()) for side, controls in BUTTON_CONTROLS.items()
}


def _mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ConfigError(f"{path}: esperado objeto/mapa")
    return value


def _only(data: Mapping[str, Any], allowed: set[str], path: str) -> None:
    unknown = set(data) - allowed
    if unknown:
        field = sorted(unknown)[0]
        raise ConfigError(f"{path}.{field}: campo desconhecido")


def _number(value: Any, path: str, minimum: float, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"{path}: esperado número")
    result = float(value)
    if not minimum <= result <= maximum:
        raise ConfigError(f"{path}: deve estar entre {minimum:g} e {maximum:g}")
    return result


def _boolean(value: Any, path: str) -> bool:
    if not isinstance(value, bool):
        raise ConfigError(f"{path}: esperado true ou false")
    return value


def _optional_integer(value: Any, path: str, minimum: int, maximum: int) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"{path}: esperado número inteiro ou null")
    if not minimum <= value <= maximum:
        raise ConfigError(f"{path}: deve estar entre {minimum} e {maximum}, ou null")
    return value


def _enum(value: Any, choices: set[str], path: str) -> str:
    if not isinstance(value, str) or value not in choices:
        options = ", ".join(sorted(choices))
        raise ConfigError(f"{path}: esperado um de: {options}")
    return value


def _key(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.startswith("KEY_"):
        raise ConfigError(f"{path}: esperado código Linux KEY_*")
    code = getattr(ecodes, value, None)
    if not isinstance(code, int):
        raise ConfigError(f"{path}: código de tecla desconhecido {value!r}")
    return value


def _address(value: Any, path: str) -> str | None:
    if value is not None and (not isinstance(value, str) or not _ADDRESS.fullmatch(value)):
        raise ConfigError(
            f"{path}: esperado endereço Bluetooth AA:BB:CC:DD:EE:FF ou null"
        )
    return value.upper() if value else None


def _devices(root: Mapping[str, Any]) -> DeviceConfig:
    data = _mapping(root.get("devices", {}), "devices")
    _only(data, {"left", "right"}, "devices")
    addresses: dict[str, str | None] = {}
    for side in ("left", "right"):
        item = _mapping(data.get(side, {}), f"devices.{side}")
        _only(item, {"address"}, f"devices.{side}")
        addresses[side] = _address(item.get("address"), f"devices.{side}.address")
    return DeviceConfig(
        left_address=addresses["left"], right_address=addresses["right"]
    )


def _reconnect(root: Mapping[str, Any]) -> ReconnectConfig:
    data = _mapping(root.get("reconnect", {}), "reconnect")
    _only(
        data,
        {"enabled", "initial_delay", "max_delay", "multiplier", "max_attempts"},
        "reconnect",
    )
    initial_delay = _number(
        data.get("initial_delay", 1.0), "reconnect.initial_delay", 0.1, 300.0
    )
    max_delay = _number(
        data.get("max_delay", 30.0), "reconnect.max_delay", 0.1, 3600.0
    )
    if max_delay < initial_delay:
        raise ConfigError(
            "reconnect.max_delay: deve ser maior ou igual a reconnect.initial_delay"
        )
    return ReconnectConfig(
        enabled=_boolean(data.get("enabled", True), "reconnect.enabled"),
        initial_delay=initial_delay,
        max_delay=max_delay,
        multiplier=_number(
            data.get("multiplier", 2.0), "reconnect.multiplier", 1.0, 10.0
        ),
        max_attempts=_optional_integer(
            data.get("max_attempts"), "reconnect.max_attempts", 1, 1000
        ),
    )


def _runtime(root: Mapping[str, Any]) -> RuntimeConfig:
    data = _mapping(root.get("runtime", {}), "runtime")
    _only(data, {"enabled"}, "runtime")
    return RuntimeConfig(
        enabled=_boolean(data.get("enabled", True), "runtime.enabled")
    )


def _mouse(root: Mapping[str, Any]) -> MouseConfig | None:
    if "mouse" not in root or root["mouse"] is None:
        return None
    data = _mapping(root["mouse"], "mouse")
    _only(
        data,
        {
            "stick",
            "dead_zone",
            "sensitivity",
            "acceleration",
            "max_speed",
            "invert_x",
            "invert_y",
        },
        "mouse",
    )
    stick = _enum(data.get("stick"), {"left_stick", "right_stick"}, "mouse.stick")
    return MouseConfig(
        stick=stick,  # type: ignore[arg-type]
        dead_zone=_number(data.get("dead_zone", 0.12), "mouse.dead_zone", 0.0, 0.95),
        sensitivity=_number(
            data.get("sensitivity", 900.0), "mouse.sensitivity", 1.0, 10000.0
        ),
        acceleration=_number(
            data.get("acceleration", 1.4), "mouse.acceleration", 0.1, 5.0
        ),
        max_speed=_number(
            data.get("max_speed", 1800.0), "mouse.max_speed", 1.0, 10000.0
        ),
        invert_x=_boolean(data.get("invert_x", False), "mouse.invert_x"),
        invert_y=_boolean(data.get("invert_y", True), "mouse.invert_y"),
    )


def _scroll(root: Mapping[str, Any]) -> ScrollConfig | None:
    if "scroll" not in root or root["scroll"] is None:
        return None
    data = _mapping(root["scroll"], "scroll")
    _only(
        data,
        {
            "stick",
            "dead_zone",
            "sensitivity",
            "acceleration",
            "max_speed",
            "invert_x",
            "invert_y",
        },
        "scroll",
    )
    stick = _enum(data.get("stick"), {"left_stick", "right_stick"}, "scroll.stick")
    return ScrollConfig(
        stick=stick,  # type: ignore[arg-type]
        dead_zone=_number(
            data.get("dead_zone", 0.18), "scroll.dead_zone", 0.0, 0.95
        ),
        sensitivity=_number(
            data.get("sensitivity", 18.0), "scroll.sensitivity", 0.1, 200.0
        ),
        acceleration=_number(
            data.get("acceleration", 1.3), "scroll.acceleration", 0.1, 5.0
        ),
        max_speed=_number(
            data.get("max_speed", 30.0), "scroll.max_speed", 0.1, 200.0
        ),
        invert_x=_boolean(data.get("invert_x", False), "scroll.invert_x"),
        invert_y=_boolean(data.get("invert_y", True), "scroll.invert_y"),
    )


def _button_mapping(value: Any, path: str) -> ButtonMapping:
    data = _mapping(value, path)
    action_type = _enum(
        data.get("type"),
        {"key", "key_chord", "mouse_button", "toggle", "boost"},
        f"{path}.type",
    )
    if action_type == "toggle":
        _only(data, {"type"}, path)
        return ToggleMapping()
    if action_type == "boost":
        _only(data, {"type", "factor"}, path)
        return BoostMapping(
            factor=_number(data.get("factor", 2.0), f"{path}.factor", 1.0, 8.0)
        )
    mode = _enum(data.get("mode", "hold"), {"tap", "hold"}, f"{path}.mode")
    if action_type == "key":
        _only(data, {"type", "key", "mode"}, path)
        return KeyMapping(
            key=_key(data.get("key"), f"{path}.key"),
            mode=mode,  # type: ignore[arg-type]
        )
    if action_type == "key_chord":
        _only(data, {"type", "keys", "mode"}, path)
        values = data.get("keys")
        if not isinstance(values, list) or not 2 <= len(values) <= 8:
            raise ConfigError(f"{path}.keys: esperado lista de 2 a 8 códigos KEY_*")
        keys = tuple(
            _key(item, f"{path}.keys[{index}]")
            for index, item in enumerate(values)
        )
        if len(set(keys)) != len(keys):
            raise ConfigError(f"{path}.keys: não deve conter teclas repetidas")
        return KeyChordMapping(keys=keys, mode=mode)  # type: ignore[arg-type]
    _only(data, {"type", "button", "mode"}, path)
    button = _enum(data.get("button"), {"left", "middle", "right"}, f"{path}.button")
    return MouseButtonMapping(button=button, mode=mode)  # type: ignore[arg-type]


def _buttons(root: Mapping[str, Any]) -> dict[str, ButtonMapping]:
    mappings = _mapping(root.get("mappings", {}), "mappings")
    _only(mappings, {"buttons"}, "mappings")
    data = _mapping(mappings.get("buttons", {}), "mappings.buttons")
    result: dict[str, ButtonMapping] = {}
    _only(data, {"left", "right"}, "mappings.buttons")
    for side in ("left", "right"):
        side_data = _mapping(data.get(side, {}), f"mappings.buttons.{side}")
        for control, value in side_data.items():
            path = f"mappings.buttons.{side}.{control}"
            if not isinstance(control, str) or control not in _BUTTONS_BY_SIDE[side]:
                raise ConfigError(f"{path}: controle JoyIO desconhecido para {side}")
            result[f"{side}.{control}"] = _button_mapping(value, path)
    return result


def load_config(path: str | Path) -> JoyIOConfig:
    """Load and fully validate a YAML configuration file."""

    config_path = Path(path)
    try:
        content = config_path.read_text(encoding="utf-8")
    except OSError as error:
        raise ConfigError(f"{config_path}: não foi possível ler: {error}") from error
    try:
        loaded = yaml.safe_load(content)
    except yaml.YAMLError as error:
        raise ConfigError(f"{config_path}: YAML inválido: {error}") from error
    root = _mapping(loaded, "config")
    _only(
        root,
        {
            "version",
            "devices",
            "reconnect",
            "runtime",
            "mouse",
            "scroll",
            "mappings",
        },
        "config",
    )
    if root.get("version") != 1 or isinstance(root.get("version"), bool):
        raise ConfigError("version: somente a versão 1 é suportada")
    return JoyIOConfig(
        version=1,
        device=_devices(root),
        reconnect=_reconnect(root),
        runtime=_runtime(root),
        mouse=_mouse(root),
        scroll=_scroll(root),
        buttons=_buttons(root),
    )
