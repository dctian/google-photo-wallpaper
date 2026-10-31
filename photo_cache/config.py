from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class Config:
    cache_dir: Path
    profile_dir: Path
    albums: tuple[str, ...] = ()
    max_photos: int = 500
    max_bytes: int = 1024 * 1024 * 1024
    batch_size: int = 50
    max_width: int = 3840
    max_height: int = 2160
    jpeg_quality: int = 88
    max_download_bytes: int = 32 * 1024 * 1024
    max_image_bytes: int = 8 * 1024 * 1024
    browser_channel: str = "chrome"
    quality_filter: bool = True
    anniversary_fraction: float = 0.3
    anniversary_window_days: int = 7
    min_long_edge: int = 1600
    min_short_edge: int = 720
    windows_wallpaper: bool = False
    wallpaper_layout: str = "collage"
    wallpaper_interval_minutes: int = 10
    wallpaper_photos_per_image: int = 20


def default_data() -> dict:
    base = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / ".local" / "share"))) / "GooglePhotosWallpaper"
    return {
        "cache_dir": str(base / "cache"),
        "profile_dir": str(base / "browser"),
        "albums": [],
        "max_photos": 500,
        "max_bytes": 1024 * 1024 * 1024,
        "batch_size": 50,
        "max_width": 3840,
        "max_height": 2160,
        "jpeg_quality": 88,
        "max_download_bytes": 32 * 1024 * 1024,
        "max_image_bytes": 8 * 1024 * 1024,
        "browser_channel": "chrome",
        "quality_filter": True,
        "anniversary_fraction": 0.3,
        "anniversary_window_days": 7,
        "min_long_edge": 1600,
        "min_short_edge": 720,
        "windows_wallpaper": False,
        "wallpaper_layout": "collage",
        "wallpaper_interval_minutes": 10,
        "wallpaper_photos_per_image": 20,
    }


def load_config(path: Path) -> Config:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise ConfigError("Cannot read config. Run the init command first, or check its JSON syntax.") from exc
    if not isinstance(data, dict):
        raise ConfigError("Config must be a JSON object.")
    # Older installations may still have the retired score settings.
    data.pop("aesthetic_filter", None)
    data.pop("aesthetic_min_score", None)
    unknown = set(data) - set(default_data())
    if unknown:
        raise ConfigError("Config contains unsupported settings.")
    values = default_data() | data
    for name, minimum, maximum in (
        ("max_photos", 1, 10000), ("max_bytes", 32 * 1024 * 1024, 100 * 1024**3),
        ("batch_size", 1, 50), ("max_width", 320, 7680), ("max_height", 320, 7680),
        ("jpeg_quality", 50, 95), ("max_download_bytes", 1024 * 1024, 128 * 1024 * 1024),
        ("max_image_bytes", 256 * 1024, 32 * 1024 * 1024),
        ("anniversary_window_days", 0, 30), ("min_long_edge", 0, 7680), ("min_short_edge", 0, 7680),
        ("wallpaper_interval_minutes", 1, 1440),
        ("wallpaper_photos_per_image", 1, 100),
    ):
        value = values[name]
        if type(value) is not int or not minimum <= value <= maximum:
            raise ConfigError(f"Invalid numeric setting: {name}.")
    if values["max_image_bytes"] * 2 >= values["max_bytes"]:
        raise ConfigError("max_bytes must be more than twice max_image_bytes.")
    if type(values["quality_filter"]) is not bool:
        raise ConfigError("quality_filter must be true or false.")
    if type(values["windows_wallpaper"]) is not bool:
        raise ConfigError("windows_wallpaper must be true or false.")
    if values["wallpaper_layout"] not in ("single", "collage"):
        raise ConfigError("wallpaper_layout must be single or collage.")
    fraction = values["anniversary_fraction"]
    if type(fraction) not in (int, float) or not 0 <= fraction <= 1:
        raise ConfigError("anniversary_fraction must be between 0 and 1.")
    if values["browser_channel"] not in ("chrome", "msedge", "chromium"):
        raise ConfigError("browser_channel must be chrome, msedge, or chromium.")
    albums = values["albums"]
    if not isinstance(albums, list) or not all(isinstance(url, str) for url in albums):
        raise ConfigError("albums must be a list of private Google Photos album URLs.")
    for url in albums:
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname != "photos.google.com" or parsed.username or parsed.password or "/album/" not in parsed.path:
            raise ConfigError("Use normal https://photos.google.com/.../album/... URLs; sharing is unnecessary.")
    paths = {}
    for name in ("cache_dir", "profile_dir"):
        if not isinstance(values[name], str) or not values[name].strip():
            raise ConfigError(f"{name} must be a nonempty path.")
        raw = Path(os.path.expandvars(values[name])).expanduser()
        paths[name] = (path.parent / raw).absolute() if not raw.is_absolute() else raw.absolute()
    cache, profile = paths["cache_dir"].resolve(), paths["profile_dir"].resolve()
    if cache == profile or cache in profile.parents or profile in cache.parents:
        raise ConfigError("cache_dir and profile_dir must be separate folders, neither inside the other.")
    return Config(**(values | paths | {"albums": tuple(dict.fromkeys(albums))}))
