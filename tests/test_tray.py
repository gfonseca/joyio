from __future__ import annotations

from joyio import tray


def test_sni_properties_expose_pixmap_and_status() -> None:
    props = tray._sni_properties("JoyIO", "Active")
    paused = tray._sni_properties("JoyIO", "Passive")

    assert "IconName" not in props, "IconName removed — pixmap only"
    assert props["Status"] == ("s", "Active")
    assert paused["Status"] == ("s", "Passive")
    assert props["ItemIsMenu"] == ("b", False)
    assert props["Category"] == ("s", "ApplicationStatus")
    assert props["Id"] == ("s", "joyio")

    # IconPixmap: D-Bus signature and multiple sizes.
    assert props["IconPixmap"][0] == "a(iiay)"
    pixmaps = props["IconPixmap"][1]
    sizes = {(w, h) for w, h, _data in pixmaps}
    assert (24, 24) in sizes
    assert (32, 32) in sizes
    assert (48, 48) in sizes

    # Active and paused pixmaps differ (paused is desaturated).
    paused_pixmaps = paused["IconPixmap"][1]
    assert props["IconPixmap"][1] != paused_pixmaps

    # Verify ARGB pixel data has correct byte length.
    for w, h, data in pixmaps:
        assert len(data) == w * h * 4, f"{w}×{h} pixmap: expected {w*h*4} ARGB bytes"


def test_menu_layout_and_event_dispatch(monkeypatch) -> None:
    actions = []
    widget = tray.JoyIOTray("/tmp/joyio.yaml", on_action=actions.append)

    monkeypatch.setattr(tray, "new_method_return", lambda *args, **kwargs: "ok")
    monkeypatch.setattr(tray, "new_error", lambda *args, **kwargs: "error")
    monkeypatch.setattr(tray, "unwrap_msg", lambda msg: msg.body)

    reply = widget._menu_reply("GetLayout", object())
    assert reply == "ok"

    reply = widget._menu_reply("Event", type("Msg", (), {"body": (1, "clicked", None, 0)})())
    assert reply == "ok"
    assert actions == ["toggle"]


def test_activate_and_contextmenu_open_editor(monkeypatch) -> None:
    actions = []
    calls = []

    class ImmediateThread:
        def __init__(self, target, args=(), kwargs=None, **_ignored):
            self._target = target
            self._args = args
            self._kwargs = kwargs or {}

        def start(self) -> None:
            calls.append(("thread", self._args[0]))
            self._target(*self._args, **self._kwargs)

    monkeypatch.setattr(tray.threading, "Thread", ImmediateThread)
    monkeypatch.setattr(tray, "_open_editor", lambda config_path: calls.append(config_path))
    monkeypatch.setattr(tray, "new_method_return", lambda *args, **kwargs: "ok")
    monkeypatch.setattr(tray, "new_error", lambda *args, **kwargs: "error")

    widget = tray.JoyIOTray("/tmp/joyio.yaml", on_action=actions.append)
    assert widget._sni_reply("Activate", object()) == "ok"
    assert widget._sni_reply("SecondaryActivate", object()) == "ok"
    assert widget._sni_reply("ContextMenu", object()) == "ok"

    assert actions == ["toggle", "reload"]
    assert calls == [("thread", "/tmp/joyio.yaml"), "/tmp/joyio.yaml"]
