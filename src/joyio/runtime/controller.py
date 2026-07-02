"""Orchestrate normalized input, mapping, and output lifecycle."""

from __future__ import annotations

import time
from typing import Callable

from collections.abc import Sequence

from joyio.devices import JoyConInput, read_runtime_events
from joyio.mapping.engine import MappingEngine
from joyio.output.backends import OutputBackend


def run_mapping(
    inputs: Sequence[JoyConInput],
    engine: MappingEngine,
    output: OutputBackend,
    *,
    clock: Callable[[], float] = time.monotonic,
) -> None:
    """Run until interrupted or disconnected, always releasing held outputs."""

    try:
        for event in read_runtime_events(inputs):
            if event is not None:
                output.emit(engine.process(event))
            output.emit(engine.tick(clock()))
    finally:
        try:
            output.release_all()
        finally:
            output.close()
            engine.reset()
