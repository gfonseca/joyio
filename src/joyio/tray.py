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

import importlib.resources
import os
import subprocess
import sys
import threading
import traceback
from typing import Callable

from PIL import Image

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

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sni_properties(title: str, status: str) -> dict:
    """Build a dict of SNI properties as (signature, value) pairs.

    Ships an ``IconPixmap`` loaded from a PNG so the icon renders at a
    readable size regardless of the system icon theme.
    """
    return {
        "Category": ("s", "ApplicationStatus"),
        "Id": ("s", "joyio"),
        "Title": ("s", title),
        "Status": ("s", status),
        "WindowId": ("u", 0),
        "IconPixmap": ("a(iiay)", _controller_pixmaps(status == "Active")),
        "ItemIsMenu": ("b", False),
        "Menu": ("o", MENU_PATH),
    }


def _controller_pixmaps(active: bool) -> list[tuple[int, int, bytes]]:
    """Return a list of (width, height, argb-bytes) pixmaps.

    Pixels are in **ARGB32 network byte order** (A, R, G, B per pixel),
    matching the D-Bus ``a(iiay)`` wire format expected by
    StatusNotifierItem hosts (KDE, GNOME AppIndicator, …).

    The source PNG (32×32 RGBA) is resized to multiple dimensions so
    the host can pick the best fit.
    """
    img = _load_icon(active)
    pixmaps: list[tuple[int, int, bytes]] = []
    for size in (24, 32, 48):
        resized = img.resize((size, size), Image.LANCZOS)
        pixmaps.append((size, size, _rgba_to_argb(resized)))
    return pixmaps


def _load_icon(active: bool) -> Image.Image:
    """Load the bundled controller icon for the given state."""
    name = "joycon-icon.png" if active else "joycon-icon-d.png"
    path = importlib.resources.files("joyio.icons") / name
    with path.open("rb") as fh:
        return Image.open(fh).convert("RGBA")


def _rgba_to_argb(img: Image.Image) -> bytes:
    """Convert Pillow RGBA to ARGB32 byte string (D-Bus wire format)."""
    r, g, b, a = img.split()
    return Image.merge("RGBA", (a, r, g, b)).tobytes()


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
                status="Active",
            )
        else:
            self._update(
                title="JoyIO — mapeamento desligado",
                status="Passive",
            )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _update(
        self,
        *,
        title: str | None = None,
        status: str | None = None,
    ) -> None:
        props_changed: dict[str, tuple[str, object]] = {}
        with self._lock:
            if title is not None:
                self._title = title
            if status is not None:
                old_status = self._status
                self._status = status
                if status != old_status:
                    props_changed["IconPixmap"] = (
                        "a(iiay)",
                        _controller_pixmaps(status == "Active"),
                    )
                    props_changed["Status"] = ("s", status)
        conn = self._conn
        if conn is not None:
            try:
                from jeepney import new_signal

                conn.send(new_signal(
                    DBusAddress(SNI_PATH, interface=SNI_IFACE), "NewIcon",
                ))
                conn.send(new_signal(
                    DBusAddress(SNI_PATH, interface=SNI_IFACE), "NewStatus",
                ))
                conn.send(new_signal(
                    DBusAddress(MENU_PATH, interface=MENU_IFACE), "LayoutUpdated",
                ))
                if props_changed:
                    conn.send(new_signal(
                        DBusAddress(SNI_PATH, interface=PROP_IFACE),
                        "PropertiesChanged",
                        "sa{sv}as",
                        (SNI_IFACE, list(props_changed.items()), []),
                    ))
            except Exception:
                pass

    @property
    def _props(self) -> dict:
        with self._lock:
            return _sni_properties(self._title, self._status)

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

        reply: object = None
        try:
            if iface == PROP_IFACE and path == SNI_PATH:
                reply = self._prop_reply(member, msg)
            elif iface == SNI_IFACE and path == SNI_PATH:
                reply = self._sni_reply(member, msg)
            elif iface == PROP_IFACE and path == MENU_PATH:
                reply = self._menu_prop_reply(member, msg)
            elif iface == MENU_IFACE and path == MENU_PATH:
                reply = self._menu_reply(member, msg)
            elif iface == "org.freedesktop.DBus.Introspectable" and member == "Introspect":
                # Let the D-Bus daemon handle introspection — we don't
                # need to reply ourselves.  Returning without sending
                # anything is the correct behaviour for an SNI item.
                return
            elif iface == "" and member == "":
                return  # silently ignore empty messages
            else:
                reply = new_error(msg, "org.freedesktop.DBus.Error.UnknownMethod",
                                  f"{iface}.{member}")
        except Exception as exc:
            try:
                reply = new_error(msg, "org.freedesktop.DBus.Error.Failed", str(exc))
            except Exception:
                return

        if reply is not None:
            try:
                conn.send(reply)
            except Exception:
                pass  # best-effort — don't kill the loop over a bad reply

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
