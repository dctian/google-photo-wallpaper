"""Documented Windows desktop slideshow API; no registry hacks or extra package."""
from __future__ import annotations

import ctypes as ct
from contextlib import contextmanager
import os
from pathlib import Path
import uuid


class WallpaperError(RuntimeError):
    pass


class GUID(ct.Structure):
    _fields_ = [("data", ct.c_ubyte * 16)]

    def __init__(self, value):
        super().__init__()
        self.data[:] = uuid.UUID(value).bytes_le


def _check(result):
    if result < 0:
        raise WallpaperError(f"Windows wallpaper operation failed (0x{result & 0xffffffff:08X}).")


def _call(pointer, slot, argtypes, *args):
    table = ct.cast(pointer, ct.POINTER(ct.POINTER(ct.c_void_p))).contents
    method = ct.WINFUNCTYPE(ct.c_long, ct.c_void_p, *argtypes)(table[slot])
    result = method(pointer, *args)
    _check(result)


def _release(pointer):
    if pointer.value:
        table = ct.cast(pointer, ct.POINTER(ct.POINTER(ct.c_void_p))).contents
        ct.WINFUNCTYPE(ct.c_ulong, ct.c_void_p)(table[2])(pointer)


@contextmanager
def _desktop():
    if os.name != "nt":
        raise WallpaperError("Native desktop slideshows require Windows 10 or 11.")
    ole = ct.WinDLL("ole32")
    ole.CoInitializeEx.argtypes = [ct.c_void_p, ct.c_ulong]
    initialized = ole.CoInitializeEx(None, 2)
    _check(initialized)
    pointer = ct.c_void_p()
    try:
        ole.CoCreateInstance.argtypes = [ct.POINTER(GUID), ct.c_void_p, ct.c_ulong, ct.POINTER(GUID), ct.POINTER(ct.c_void_p)]
        _check(ole.CoCreateInstance(ct.byref(GUID("C2CF3110-460E-4FC1-B9D0-8A1C0C9CC4BD")),
                                   None, 23, ct.byref(GUID("B92B56A9-8B55-4E14-9A89-0199BBB6F93B")), ct.byref(pointer)))
        yield pointer
    finally:
        _release(pointer)
        ole.CoUninitialize()


def slideshow_options() -> tuple[bool, int]:
    """Read-back for verification without changing the desktop."""
    with _desktop() as desktop:
        shuffle, tick = ct.c_uint(), ct.c_uint()
        _call(desktop, 15, [ct.POINTER(ct.c_uint), ct.POINTER(ct.c_uint)], ct.byref(shuffle), ct.byref(tick))
        return bool(shuffle.value & 1), tick.value


def set_wallpaper_all(path: Path) -> None:
    if not path.is_file():
        raise WallpaperError("The generated wallpaper image was not found.")
    with _desktop() as desktop:
        _call(desktop, 10, [ct.c_uint], 3)  # Fit, never span.
        _call(desktop, 3, [ct.c_wchar_p, ct.c_wchar_p], None, str(path.absolute()))


def monitor_wallpapers() -> tuple[list[str], int, int]:
    """Read back each monitor's wallpaper path, slideshow flags, and fit mode."""
    with _desktop() as desktop:
        count, status, position = ct.c_uint(), ct.c_uint(), ct.c_uint()
        _call(desktop, 6, [ct.POINTER(ct.c_uint)], ct.byref(count))
        _call(desktop, 17, [ct.POINTER(ct.c_uint)], ct.byref(status))
        _call(desktop, 11, [ct.POINTER(ct.c_uint)], ct.byref(position))
        ole = ct.WinDLL("ole32")
        ole.CoTaskMemFree.argtypes = [ct.c_void_p]
        paths = []
        for index in range(count.value):
            monitor, path = ct.c_void_p(), ct.c_void_p()
            try:
                _call(desktop, 5, [ct.c_uint, ct.POINTER(ct.c_void_p)], index, ct.byref(monitor))
                _call(desktop, 4, [ct.c_wchar_p, ct.POINTER(ct.c_void_p)], ct.wstring_at(monitor), ct.byref(path))
                paths.append(ct.wstring_at(path) if path.value else "")
            finally:
                ole.CoTaskMemFree(monitor)
                ole.CoTaskMemFree(path)
        return paths, status.value, position.value


def enable_slideshow(folder: Path, minutes: int = 10) -> None:
    if not folder.is_dir() or not any(folder.glob("*.jpg")) or not 1 <= minutes <= 1440:
        raise WallpaperError("Prepare wallpaper images and choose an interval between 1 and 1440 minutes.")
    with _desktop() as desktop:
        shell = ct.WinDLL("shell32")
        item, array = ct.c_void_p(), ct.c_void_p()
        try:
            shell.SHCreateItemFromParsingName.argtypes = [ct.c_wchar_p, ct.c_void_p, ct.POINTER(GUID), ct.POINTER(ct.c_void_p)]
            shell.SHCreateShellItemArrayFromShellItem.argtypes = [ct.c_void_p, ct.POINTER(GUID), ct.POINTER(ct.c_void_p)]
            _check(shell.SHCreateItemFromParsingName(str(folder.absolute()), None,
                ct.byref(GUID("43826D1E-E718-42EE-BC55-A1E261C37BFE")), ct.byref(item)))
            _check(shell.SHCreateShellItemArrayFromShellItem(item,
                ct.byref(GUID("B63EA76D-1F85-456F-A19C-48159EFA858B")), ct.byref(array)))
            # Slots follow IDesktopWallpaper's order in the Windows SDK header.
            _call(desktop, 14, [ct.c_uint, ct.c_uint], 1, minutes * 60_000)
            _call(desktop, 10, [ct.c_uint], 3)  # DWPOS_FIT also preserves framing on smaller monitors.
            _call(desktop, 18, [ct.c_int], 1)  # Enable
            _call(desktop, 12, [ct.c_void_p], array)  # Select new folder last.
        finally:
            _release(array)
            _release(item)


def screen_size() -> tuple[int, int]:
    if os.name == "nt":
        # Get physical primary-screen pixels, independent of Tk's DPI scaling.
        user = ct.WinDLL("user32")
        context = user.SetThreadDpiAwarenessContext
        context.argtypes = [ct.c_void_p]
        context.restype = ct.c_void_p
        previous = context(ct.c_void_p(-4))
        try:
            return max(320, user.GetSystemMetrics(0)), max(320, user.GetSystemMetrics(1))
        finally:
            if previous:
                context(previous)
    return 1920, 1080
