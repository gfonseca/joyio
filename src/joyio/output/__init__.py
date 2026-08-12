"""Virtual and diagnostic output backends."""

from joyio.output.backends import DryRunOutput, OutputError, UInputOutput
from joyio.output.gamepad import GamepadError, VirtualGamepad

__all__ = [
    "DryRunOutput",
    "GamepadError",
    "OutputError",
    "UInputOutput",
    "VirtualGamepad",
]
