from __future__ import annotations

from joyio.config.models import (
    BoostMapping,
    JoyIOConfig,
    KeyChordMapping,
    KeyMapping,
    MouseButtonMapping,
    MouseConfig,
    ScrollConfig,
    ToggleMapping,
)
from joyio.events import NormalizedEvent
from joyio.mapping.actions import (
    KeyAction,
    MouseButtonAction,
    MouseMoveAction,
    MouseScrollAction,
    ToggleAction,
)
from joyio.mapping import engine as engine_module
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


def test_boost_amplifies_mouse_only_while_held() -> None:
    mouse = MouseConfig(
        stick="left_stick",
        dead_zone=0.0,
        sensitivity=10.0,
        acceleration=1.0,
        max_speed=100.0,
        invert_x=False,
        invert_y=False,
    )
    base_engine = MappingEngine(
        JoyIOConfig(
            version=1,
            mouse=mouse,
        )
    )
    boosted_engine = MappingEngine(
        JoyIOConfig(
            version=1,
            mouse=mouse,
            buttons={"left.minus": BoostMapping(2.5)},
        )
    )

    base_engine.process(event("left_stick_x", "", side="left", kind="axis", value=1.0))
    base_engine.tick(0.0)
    assert base_engine.tick(0.1) == [MouseMoveAction(1, 0)]

    boosted_engine.process(
        event("left_stick_x", "", side="left", kind="axis", value=1.0)
    )
    boosted_engine.tick(0.0)
    assert boosted_engine.process(event("minus", "pressed", side="left")) == []
    assert boosted_engine.tick(0.1) == [MouseMoveAction(2, 0)]

    assert boosted_engine.process(event("minus", "released", side="left", value=0.0)) == []
    assert boosted_engine.tick(0.2) == [MouseMoveAction(1, 0)]
    assert boosted_engine.tick(0.3) == [MouseMoveAction(1, 0)]


def test_boost_is_cleared_when_side_disconnects() -> None:
    mouse = MouseConfig(
        stick="left_stick",
        dead_zone=0.0,
        sensitivity=10.0,
        acceleration=1.0,
        max_speed=100.0,
        invert_x=False,
        invert_y=False,
    )
    engine = MappingEngine(
        JoyIOConfig(
            version=1,
            mouse=mouse,
            buttons={"left.minus": BoostMapping(2.5)},
        )
    )

    engine.process(event("left_stick_x", "", side="left", kind="axis", value=1.0))
    engine.process(event("minus", "pressed", side="left"))
    engine.tick(0.0)
    assert engine.tick(0.1) == [MouseMoveAction(2, 0)]

    assert engine.release_side("left") == []
    assert engine.tick(0.2) == []


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


def test_analog_curve_is_recomputed_only_when_axis_changes(monkeypatch) -> None:
    calls = 0
    original_hypot = engine_module.math.hypot

    def counting_hypot(x, y):
        nonlocal calls
        calls += 1
        return original_hypot(x, y)

    monkeypatch.setattr(engine_module.math, "hypot", counting_hypot)
    engine = MappingEngine(
        JoyIOConfig(
            version=1,
            mouse=MouseConfig(stick="left_stick"),
        )
    )
    axis = event("left_stick_x", "", side="left", kind="axis", value=0.5)

    engine.process(axis)
    for tick in range(100):
        engine.tick(tick / 120.0)
    engine.process(axis)

    assert calls == 1


def test_release_side_releases_only_its_holds_and_stops_its_stick() -> None:
    engine = MappingEngine(
        JoyIOConfig(
            version=1,
            mouse=MouseConfig(
                stick="left_stick",
                dead_zone=0.0,
                sensitivity=100.0,
                acceleration=1.0,
                max_speed=100.0,
                invert_x=False,
                invert_y=False,
            ),
            buttons={
                "left.l": KeyMapping("KEY_A", "hold"),
                "right.r": KeyMapping("KEY_B", "hold"),
            },
        )
    )
    engine.process(event("l", "pressed", side="left"))
    engine.process(event("r", "pressed", side="right"))
    engine.process(event("left_stick_x", "", side="left", kind="axis", value=1.0))
    engine.tick(1.0)

    assert engine.release_side("left") == [KeyAction("KEY_A", False)]
    assert engine.tick(1.1) == []
    assert engine.process(event("r", "released", side="right")) == [
        KeyAction("KEY_B", False)
    ]


def test_toggle_mode_disables_and_reenables_output() -> None:
    engine = MappingEngine(
        JoyIOConfig(
            version=1,
            buttons={
                "left.capture": ToggleMapping(),
                "right.a": KeyMapping("KEY_A", "hold"),
            },
        )
    )

    assert engine.enabled is True
    assert engine.process(event("capture", "pressed", side="left")) == [
        ToggleAction()
    ]
    assert engine.enabled is True

    assert engine.set_enabled(False) == []
    assert engine.enabled is False
    assert (
        engine.process(
            event("a", "pressed", side="right")
        )
        == []
    )
    assert engine.process(event("a", "released", side="right", value=0.0)) == []
    assert engine.process(event("capture", "released", side="left")) == []
    assert engine.process(event("capture", "pressed", side="left")) == [
        ToggleAction()
    ]
    assert engine.set_enabled(True) == []
    assert engine.enabled is True
    assert engine.process(event("a", "pressed")) == [KeyAction("KEY_A", True)]
