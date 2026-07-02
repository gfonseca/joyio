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
        self._pressed_keys: dict[str, int] = {}
        self._pressed_buttons: dict[str, int] = {}

    def emit(self, actions: Iterable[OutputAction]) -> None:
        for action in actions:
            if self._track(action):
                print(action_json(action), file=self.stream, flush=True)

    def release_all(self) -> None:
        actions: list[OutputAction] = [
            KeyAction(key, False) for key in sorted(self._pressed_keys)
        ]
        actions.extend(
            MouseButtonAction(button, False)
            for button in sorted(self._pressed_buttons)
        )
        # One virtual release is sufficient regardless of how many physical
        # mappings currently reference the same output.
        self._pressed_keys = {key: 1 for key in self._pressed_keys}
        self._pressed_buttons = {button: 1 for button in self._pressed_buttons}
        self.emit(actions)

    def close(self) -> None:
        return None

    def _track(self, action: OutputAction) -> bool:
        if isinstance(action, KeyAction):
            return self._update_count(self._pressed_keys, action.key, action.pressed)
        elif isinstance(action, MouseButtonAction):
            return self._update_count(
                self._pressed_buttons, action.button, action.pressed
            )
        return True

    @staticmethod
    def _update_count(state: dict[str, int], name: str, pressed: bool) -> bool:
        count = state.get(name, 0)
        if pressed:
            state[name] = count + 1
            return count == 0
        elif count > 1:
            state[name] = count - 1
            return False
        elif count:
            del state[name]
            return True
        return False


class UInputOutput:
    _MOUSE_CODES = {
        "left": ecodes.BTN_LEFT,
        "middle": ecodes.BTN_MIDDLE,
        "right": ecodes.BTN_RIGHT,
    }

    def __init__(self, config: JoyIOConfig) -> None:
        keys: set[int] = set(self._MOUSE_CODES.values())
        self._key_codes: dict[str, int] = {}
        for mapping in config.buttons.values():
            if isinstance(mapping, KeyMapping):
                code = getattr(ecodes, mapping.key)
                keys.add(code)
                self._key_codes[mapping.key] = code
            elif isinstance(mapping, KeyChordMapping):
                for key in mapping.keys:
                    code = getattr(ecodes, key)
                    keys.add(code)
                    self._key_codes[key] = code
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
            self._device = UInput(
                capabilities,
                name="JoyIO Virtual Keyboard and Mouse",
                max_effects=0,
            )
        except (FileNotFoundError, PermissionError, OSError) as error:
            raise OutputError(f"não foi possível criar dispositivo uinput: {error}") from error
        self._pressed_keys: dict[int, int] = {}
        self._pressed_buttons: dict[int, int] = {}

    def emit(self, actions: Iterable[OutputAction]) -> None:
        try:
            relative_pending = False
            for action in actions:
                if isinstance(action, KeyAction):
                    if relative_pending:
                        self._device.syn()
                        relative_pending = False
                    code = self._key_codes[action.key]
                    self._write_key(code, action.pressed, self._pressed_keys)
                elif isinstance(action, MouseButtonAction):
                    if relative_pending:
                        self._device.syn()
                        relative_pending = False
                    code = self._MOUSE_CODES[action.button]
                    self._write_key(code, action.pressed, self._pressed_buttons)
                elif isinstance(action, MouseMoveAction):
                    if action.dx:
                        self._device.write(ecodes.EV_REL, ecodes.REL_X, action.dx)
                        relative_pending = True
                    if action.dy:
                        self._device.write(ecodes.EV_REL, ecodes.REL_Y, action.dy)
                        relative_pending = True
                elif isinstance(action, MouseScrollAction):
                    if action.dx:
                        self._device.write(ecodes.EV_REL, ecodes.REL_HWHEEL, action.dx)
                        relative_pending = True
                    if action.dy:
                        self._device.write(ecodes.EV_REL, ecodes.REL_WHEEL, action.dy)
                        relative_pending = True
            if relative_pending:
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
