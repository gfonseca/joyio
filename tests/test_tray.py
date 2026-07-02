from __future__ import annotations

from joyio import tray


def test_sni_properties_expose_theme_icon_and_status() -> None:
    props = tray._sni_properties("JoyIO", tray.ICON_ACTIVE, "Active")
    paused = tray._sni_properties("JoyIO", tray.ICON_DISABLED, "Passive")

    assert props["IconName"] == ("s", tray.ICON_ACTIVE)
    assert props["Status"] == ("s", "Active")
    assert props["ItemIsMenu"] == ("b", False)
    assert props["IconPixmap"][0] == "a(iiay)"
    assert len(props["IconPixmap"][1]) == 1
    assert props["IconPixmap"][1] != paused["IconPixmap"][1]


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
