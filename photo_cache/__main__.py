from __future__ import annotations

import argparse
import hashlib
import json
import sys
import subprocess
from datetime import datetime
from pathlib import Path
from . import __version__

from .cache import Cache, CacheError, file_lock, now, safe_path
from .config import ConfigError, default_data, load_config
from .source import GooglePhotosSource, SourceError, LoginRequired, login


def config_fingerprint(config) -> str:
    values = {name: str(value) if isinstance(value, Path) else value for name, value in vars(config).items()}
    return hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()


def cache_lock_path(config) -> Path:
    # A separate cache lock also protects configurations using different
    # browser profiles but the same wallpaper destination.
    return config.cache_dir.parent / f".{config.cache_dir.name}.lock"


def _refresh_wallpapers(config) -> None:
    if config.windows_wallpaper:
        from .wallpapers import generate_wallpapers
        from .windows_wallpaper import WallpaperError
        try:
            generate_wallpapers(config, apply=True)
        except (WallpaperError, OSError, CacheError):
            # Photo downloads can succeed independently of Windows desktop policy.
            print("Photos were retained, but the wallpaper update failed. Try Use wallpaper rotation in the app.")


def show_status(config, require_ready: bool, require_schedulable: bool = False) -> int:
    """Inspect actual cache files without repairing or deleting anything."""
    safe_path(config.cache_dir)
    state_path = config.cache_dir / "state.json"
    safe_path(state_path)
    if not state_path.is_file():
        print("No successful refresh yet. Choose albums in the app, then Refresh now.")
        return 1 if require_ready or require_schedulable else 0
    state = json.loads(state_path.read_text(encoding="utf-8"))
    cache = Cache(config)
    cache.state = state
    cache._validate_state()
    marker = config.cache_dir / ".owner"
    pending = config.cache_dir / "pending.jpg"
    for path in (marker, pending, cache.photos):
        safe_path(path)
    files = list(cache.photos.iterdir()) if cache.photos.is_dir() else []
    for path in files:
        safe_path(path)
    sizes = {path.name: path.stat().st_size for path in files if path.is_file()}
    expected = {f"{key}.jpg" for key in state["items"]}
    intact = (bool(expected) and set(sizes) == expected and len(files) == len(sizes)
              and all(0 < size <= config.max_image_bytes for size in sizes.values()))
    total_bytes = sum(sizes.values()) + (pending.stat().st_size if pending.is_file() else 0)
    within_limits = len(files) <= config.max_photos and total_bytes <= config.max_bytes
    owned = marker.is_file() and marker.read_text(encoding="utf-8") == Cache.MARKER
    try:
        last_success = datetime.fromisoformat(state.get("last_success") or "")
        last_attempt = datetime.fromisoformat(state.get("last_attempt") or "")
        completed = last_attempt <= last_success
    except (TypeError, ValueError):
        completed = False
    print(f"Wallpapers: {len(files)} | {total_bytes / 1024**2:.1f} MiB")
    print(f"Folder for JBS: {cache.photos}")
    print(f"Last successful refresh: {state.get('last_success') or 'none'}")
    if state.get("last_error"):
        print(f"Last refresh issue: {state['last_error']}")
    ready = (owned and intact and within_limits and completed and not pending.exists()
             and not state.get("last_error")
             and state.get("config_fingerprint") == config_fingerprint(config))
    if require_schedulable:
        # Scheduling resumes existing, locally verified work. It does not
        # manufacture a successful refresh or make an authentication request.
        from .source import _PROFILE_MARKER
        profile_marker = config.profile_dir / _PROFILE_MARKER
        safe_path(profile_marker)
        schedulable = (owned and intact and within_limits and not pending.exists()
                       and bool(config.albums) and profile_marker.is_file())
        if schedulable:
            print("Scheduling preflight passed: the retained collection can resume on schedule. Google sign-in was not rechecked.")
        else:
            print("Scheduling requires selected albums, a dedicated browser profile, and an intact owned cache within the current limits.")
        return 0 if schedulable else 1
    if require_ready and not ready:
        print("A successful refresh with the current settings and an intact cache is required.")
    return 0 if not require_ready or ready else 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Private Google Photos albums to a bounded local wallpaper collection")
    parser.add_argument("--version", action="version", version="google-photo-wallpaper " + __version__)
    parser.add_argument("--config", type=Path, default=Path(__file__).resolve().parent.parent / "config.json")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init", help="Create a private local configuration")
    commands.add_parser("gui", help="Open the desktop album selector")
    commands.add_parser("login", help="Sign in once in the dedicated browser")
    commands.add_parser("albums", help="List private albums by title")
    commands.add_parser("refresh", help="Download one new batch")
    commands.add_parser("wallpaper-next", help="Apply the next local collage to all monitors")
    wallpaper_parser = commands.add_parser("wallpapers", help="Generate wallpapers from local photos")
    wallpaper_parser.add_argument("--enable", action="store_true", help="Enable synchronized wallpaper rotation on all monitors")
    status_parser = commands.add_parser("status", help="Show local cache status")
    status_checks = status_parser.add_mutually_exclusive_group()
    status_checks.add_argument("--require-ready", action="store_true")
    status_checks.add_argument("--require-schedulable", action="store_true")
    args = parser.parse_args(argv)
    config_path = args.config.absolute()
    try:
        if args.command == "init":
            config_path.parent.mkdir(parents=True, exist_ok=True)
            with config_path.open("x", encoding="utf-8") as handle:
                json.dump(default_data(), handle, indent=2)
                handle.write("\n")
            print(f"Created {config_path}. Open the gui to sign in and choose albums.")
            return 0
        if args.command == "gui":
            if not config_path.exists():
                config_path.parent.mkdir(parents=True, exist_ok=True)
                config_path.write_text(json.dumps(default_data(), indent=2) + "\n", encoding="utf-8")
            from .gui import launch
            launch(config_path)
            return 0
        config = load_config(config_path)
        if args.command == "wallpaper-next":
            from .wallpapers import rotate_wallpaper
            from .windows_wallpaper import WallpaperError
            try:
                with file_lock(cache_lock_path(config)):
                    rotate_wallpaper(config)
                return 0
            except WallpaperError as exc:
                print(str(exc), file=sys.stderr)
                return 1
        if args.command == "wallpapers":
            from .wallpapers import generate_wallpapers
            from .windows_wallpaper import WallpaperError
            try:
                with file_lock(config.profile_dir.parent / "operation.lock"), file_lock(cache_lock_path(config)):
                    generate_wallpapers(config, apply=args.enable)
                    if args.enable:
                        from .gui import _write_config
                        data = json.loads(config_path.read_text(encoding="utf-8-sig"))
                        data["windows_wallpaper"] = True
                        _write_config(config_path, data)
                if args.enable:
                    script = Path(__file__).resolve().parent.parent / "scripts" / "Install-WallpaperTask.ps1"
                    task = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                        "-File", str(script), "-ConfigPath", str(config_path)],
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                        creationflags=subprocess.CREATE_NO_WINDOW)
                    if task.returncode:
                        print("Wallpaper applied, but automatic rotation could not be installed. Run scripts/Install-WallpaperTask.ps1.", file=sys.stderr)
                        return 1
                    print(task.stdout.strip())
                return 0
            except WallpaperError as exc:
                print(str(exc), file=sys.stderr)
                return 1
        with file_lock(config.profile_dir.parent / "operation.lock"):
            if args.command == "login":
                print("Sign in to Google in the separate Chrome window. Once your Photos library appears, close that browser window to let the app verify the saved session.", flush=True)
                login(config.profile_dir, browser_channel=config.browser_channel)
                print("Sign-in saved. Open the app and load your albums.")
                return 0
            if args.command == "status":
                # Read-only: task installation must not alter or repair a cache.
                with file_lock(cache_lock_path(config)):
                    return show_status(config, args.require_ready, args.require_schedulable)
            if args.command == "refresh" and not config.albums:
                raise ConfigError("Open the app and choose one or more albums first.")
            if args.command == "albums":
                with GooglePhotosSource(config.profile_dir, max_width=config.max_width,
                                        max_height=config.max_height, browser_channel=config.browser_channel) as source:
                    for index, album in enumerate(source.list_albums(), 1):
                        print(f"{index}. {album.title} ({album.item_count} items)")
                    return 0
            with file_lock(cache_lock_path(config)):
                cache = Cache(config)
                cache.open()
                if cache.quota_status().remaining == 0:
                    result = cache.deferred_result(lambda message: print(message, flush=True))
                    print(f"Available: {result.photos} wallpapers ({result.bytes / 1024**2:.1f} MiB); no photos requested.")
                    print(f"JBS folder: {cache.photos}")
                    _refresh_wallpapers(config)
                    return 0
                cache.state["last_attempt"] = now()
                cache.state["last_error"] = None
                cache.save()
                try:
                    with GooglePhotosSource(config.profile_dir, max_width=config.max_width,
                                            max_height=config.max_height, browser_channel=config.browser_channel) as source:
                        print("Reading selected albums...", flush=True)
                        photos = source.list_photos(list(config.albums))
                        limit = min(config.batch_size, cache.quota_status().remaining, 50)
                        print(f"Found {len(photos)} still photos. Trying up to {limit} photos within the shared hourly allowance...", flush=True)

                        def authenticated_download(photo, settings):
                            try:
                                return source.download_photo(photo, settings)
                            except LoginRequired:
                                # Stop promptly if the session expires mid-refresh.
                                raise
                            except SourceError as exc:
                                raise CacheError(str(exc)) from None

                        # The newer Google image host requires the same live
                        # authenticated browser context as album enumeration.
                        result = cache.refresh(photos, fetch=authenticated_download,
                                               report=lambda message: print(message, flush=True))
                    cache.state["config_fingerprint"] = config_fingerprint(config)
                    cache.save()
                except Exception as exc:
                    cache.state["last_error"] = (str(exc) if isinstance(exc, (CacheError, SourceError))
                                                 else f"Refresh failed ({type(exc).__name__}). Check setup, disk space, and write access.")
                    try:
                        cache.save()
                    except OSError:
                        pass
                    _refresh_wallpapers(config)
                    raise
                print(f"Available: {result.photos} wallpapers ({result.bytes / 1024**2:.1f} MiB); {result.downloaded} added.")
                print(f"JBS folder: {cache.photos}")
                if cache.state.get("last_error"):
                    print(cache.state["last_error"])
                _refresh_wallpapers(config)
                return 0 if result.deferred else (2 if result.failed or cache.state.get("last_error") else 0)
    except FileExistsError:
        print("Configuration already exists; it was left unchanged.", file=sys.stderr)
        return 1
    except (ConfigError, CacheError, SourceError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Stopped. Existing wallpapers remain available.", file=sys.stderr)
        return 130
    except Exception as exc:
        # Never print arbitrary exception bodies; third-party errors can contain session URLs.
        print(f"Operation failed ({type(exc).__name__}). Check setup, disk space, and write access; no Google photos were changed.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
