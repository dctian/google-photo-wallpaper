"""Windows tray lifecycle isolated from Tk; callbacks only enqueue commands."""

from __future__ import annotations

import threading
from typing import Callable


def _create_icon(post: Callable[[str], None]):
    import pystray
    from PIL import Image, ImageDraw

    image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((4, 7, 60, 57), radius=10, fill="#2878cc")
    draw.rounded_rectangle((11, 14, 53, 50), radius=4, fill="#edf6ff")
    draw.ellipse((36, 20, 45, 29), fill="#f4b942")
    draw.polygon(((13, 45), (26, 29), (35, 39), (41, 33), (51, 45)), fill="#328f65")
    return pystray.Icon(
        "google_photos_wallpaper", image, "Google Photos Wallpaper",
        menu=pystray.Menu(
            pystray.MenuItem("Show app", lambda _icon, _item: post("tray_show"), default=True),
            pystray.MenuItem("Refresh wallpaper", lambda _icon, _item: post("tray_refresh")),
            pystray.MenuItem("Open wallpaper folder", lambda _icon, _item: post("tray_folder")),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Exit app", lambda _icon, _item: post("tray_exit")),
        ),
    )


class TrayIcon:
    """Start once, report readiness, and remove the icon when the app exits.

    Windows permits pystray's event loop on a worker thread. Both that worker
    and its setup thread are daemons, so a failed backend cannot keep Python
    alive after the app exits. No method or callback calls Tk directly.
    """

    def __init__(self, post: Callable[[str], None], factory: Callable = _create_icon):
        self._post = post
        self._factory = factory
        self._lock = threading.RLock()
        self._icon = None
        self._thread = None
        self._ready = False
        self._closed = False

    def _emit(self, event: str) -> None:
        with self._lock:
            if not self._closed:
                self._post(event)

    def show(self) -> None:
        """Emit tray_ready only after Windows has accepted a visible icon."""
        with self._lock:
            if self._closed:
                return
            if self._ready:
                self._emit("tray_ready")
                return
            if self._icon is not None:
                return
            try:
                icon = self._factory(self._emit)
            except Exception:
                self._emit("tray_error")
                return
            self._icon = icon
            self._thread = threading.Thread(target=self._run, args=(icon,),
                                            name="photo-wallpaper-tray", daemon=True)
            self._thread.start()

    def _run(self, icon) -> None:
        unexpected_stop = False
        try:
            with self._lock:
                if self._closed:
                    return
            icon.run(setup=self._on_ready)
            unexpected_stop = True
        except Exception:
            unexpected_stop = True
        finally:
            with self._lock:
                if self._icon is icon:
                    self._icon = None
                    self._ready = False
                if unexpected_stop and not self._closed:
                    self._emit("tray_error")

    def _on_ready(self, icon) -> None:
        try:
            with self._lock:
                if self._closed:
                    icon.stop()
                    return
                icon.visible = True
                self._ready = True
                self._emit("tray_ready")
        except Exception:
            self._emit("tray_error")
            icon.stop()

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            icon = self._icon
            self._ready = False
        if icon is not None:
            try:
                icon.stop()
            except Exception:
                pass
