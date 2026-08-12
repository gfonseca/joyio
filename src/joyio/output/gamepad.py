"""Linux uinput virtual gamepad that combines two Joy-Cons into one device."""

from __future__ import annotations

from contextlib import suppress

from evdev import AbsInfo, UInput, ecodes

from joyio.controls import JoyConSide


class GamepadError(RuntimeError):
    """The virtual gamepad device could not be created or written."""


# ── uinput capabilities for a standard dual-stick gamepad ──────────────

_GAMEPAD_KEYS = (
    ecodes.BTN_SOUTH,   # A
    ecodes.BTN_EAST,    # B
    ecodes.BTN_NORTH,   # X
    ecodes.BTN_WEST,    # Y
    ecodes.BTN_TL,      # L
    ecodes.BTN_TR,      # R
    ecodes.BTN_TL2,     # ZL
    ecodes.BTN_TR2,     # ZR
    ecodes.BTN_SELECT,  # minus
    ecodes.BTN_START,   # plus
    ecodes.BTN_THUMBL,  # left stick press
    ecodes.BTN_THUMBR,  # right stick press
    ecodes.BTN_MODE,    # home
    ecodes.BTN_Z,       # capture (extra)
)

_STICK_INFO = AbsInfo(
    value=0, min=-32768, max=32767, fuzz=0, flat=128, resolution=0,
)

_HAT_INFO = AbsInfo(
    value=0, min=-1, max=1, fuzz=0, flat=0, resolution=0,
)

_GAMEPAD_AXES: tuple[tuple[int, AbsInfo], ...] = (
    (ecodes.ABS_X, _STICK_INFO),
    (ecodes.ABS_Y, _STICK_INFO),
    (ecodes.ABS_RX, _STICK_INFO),
    (ecodes.ABS_RY, _STICK_INFO),
    (ecodes.ABS_HAT0X, _HAT_INFO),
    (ecodes.ABS_HAT0Y, _HAT_INFO),
)

_GAMEPAD_CAPABILITIES: dict[int, list] = {
    ecodes.EV_KEY: list(_GAMEPAD_KEYS),
    ecodes.EV_ABS: [(code, info) for code, info in _GAMEPAD_AXES],
}

# ── JoyIO canonical control → gamepad evdev code ────────────────────────

_AXIS_MAP: dict[tuple[JoyConSide, str], int] = {
    ("left", "left_stick_x"): ecodes.ABS_X,
    ("left", "left_stick_y"): ecodes.ABS_Y,
    ("right", "right_stick_x"): ecodes.ABS_RX,
    ("right", "right_stick_y"): ecodes.ABS_RY,
}

_BUTTON_MAP: dict[tuple[JoyConSide, str], int] = {
    # Left Joy-Con
    ("left", "dpad_up"): ecodes.BTN_DPAD_UP,
    ("left", "dpad_down"): ecodes.BTN_DPAD_DOWN,
    ("left", "dpad_left"): ecodes.BTN_DPAD_LEFT,
    ("left", "dpad_right"): ecodes.BTN_DPAD_RIGHT,
    ("left", "l"): ecodes.BTN_TL,
    ("left", "zl"): ecodes.BTN_TL2,
    ("left", "minus"): ecodes.BTN_SELECT,
    ("left", "left_stick_press"): ecodes.BTN_THUMBL,
    ("left", "capture"): ecodes.BTN_Z,
    ("left", "sl"): ecodes.BTN_TR,    # rail SL
    ("left", "sr"): ecodes.BTN_TR2,   # rail SR
    # Right Joy-Con
    ("right", "a"): ecodes.BTN_SOUTH,
    ("right", "b"): ecodes.BTN_EAST,
    ("right", "x"): ecodes.BTN_NORTH,
    ("right", "y"): ecodes.BTN_WEST,
    ("right", "r"): ecodes.BTN_TR,
    ("right", "zr"): ecodes.BTN_TR2,
    ("right", "plus"): ecodes.BTN_START,
    ("right", "right_stick_press"): ecodes.BTN_THUMBR,
    ("right", "home"): ecodes.BTN_MODE,
    ("right", "sl"): ecodes.BTN_TL,   # rail SL
    ("right", "sr"): ecodes.BTN_TL2,  # rail SR
}

# D-pad: each direction maps to a HAT axis value.
_DPAD_HAT: dict[str, tuple[int, int]] = {
    "dpad_up": (ecodes.ABS_HAT0Y, -1),
    "dpad_down": (ecodes.ABS_HAT0Y, 1),
    "dpad_left": (ecodes.ABS_HAT0X, -1),
    "dpad_right": (ecodes.ABS_HAT0X, 1),
}


def _button_code(side: JoyConSide, control: str) -> int | None:
    """Return the gamepad button code for a JoyIO canonical control, or None."""
    return _BUTTON_MAP.get((side, control))


def _axis_code(side: JoyConSide, control: str) -> int | None:
    """Return the gamepad axis code for a JoyIO stick axis, or None."""
    return _AXIS_MAP.get((side, control))


def _dpad_hat(control: str) -> tuple[int, int] | None:
    """Return (axis_code, value) for a dpad direction, or None."""
    return _DPAD_HAT.get(control)


class VirtualGamepad:
    """uinput device combining two Joy-Cons into a single virtual gamepad.

    Usage::

        gp = VirtualGamepad()
        # Left stick
        gp.emit_axis(ecodes.ABS_X, 16000)   # right
        gp.emit_axis(ecodes.ABS_Y, -8000)   # up
        # Right stick
        gp.emit_axis(ecodes.ABS_RX, -12000) # left
        # Button
        gp.emit_button(ecodes.BTN_SOUTH, True)  # A pressed
        gp.emit_button(ecodes.BTN_SOUTH, False) # A released
        gp.close()

    Convenience methods accept JoyIO canonical control names::

        gp.emit_joyio_button("left", "l", True)
        gp.emit_joyio_button("right", "a", False)
        gp.emit_joyio_axis("left", "left_stick_x", 0.5)
    """

    def __init__(self) -> None:
        try:
            # Identifica-se como Nintendo Switch Pro Controller para que
            # SDL2/RetroArch/Steam reconheçam o layout de botões (A/B/X/Y)
            # automaticamente via controller database.
            self._device = UInput(
                _GAMEPAD_CAPABILITIES,
                name="JoyIO Virtual Gamepad",
                vendor=0x057E,   # Nintendo
                product=0x2009,  # Switch Pro Controller
                version=0x0001,
                bustype=ecodes.BUS_USB,
                max_effects=0,
            )
        except (FileNotFoundError, PermissionError, OSError) as error:
            raise GamepadError(
                f"não foi possível criar gamepad virtual: {error}"
            ) from error

        # Track dpad state so releasing one direction doesn't zero the axis
        # while another direction is still held.
        self._dpad_state: dict[int, int] = {
            ecodes.ABS_HAT0X: 0,
            ecodes.ABS_HAT0Y: 0,
        }
        self._dpad_held: dict[str, bool] = {
            "dpad_up": False,
            "dpad_down": False,
            "dpad_left": False,
            "dpad_right": False,
        }
        self._pressed_buttons: dict[int, int] = {}

    # ── low-level emit ─────────────────────────────────────────────

    def emit_button(self, code: int, pressed: bool) -> None:
        """Write a button event directly to the virtual device."""
        if pressed:
            count = self._pressed_buttons.get(code, 0)
            self._pressed_buttons[code] = count + 1
            if count:
                return
        else:
            count = self._pressed_buttons.get(code, 0)
            if count > 1:
                self._pressed_buttons[code] = count - 1
                return
            if count == 0:
                return
            del self._pressed_buttons[code]
        self._write_key(code, pressed)

    def emit_axis(self, code: int, value: int) -> None:
        """Write an absolute axis event directly to the virtual device."""
        self._device.write(ecodes.EV_ABS, code, value)
        self._device.syn()

    # ── JoyIO convenience methods ──────────────────────────────────

    def emit_joyio_button(
        self, side: JoyConSide, control: str, pressed: bool
    ) -> None:
        """Translate a JoyIO canonical button to the gamepad and emit.

        Returns True when the control was recognized and emitted.
        """
        # D-pad is mapped to HAT axes, not buttons.
        dpad = _dpad_hat(control)
        if dpad is not None:
            self._emit_dpad(control, dpad, pressed)
            return

        code = _button_code(side, control)
        if code is not None:
            self.emit_button(code, pressed)

    def emit_joyio_axis(
        self, side: JoyConSide, control: str, value: float
    ) -> None:
        """Translate a JoyIO normalized axis (-1..1) to gamepad integer value.

        Returns True when the control was recognized and emitted.
        """
        code = _axis_code(side, control)
        if code is not None:
            int_value = int(value * 32767)
            self.emit_axis(code, int_value)

    # ── lifecycle ──────────────────────────────────────────────────

    def close(self) -> None:
        """Close the virtual gamepad device and release all inputs."""
        try:
            for code in sorted(self._pressed_buttons):
                self._device.write(ecodes.EV_KEY, code, 0)
            if self._pressed_buttons:
                self._device.syn()
            self._pressed_buttons.clear()
            # Reset axes to center.
            for code, _info in _GAMEPAD_AXES:
                self._device.write(ecodes.EV_ABS, code, 0)
            self._device.syn()
        except OSError:
            pass
        finally:
            with suppress(OSError):
                self._device.close()

    # ── helpers ────────────────────────────────────────────────────

    def _write_key(self, code: int, pressed: bool) -> None:
        self._device.write(ecodes.EV_KEY, code, int(pressed))
        self._device.syn()

    def _emit_dpad(
        self, direction: str, hat: tuple[int, int], pressed: bool
    ) -> None:
        axis, pressed_value = hat
        self._dpad_held[direction] = pressed

        # Compute the resulting axis value from all held directions.
        value = 0
        if self._dpad_held["dpad_left"]:
            value = -1
        elif self._dpad_held["dpad_right"]:
            value = 1
        if self._dpad_held["dpad_up"]:
            value = -1 if axis == ecodes.ABS_HAT0Y else value
        elif self._dpad_held["dpad_down"]:
            value = 1 if axis == ecodes.ABS_HAT0Y else value

        if axis == ecodes.ABS_HAT0X:
            if not any((self._dpad_held["dpad_left"], self._dpad_held["dpad_right"])):
                value = 0
        else:
            if not any((self._dpad_held["dpad_up"], self._dpad_held["dpad_down"])):
                value = 0

        if self._dpad_state[axis] != value:
            self._dpad_state[axis] = value
            self.emit_axis(axis, value)

    def __repr__(self) -> str:
        return f"<VirtualGamepad buttons={len(self._pressed_buttons)}>"
