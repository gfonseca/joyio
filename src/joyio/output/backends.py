"""Backends for dry-run JSONL and Linux uinput."""

from __future__ import annotations

from contextlib import suppress
import sys
from typing import Iterable, Protocol, TextIO

from evdev import UInput, ecodes

from joyio.config.models import JoyIOConfig, KeyChordMapping, KeyMapping
from joyio.mapping.actions import (
    KeyAction,
    MouseButtonAction,
    MouseMoveAction,
    MouseScrollAction,
    OutputAction,
    action_json,
)


class OutputBackend(Protocol):
    def emit(self, actions: Iterable[OutputAction]) -> None: ...
    def release_all(self) -> None: ...
    def close(self) -> None: ...


class OutputError(RuntimeError):
    """The virtual output device could not be created or written."""


class DryRunOutput:
    def __init__(self, stream: TextIO | None = None) -> None:
        self.stream = stream or sys.stdout
        self._pressed_keys: set[str] = set()
        self._pressed_buttons: set[str] = set()

    def emit(self, actions: Iterable[OutputAction]) -> None:
        for action in actions:
            print(action_json(action), file=self.stream, flush=True)
            self._track(action)

    def release_all(self) -> None:
        actions: list[OutputAction] = [
            KeyAction(key, False) for key in sorted(self._pressed_keys)
        ]
        actions.extend(
            MouseButtonAction(button, False)
            for button in sorted(self._pressed_buttons)
        )
        self.emit(actions)

    def close(self) -> None:
        return None

    def _track(self, action: OutputAction) -> None:
        if isinstance(action, KeyAction):
            update = self._pressed_keys.add if action.pressed else self._pressed_keys.discard
            update(action.key)
        elif isinstance(action, MouseButtonAction):
            update = (
                self._pressed_buttons.add
                if action.pressed
                else self._pressed_buttons.discard
            )
            update(action.button)


class UInputOutput:
    _MOUSE_CODES = {
        "left": ecodes.BTN_LEFT,
        "middle": ecodes.BTN_MIDDLE,
        "right": ecodes.BTN_RIGHT,
    }

    def __init__(self, config: JoyIOConfig) -> None:
        keys: set[int] = set(self._MOUSE_CODES.values())
        for mapping in config.buttons.values():
            if isinstance(mapping, KeyMapping):
                keys.add(getattr(ecodes, mapping.key))
            elif isinstance(mapping, KeyChordMapping):
                keys.update(getattr(ecodes, key) for key in mapping.keys)
        capabilities = {
            ecodes.EV_KEY: sorted(keys),
            ecodes.EV_REL: [
                ecodes.REL_X,
                ecodes.REL_Y,
                ecodes.REL_HWHEEL,
                ecodes.REL_WHEEL,
            ],
        }
        try:
            self._device = UInput(capabilities, name="JoyIO Virtual Keyboard and Mouse")
        except (FileNotFoundError, PermissionError, OSError) as error:
            raise OutputError(f"não foi possível criar dispositivo uinput: {error}") from error
        self._pressed_keys: dict[int, int] = {}
        self._pressed_buttons: dict[int, int] = {}

    def emit(self, actions: Iterable[OutputAction]) -> None:
        try:
            for action in actions:
                if isinstance(action, KeyAction):
                    code = getattr(ecodes, action.key)
                    self._write_key(code, action.pressed, self._pressed_keys)
                elif isinstance(action, MouseButtonAction):
                    code = self._MOUSE_CODES[action.button]
                    self._write_key(code, action.pressed, self._pressed_buttons)
                elif isinstance(action, MouseMoveAction):
                    if action.dx:
                        self._device.write(ecodes.EV_REL, ecodes.REL_X, action.dx)
                    if action.dy:
                        self._device.write(ecodes.EV_REL, ecodes.REL_Y, action.dy)
                    self._device.syn()
                elif isinstance(action, MouseScrollAction):
                    if action.dx:
                        self._device.write(ecodes.EV_REL, ecodes.REL_HWHEEL, action.dx)
                    if action.dy:
                        self._device.write(ecodes.EV_REL, ecodes.REL_WHEEL, action.dy)
                    self._device.syn()
        except OSError as error:
            raise OutputError(f"falha ao escrever no dispositivo uinput: {error}") from error

    def release_all(self) -> None:
        try:
            pressed_codes = self._pressed_keys.keys() | self._pressed_buttons.keys()
            for code in sorted(pressed_codes):
                self._device.write(ecodes.EV_KEY, code, 0)
            if self._pressed_keys or self._pressed_buttons:
                self._device.syn()
            self._pressed_keys.clear()
            self._pressed_buttons.clear()
        except OSError as error:
            raise OutputError(f"falha ao liberar entradas no uinput: {error}") from error

    def close(self) -> None:
        with suppress(OSError):
            self._device.close()

    def _write_key(self, code: int, pressed: bool, state: dict[int, int]) -> None:
        if pressed:
            count = state.get(code, 0)
            state[code] = count + 1
            if count:
                return
        else:
            count = state.get(code, 0)
            if count > 1:
                state[code] = count - 1
                return
            if count == 0:
                return
            del state[code]
        self._device.write(ecodes.EV_KEY, code, int(pressed))
        self._device.syn()
