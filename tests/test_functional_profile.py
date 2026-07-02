"""Functional contract for the complete example profile.

This test intentionally crosses the config, mapping and dry-run output boundaries.
It exercises every configured button and both analog pipelines without Bluetooth or
real input devices.
"""

from __future__ import annotations

from io import StringIO
import json
from pathlib import Path

from joyio.config import load_config
from joyio.config.models import (
    BoostMapping,
    KeyChordMapping,
    KeyMapping,
    MouseButtonMapping,
    ToggleMapping,
)
from joyio.controls import BUTTON_CONTROLS
from joyio.events import NormalizedEvent
from joyio.mapping import MappingEngine
from joyio.mapping.actions import MouseMoveAction, MouseScrollAction, ToggleAction
from joyio.output import DryRunOutput


PROFILE = Path(__file__).parents[1] / "config.example.yaml"


def event(
    side: str,
    control: str,
    *,
    kind: str = "button",
    state: str | None = "pressed",
    value: float = 1.0,
) -> NormalizedEvent:
    return NormalizedEvent(
        kind=kind,
        control=control,
        source_control="functional-test",
        side=side,  # type: ignore[arg-type]
        code=0,
        value=value,
        state=state,
        timestamp=1.0,
    )


def test_complete_profile_maps_every_control_through_dry_run() -> None:
    config = load_config(PROFILE)
    engine = MappingEngine(config)
    stream = StringIO()
    output = DryRunOutput(stream)

    expected_controls = {
        f"{side}.{control}"
        for side, controls in BUTTON_CONTROLS.items()
        for control in controls.values()
    }
    assert set(config.buttons) == expected_controls

    for control_id, mapping in sorted(config.buttons.items()):
        side, control = control_id.split(".", maxsplit=1)
        pressed = engine.process(event(side, control))
        if isinstance(mapping, (ToggleMapping, BoostMapping)):
            assert pressed == []
            if isinstance(mapping, ToggleMapping):
                assert engine.process(
                    event(side, control, state="released", value=0.0)
                ) == []
                continue
            assert engine.process(
                event(side, control, state="released", value=0.0)
            ) == []
            continue
        assert pressed, f"{control_id} não produziu ação ao pressionar"
        if isinstance(mapping, ToggleMapping):
            assert pressed == [ToggleAction()]
            assert engine.set_enabled(False) == []
            assert engine.enabled is False
            assert (
                engine.process(
                    event(side, control, state="released", value=0.0)
                )
                == []
            )
            engine.set_enabled(True)
            continue
        output.emit(pressed)

        released = engine.process(
            event(side, control, state="released", value=0.0)
        )
        if mapping.mode == "hold":
            assert released, f"{control_id} não liberou a ação hold"
        else:
            assert released == []
        output.emit(released)

    assert config.mouse is not None
    assert config.scroll is not None
    mouse_side = config.mouse.stick.removesuffix("_stick")
    scroll_side = config.scroll.stick.removesuffix("_stick")
    engine.process(
        event(
            mouse_side,
            f"{config.mouse.stick}_x",
            kind="axis",
            state=None,
            value=1.0,
        )
    )
    engine.process(
        event(
            scroll_side,
            f"{config.scroll.stick}_x",
            kind="axis",
            state=None,
            value=1.0,
        )
    )
    assert engine.tick(0.0) == []
    horizontal_actions = engine.tick(0.1)
    assert any(
        isinstance(action, MouseMoveAction) and action.dx > 0
        for action in horizontal_actions
    )
    assert any(
        isinstance(action, MouseScrollAction) and action.dx > 0
        for action in horizontal_actions
    )
    output.emit(horizontal_actions)

    engine.process(
        event(
            mouse_side,
            f"{config.mouse.stick}_x",
            kind="axis",
            state=None,
            value=0.0,
        )
    )
    engine.process(
        event(
            scroll_side,
            f"{config.scroll.stick}_x",
            kind="axis",
            state=None,
            value=0.0,
        )
    )
    engine.process(
        event(
            scroll_side,
            f"{config.scroll.stick}_y",
            kind="axis",
            state=None,
            value=-1.0,
        )
    )
    vertical_actions = engine.tick(0.2)
    assert any(
        isinstance(action, MouseScrollAction) and action.dy > 0
        for action in vertical_actions
    )
    output.emit(vertical_actions)

    lines_before_release = stream.getvalue().splitlines()
    output.release_all()
    assert stream.getvalue().splitlines() == lines_before_release

    records = [json.loads(line) for line in lines_before_release]
    assert {record["type"] for record in records} == {
        "key",
        "mouse_button",
        "mouse_move",
        "mouse_scroll",
    }

    expected_keys: set[str] = set()
    expected_mouse_buttons: set[str] = set()
    for mapping in config.buttons.values():
        if isinstance(mapping, KeyMapping):
            expected_keys.add(mapping.key)
        elif isinstance(mapping, KeyChordMapping):
            expected_keys.update(mapping.keys)
        elif isinstance(mapping, MouseButtonMapping):
            expected_mouse_buttons.add(mapping.button)
    assert expected_keys <= {
        record["key"] for record in records if record["type"] == "key"
    }
    assert expected_mouse_buttons <= {
        record["button"]
        for record in records
        if record["type"] == "mouse_button"
    }
