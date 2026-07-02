from __future__ import annotations

from joyio.config.models import (
    JoyIOConfig,
    KeyChordMapping,
    KeyMapping,
    MouseButtonMapping,
    MouseConfig,
    ScrollConfig,
)
from joyio.events import NormalizedEvent
from joyio.mapping.actions import (
    KeyAction,
    MouseButtonAction,
    MouseMoveAction,
    MouseScrollAction,
)
from joyio.mapping.engine import MappingEngine


def event(
    control: str,
    state: str,
    *,
    side: str = "right",
    kind: str = "button",
    value: float = 1.0,
) -> NormalizedEvent:
    return NormalizedEvent(
        kind=kind,
        control=control,
        source_control="test",
        side=side,
        code=0,
        value=value,
        state=state if kind == "button" else None,
        timestamp=1.0,
    )


def test_hold_key_preserves_press_and_release() -> None:
    engine = MappingEngine(
        JoyIOConfig(version=1, buttons={"right.a": KeyMapping("KEY_A", "hold")})
    )

    assert engine.process(event("a", "pressed")) == [KeyAction("KEY_A", True)]
    assert engine.process(event("a", "pressed")) == []
    assert engine.process(event("a", "released", value=0.0)) == [KeyAction("KEY_A", False)]


def test_tap_ignores_physical_release() -> None:
    engine = MappingEngine(
        JoyIOConfig(
            version=1, buttons={"right.a": MouseButtonMapping("left", "tap")}
        )
    )

    assert engine.process(event("a", "pressed")) == [
        MouseButtonAction("left", True),
        MouseButtonAction("left", False),
    ]
    assert engine.process(event("a", "released", value=0.0)) == []


def test_chord_releases_in_reverse_order() -> None:
    mapping = KeyChordMapping(("KEY_LEFTCTRL", "KEY_C"), "hold")
    engine = MappingEngine(JoyIOConfig(version=1, buttons={"right.x": mapping}))

    assert engine.process(event("x", "pressed")) == [
        KeyAction("KEY_LEFTCTRL", True),
        KeyAction("KEY_C", True),
    ]
    assert engine.process(event("x", "released")) == [
        KeyAction("KEY_C", False),
        KeyAction("KEY_LEFTCTRL", False),
    ]


def test_same_named_rail_buttons_are_independent_between_sides() -> None:
    engine = MappingEngine(
        JoyIOConfig(
            version=1,
            buttons={
                "left.sl": KeyMapping("KEY_Q", "hold"),
                "right.sl": KeyMapping("KEY_E", "hold"),
            },
        )
    )

    assert engine.process(event("sl", "pressed", side="left")) == [
        KeyAction("KEY_Q", True)
    ]
    assert engine.process(event("sl", "pressed", side="right")) == [
        KeyAction("KEY_E", True)
    ]
    assert engine.process(event("sl", "released", side="left")) == [
        KeyAction("KEY_Q", False)
    ]


def test_mouse_uses_dead_zone_and_elapsed_time() -> None:
    mouse = MouseConfig(
        stick="right_stick",
        dead_zone=0.1,
        sensitivity=100.0,
        acceleration=1.0,
        max_speed=100.0,
        invert_x=False,
        invert_y=False,
    )
    engine = MappingEngine(JoyIOConfig(version=1, mouse=mouse))
    engine.process(event("right_stick_x", "", kind="axis", value=0.05))
    assert engine.tick(10.0) == []
    assert engine.tick(10.1) == []

    engine.process(event("right_stick_x", "", kind="axis", value=1.0))
    assert engine.tick(10.15) == [MouseMoveAction(5, 0)]


def test_mouse_caps_late_tick_and_preserves_fractional_residue() -> None:
    mouse = MouseConfig(
        stick="right_stick",
        dead_zone=0.0,
        sensitivity=15.0,
        acceleration=1.0,
        max_speed=15.0,
        invert_x=False,
        invert_y=False,
    )
    engine = MappingEngine(JoyIOConfig(version=1, mouse=mouse))
    engine.process(event("right_stick_x", "", kind="axis", value=1.0))
    engine.tick(1.0)

    assert engine.tick(1.05) == []
    assert engine.tick(1.10) == [MouseMoveAction(1, 0)]
    assert engine.tick(5.0) == [MouseMoveAction(2, 0)]


def test_mouse_and_scroll_use_different_sticks_simultaneously() -> None:
    mouse = MouseConfig(
        stick="left_stick",
        dead_zone=0.0,
        sensitivity=100.0,
        acceleration=1.0,
        max_speed=100.0,
        invert_x=False,
        invert_y=False,
    )
    scroll = ScrollConfig(
        stick="right_stick",
        dead_zone=0.0,
        sensitivity=20.0,
        acceleration=1.0,
        max_speed=20.0,
        invert_x=False,
        invert_y=False,
    )
    engine = MappingEngine(JoyIOConfig(version=1, mouse=mouse, scroll=scroll))
    engine.process(
        event("left_stick_x", "", side="left", kind="axis", value=1.0)
    )
    engine.process(event("right_stick_y", "", kind="axis", value=1.0))

    assert engine.tick(0.0) == []
    assert engine.tick(0.05) == [
        MouseMoveAction(5, 0),
        MouseScrollAction(0, 1),
    ]
