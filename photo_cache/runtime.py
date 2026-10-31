"""Paths and child commands for source checkouts and installed Windows builds."""
from __future__ import annotations

import os
from pathlib import Path
import sys


def frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def data_dir() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", str(Path.home()/".local"/"share"))) / "GooglePhotosWallpaper"


def application_dir() -> Path:
    return Path(sys.executable).resolve().parent if frozen() else Path(__file__).resolve().parent.parent


def resource_dir() -> Path:
    return Path(sys._MEIPASS) if frozen() else application_dir()


def default_config_path() -> Path:
    return (data_dir() if frozen() else application_dir()) / "config.json"


def command(arguments: list[str], python: str | None = None) -> list[str]:
    if frozen():
        return [str(application_dir()/"GooglePhotoWallpaper-cli.exe"), *arguments]
    executable = Path(python or sys.executable)
    if os.name == "nt" and executable.name.lower() == "pythonw.exe":
        executable = executable.with_name("python.exe")
    return [str(executable), "-m", "photo_cache", *arguments]
