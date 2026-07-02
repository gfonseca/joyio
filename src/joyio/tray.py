"""StatusNotifierItem tray icon via D-Bus (jeepney, zero system deps).

Runs on a daemon thread alongside the evdev loop. The tray exposes
click actions for the common runtime controls:

- primary click toggles mapping on/off;
- secondary click reloads the current configuration;
- context-menu click opens the config editor.

On Wayland/GNOME the icon appears in the top bar when a
StatusNotifierItem-compatible extension (e.g. AppIndicator) is installed.
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import traceback
from typing import Callable

from jeepney import (
    DBusAddress,
    HeaderFields,
    MatchRule,
    new_error,
    new_method_call,
    new_method_return,
)
from jeepney.io.blocking import open_dbus_connection
from jeepney.wrappers import unwrap_msg

# ---------------------------------------------------------------------------
# D-Bus addresses & constants
# ---------------------------------------------------------------------------

BUS_DAEMON = DBusAddress(
    "/org/freedesktop/DBus",
    bus_name="org.freedesktop.DBus",
    interface="org.freedesktop.DBus",
)
SNI_WATCHER = DBusAddress(
    "/StatusNotifierWatcher",
    bus_name="org.kde.StatusNotifierWatcher",
    interface="org.kde.StatusNotifierWatcher",
)

PROP_IFACE = "org.freedesktop.DBus.Properties"
SNI_IFACE = "org.kde.StatusNotifierItem"
SNI_PATH = "/StatusNotifierItem"
MENU_IFACE = "com.canonical.dbusmenu"
MENU_PATH = "/MenuBar"
BUS_NAME = "org.joyio.tray"

# Theme icons for a controller item in active/passive states.
ICON_ACTIVE = "input-gaming"
ICON_DISABLED = "input-gaming-symbolic"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sni_properties(title: str, icon_name: str, status: str) -> dict:
    """Build a dict of SNI properties as (signature, value) pairs."""
    return {
        "Category": ("s", "ApplicationStatus"),
        "Id": ("s", "joyio"),
        "Title": ("s", title),
        "Status": ("s", status),
        "WindowId": ("u", 0),
        "IconName": ("s", icon_name),
        "IconPixmap": ("a(iiay)", _controller_pixmaps(status == "Active")),
        "ItemIsMenu": ("b", False),
        "Menu": ("o", MENU_PATH),
    }


def _controller_pixmaps(active: bool) -> list[tuple[int, int, bytes]]:
    size = 22
    pixels = bytearray(size * size * 4)
    if active:
        body = (56, 168, 96, 255)
        edge = (28, 84, 48, 255)
        buttons = (236, 252, 238, 255)
        dpad = (18, 64, 34, 255)
    else:
        body = (166, 166, 166, 255)
        edge = (116, 116, 116, 255)
        buttons = (214, 214, 214, 255)
        dpad = (92, 92, 92, 255)

    def put(x: int, y: int, rgba: tuple[int, int, int, int]) -> None:
        idx = (y * size + x) * 4
        pixels[idx : idx + 4] = bytes(rgba)

    def inside_body(x: int, y: int) -> bool:
        return 4 <= x <= 17 and 7 <= y <= 14

    for y in range(size):
        for x in range(size):
            if inside_body(x, y):
                put(x, y, body)

    # Simple controller silhouette.
    for x in range(5, 17):
        put(x, 7, edge)
        put(x, 14, edge)
    for y in range(8, 14):
        put(4, y, edge)
        put(17, y, edge)

    for x in range(7, 9):
        for y in range(9, 11):
            put(x, y, dpad)
    for x in range(12, 14):
        for y in range(9, 11):
            put(x, y, buttons)
    for x in range(10, 12):
        for y in range(8, 10):
            put(x, y, buttons)

    if not active:
        for x in range(8, 10):
            for y in range(8, 13):
                put(x, y, (76, 76, 76, 255))
        for x in range(12, 14):
            for y in range(8, 13):
                put(x, y, (76, 76, 76, 255))

    return [(size, size, bytes(pixels))]


def _open_editor(config_path: str) -> None:
    editor = os.environ.get("EDITOR", os.environ.get("VISUAL", "gnome-text-editor"))
    subprocess.Popen([editor, config_path], start_new_session=True)


# ---------------------------------------------------------------------------
# Tray controller
# ---------------------------------------------------------------------------


class JoyIOTray:
    """StatusNotifierItem tray icon for JoyIO."""

    def __init__(
        self,
        config_path: str,
        *,
        on_action: Callable[[str], None] | None = None,
    ) -> None:
        self._config_path = config_path
        self._on_action = on_action
        self._conn = None
        self._running = False
        self._thread = None
        self._lock = threading.Lock()
        self._title = "JoyIO"
        self._icon_name = ICON_ACTIVE
        self._status = "Active"
        self._revision = 1

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="joyio-tray"
        )
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        conn = self._conn
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=1.0)

    def set_mapping_enabled(self, enabled: bool) -> None:
        if enabled:
            self._update(
                title="JoyIO — mapeamento ativo",
                icon_name=ICON_ACTIVE,
                status="Active",
            )
        else:
            self._update(
                title="JoyIO — mapeamento desligado",
                icon_name=ICON_DISABLED,
                status="Passive",
            )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _update(
        self,
        *,
        title: str | None = None,
        icon_name: str | None = None,
        status: str | None = None,
    ) -> None:
        with self._lock:
            if title is not None:
                self._title = title
            if icon_name is not None:
                self._icon_name = icon_name
            if status is not None:
                self._status = status
        # Emit NewIcon so the host re-reads IconPixmap & Title.
        conn = self._conn
        if conn is not None:
            try:
                from jeepney import new_signal

                conn.send(new_signal(SNI_PATH, SNI_IFACE, "NewIcon"))
                conn.send(new_signal(SNI_PATH, SNI_IFACE, "NewStatus"))
                conn.send(new_signal(MENU_PATH, MENU_IFACE, "LayoutUpdated"))
            except Exception:
                pass

    @property
    def _props(self) -> dict:
        with self._lock:
            return _sni_properties(self._title, self._icon_name, self._status)

    # ------------------------------------------------------------------
    # D-Bus loop
    # ------------------------------------------------------------------

    def _run(self) -> None:
        log = lambda msg: print(f"  tray: {msg}", file=sys.stderr)

        try:
            self._conn = open_dbus_connection(bus="SESSION")
        except Exception as exc:
            log(f"D-Bus connection failed — {exc}")
            return

        conn = self._conn

        # Claim well-known name.
        try:
            reply = conn.send_and_get_reply(
                new_method_call(BUS_DAEMON, "RequestName", "su", (BUS_NAME, 0x04)),
                timeout=2.0,
            )
            result = unwrap_msg(reply)
            # result[0]: 1=primary owner, 2=queued, 3=exists, 4=already owner
            status_codes = {1: "PRIMARY_OWNER", 2: "IN_QUEUE", 3: "EXISTS", 4: "ALREADY_OWNER"}
            status = status_codes.get(result[0], f"UNKNOWN({result[0]})")
            if result[0] in (1, 4):
                log(f"D-Bus name {BUS_NAME} registered ({status}) on {conn.unique_name}")
            else:
                log(f"D-Bus name {BUS_NAME} NOT granted: {status}")
                return
        except Exception as exc:
            log(f"RequestName failed — {exc}")
            return

        # Register with StatusNotifierWatcher.
        conn.send(new_method_call(SNI_WATCHER, "RegisterStatusNotifierItem", "s", (BUS_NAME,)))

        log("tray icon started — look at the GNOME top bar")

        sni_rule = MatchRule(type="method_call", path=SNI_PATH)
        menu_rule = MatchRule(type="method_call", path=MENU_PATH)
        with conn.filter(sni_rule) as sni_queue, conn.filter(menu_rule) as menu_queue:
            try:
                while self._running:
                    try:
                        msg = conn.recv_until_filtered(sni_queue, timeout=0.1)
                        self._dispatch(conn, msg)
                    except TimeoutError:
                        try:
                            msg = conn.recv_until_filtered(menu_queue, timeout=0.1)
                            self._dispatch(conn, msg)
                        except TimeoutError:
                            pass  # just a sleep interval between checks
            except Exception as exc:
                if self._running:
                    log(f"loop error — {exc}\n{traceback.format_exc()}")
            finally:
                try:
                    conn.send(new_method_call(
                        BUS_DAEMON, "ReleaseName", "s", (BUS_NAME,)
                    ))
                except Exception:
                    pass

    def _dispatch(self, conn, msg) -> None:
        iface = msg.header.fields.get(HeaderFields.interface, "")
        member = msg.header.fields.get(HeaderFields.member, "")
        path = msg.header.fields.get(HeaderFields.path, "")
        print(
            f"  tray: recv iface={iface!r} member={member!r} path={path!r} body={unwrap_msg(msg)!r}",
            file=sys.stderr,
        )

        try:
            if iface == PROP_IFACE and path == SNI_PATH:
                reply = self._prop_reply(member, msg)
            elif iface == SNI_IFACE and path == SNI_PATH:
                reply = self._sni_reply(member, msg)
            elif iface == PROP_IFACE and path == MENU_PATH:
                reply = self._menu_prop_reply(member, msg)
            elif iface == MENU_IFACE and path == MENU_PATH:
                reply = self._menu_reply(member, msg)
            else:
                reply = new_error(msg, "org.freedesktop.DBus.Error.UnknownMethod",
                                  f"{iface}.{member}")
        except Exception as exc:
            reply = new_error(msg, "org.freedesktop.DBus.Error.Failed", str(exc))

        if reply is not None:
            conn.send(reply)

    def _prop_reply(self, member: str, msg) -> object:
        if member == "GetAll":
            iface_name = unwrap_msg(msg)[0]
            if iface_name == SNI_IFACE:
                # a{sv} expects list of (key, (sig, value)) tuples.
                props_list = list(self._props.items())
                return new_method_return(msg, "a{sv}", (props_list,))
        elif member == "Get":
            body = unwrap_msg(msg)
            iface_name, prop_name = body[0], body[1]
            if iface_name == SNI_IFACE:
                value = self._props.get(prop_name)
                if value is not None:
                    sig, val = value
                    return new_method_return(msg, "v", ((sig, val),))
        return new_error(msg, "org.freedesktop.DBus.Error.UnknownProperty",
                         "Unknown property")

    def _sni_reply(self, member: str, msg) -> object:
        if member == "Activate":
            self._emit_action("toggle")
            return new_method_return(msg, "", ())
        if member == "SecondaryActivate":
            self._emit_action("reload")
            return new_method_return(msg, "", ())
        if member == "ContextMenu":
            threading.Thread(target=_open_editor, args=(self._config_path,)).start()
            return new_method_return(msg, "", ())
        return new_error(msg, "org.freedesktop.DBus.Error.UnknownMethod",
                         f"SNI.{member}")

    def _menu_prop_reply(self, member: str, msg) -> object:
        props = {
            "Version": ("u", 3),
            "TextDirection": ("s", "ltr"),
            "Status": ("s", "normal"),
        }
        if member == "GetAll":
            iface_name = unwrap_msg(msg)[0]
            if iface_name == MENU_IFACE:
                return new_method_return(msg, "a{sv}", (list(props.items()),))
        elif member == "Get":
            body = unwrap_msg(msg)
            iface_name, prop_name = body[0], body[1]
            if iface_name == MENU_IFACE:
                value = props.get(prop_name)
                if value is not None:
                    sig, val = value
                    return new_method_return(msg, "v", ((sig, val),))
        return new_error(msg, "org.freedesktop.DBus.Error.UnknownProperty",
                         "Unknown property")

    def _menu_reply(self, member: str, msg) -> object:
        if member == "GetLayout":
            # (parent_id, recursion_depth, property_names)
            layout = self._menu_layout()
            return new_method_return(msg, "u(ia{sv}av)", (self._revision, layout))
        if member == "GetGroupProperties":
            body = unwrap_msg(msg)
            ids = body[0] if body else ()
            props = self._menu_group_properties(ids)
            return new_method_return(msg, "a(ia{sv})", (props,))
        if member == "GetProperty":
            body = unwrap_msg(msg)
            item_id = body[0]
            prop_name = body[1]
            value = self._menu_property_for(item_id, prop_name)
            if value is not None:
                sig, val = value
                return new_method_return(msg, "v", ((sig, val),))
            return new_error(msg, "org.freedesktop.DBus.Error.UnknownProperty",
                             "Unknown property")
        if member == "AboutToShow":
            return new_method_return(msg, "b", (False,))
        if member == "AboutToShowGroup":
            return new_method_return(msg, "ai", ([],))
        if member == "Event":
            body = unwrap_msg(msg)
            item_id = body[0]
            event_id = body[1]
            if event_id == "clicked":
                self._emit_menu_action(item_id)
                return new_method_return(msg, "i", (1,))
            return new_method_return(msg, "i", (0,))
        return new_error(msg, "org.freedesktop.DBus.Error.UnknownMethod",
                         f"Menu.{member}")

    def _menu_layout(self) -> tuple[int, list[tuple[str, tuple[str, object]]], list[tuple]]:
        title = "Desativar mapeamento" if self._status == "Active" else "Ativar mapeamento"
        children = [
            self._menu_item(1, title),
            self._menu_item(2, "Recarregar configuração"),
            self._menu_item(3, "Abrir configuração"),
            self._menu_item(4, "Sair"),
        ]
        return 0, [], children

    def _menu_group_properties(
        self, ids: object
    ) -> list[tuple[int, list[tuple[str, tuple[str, object]]]]]:
        requested = {int(item) for item in ids} if ids else {1, 2, 3, 4}
        result = []
        for item_id, label in (
            (1, "Desativar mapeamento" if self._status == "Active" else "Ativar mapeamento"),
            (2, "Recarregar configuração"),
            (3, "Abrir configuração"),
            (4, "Sair"),
        ):
            if item_id in requested:
                result.append((item_id, [("label", ("s", label)), ("enabled", ("b", True)), ("visible", ("b", True))]))
        return result

    def _menu_property_for(self, item_id: int, prop_name: str) -> tuple[str, object] | None:
        labels = {
            1: "Desativar mapeamento" if self._status == "Active" else "Ativar mapeamento",
            2: "Recarregar configuração",
            3: "Abrir configuração",
            4: "Sair",
        }
        if prop_name == "label" and item_id in labels:
            return "s", labels[item_id]
        if prop_name in {"enabled", "visible"} and item_id in labels:
            return "b", True
        return None

    @staticmethod
    def _menu_item(
        item_id: int, label: str
    ) -> tuple[int, list[tuple[str, tuple[str, object]]], list[tuple]]:
        props = [
            ("label", ("s", label)),
            ("enabled", ("b", True)),
            ("visible", ("b", True)),
        ]
        return ("(ia{sv}av)", (item_id, props, []))

    def _emit_menu_action(self, item_id: int) -> None:
        if item_id == 1:
            self._emit_action("toggle")
        elif item_id == 2:
            self._emit_action("reload")
        elif item_id == 3:
            threading.Thread(target=_open_editor, args=(self._config_path,)).start()
        elif item_id == 4:
            self._emit_action("quit")

    def _emit_action(self, action: str) -> None:
        if self._on_action is None:
            return
        try:
            self._on_action(action)
        except Exception:
            pass
