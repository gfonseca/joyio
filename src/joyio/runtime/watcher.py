"""inotify-based config file watcher for hot reload."""

from __future__ import annotations

import ctypes
import ctypes.util
import os
import pathlib


# inotify event masks from <linux/inotify.h>.
_IN_CLOSE_WRITE = 0x00000008
_IN_MODIFY = 0x00000002
_IN_ATTRIB = 0x00000004
_IN_MOVED_TO = 0x00000080
_IN_CREATE = 0x00000100

# Watching the *directory* (not the file itself) so that rename-based saves
# (vim, sed -i) don't orphan the watch onto a deleted inode.  Events are
# filtered to our filename in _matches_our_file().
_INOTIFY_FLAGS = (
    _IN_CLOSE_WRITE   # nano/gedit: file closed after write
    | _IN_MOVED_TO     # vim/sed -i: tempfile renamed over target
    | _IN_CREATE       # first-time creation of the config file
    | _IN_MODIFY       # catch truncate-and-write without close
    | _IN_ATTRIB       # metadata changes (harmless extra safety)
)
_DEBOUNCE_SECONDS = 0.5

_LIBC_NAME = ctypes.util.find_library("c")
if _LIBC_NAME is None:
    _LIBC: ctypes.CDLL | None = None
else:
    _LIBC = ctypes.CDLL(_LIBC_NAME, use_errno=True)
    _LIBC.inotify_init.restype = ctypes.c_int
    _LIBC.inotify_add_watch.argtypes = (
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint32,
    )
    _LIBC.inotify_add_watch.restype = ctypes.c_int


def _inotify_init() -> int:
    if _LIBC is None:
        return -1
    return _LIBC.inotify_init()


def _inotify_add_watch(fd: int, path: str, mask: int) -> int:
    if _LIBC is None:
        return -1
    return _LIBC.inotify_add_watch(fd, path.encode("utf-8"), ctypes.c_uint32(mask))


class ConfigWatcher:
    """Watches a single file for saves via Linux inotify.

    The inotify file descriptor is exposed so it can be added to the
    existing ``select()`` call in the event loop — no extra threads or
    polling overhead.

    Because editors write in different ways (vim renames a tempfile,
    nano / gEdit overwrite in-place), we include ``IN_ATTRIB`` alongside
    ``IN_CLOSE_WRITE``.  A short debounce suppresses double-fires from
    multi-step save sequences.
    """

    def __init__(self, config_path: str | pathlib.Path) -> None:
        self._path = pathlib.Path(config_path).resolve()
        self._filename = self._path.name
        self._fd: int = -1
        self._last_event = 0.0

        self._fd = _inotify_init()
        if self._fd < 0:
            raise OSError("inotify_init failed")

        # Watch the *directory*, not the file.  inotify watches inodes, and
        # editors like vim (and sed -i) save by renaming a tempfile over the
        # target — which replaces the inode.  A directory watch survives
        # renames because we filter by filename in each event.
        watch_target = str(self._path.parent)
        self._wd = _inotify_add_watch(self._fd, watch_target, _INOTIFY_FLAGS)
        if self._wd < 0:
            os.close(self._fd)
            self._fd = -1
            raise OSError(f"inotify_add_watch failed for {watch_target}")

    @property
    def fd(self) -> int:
        """The inotify file descriptor for integration with ``select()``."""
        return self._fd

    @property
    def path(self) -> str:
        """Absolute path to the watched config file."""
        return str(self._path)

    def consume(self) -> bool:
        """Read pending inotify events; return True if *our* file was touched.

        Call when ``fd`` is readable in ``select()``.  Returns True when the
        watched filename appears in the event stream (write, rename, attrib
        change).  The caller must still apply debounce — this only filters
        by filename.
        """
        try:
            data = os.read(self._fd, 4096)
        except OSError:
            return False
        if not data:
            return False
        return self._matches_our_file(data)

    def debounce(self, now: float) -> bool:
        """Return True when enough time has passed since the last accepted change."""
        if now - self._last_event < _DEBOUNCE_SECONDS:
            return False
        self._last_event = now
        return True

    def _matches_our_file(self, data: bytes) -> bool:
        """Scan raw inotify event data for our filename."""
        offset = 0
        while offset + 16 <= len(data):
            # struct inotify_event: wd(4) mask(4) cookie(4) len(4) name(len)
            wd = int.from_bytes(data[offset : offset + 4], "little")
            name_len = int.from_bytes(data[offset + 12 : offset + 16], "little")
            offset += 16
            if name_len > 0 and wd == self._wd:
                raw_name = data[offset : offset + name_len]
                name = raw_name.rstrip(b"\x00").decode("utf-8", errors="replace")
                if name == self._filename:
                    return True
            offset += name_len
        return False

    def close(self) -> None:
        if self._fd >= 0:
            try:
                os.close(self._fd)
            except OSError:
                pass
            self._fd = -1
