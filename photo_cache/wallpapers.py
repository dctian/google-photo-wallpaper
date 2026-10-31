"""Compose a bounded set of wallpapers from the owned local photo cache."""
from __future__ import annotations

import json
import hashlib
import io
from pathlib import Path
import random
import re
import shutil
import uuid

from PIL import Image, ImageOps

from .cache import Cache, safe_path
from .windows_wallpaper import WallpaperError, set_wallpaper_all, screen_size

MARKER = "GooglePhotosWallpaper generated wallpapers v1\n"
GENERATION = re.compile(r"generation-[a-f0-9]{32}")
MAX_GENERATION_BYTES = 32 * 1024 * 1024


def wallpaper_dir(config) -> Path:
    """Keep the standard cache's existing location; isolate sibling caches."""
    cache = config.cache_dir
    if cache.name.casefold() == "cache":
        return cache.parent / "wallpapers"
    suffix = hashlib.sha256(cache.name.casefold().encode("utf-8")).hexdigest()[:20]
    return cache.parent / ("wallpapers-" + suffix)


def compose(paths: list[Path], size: tuple[int, int], layout: str) -> Image.Image:
    """Compose photo prints for collages; fit a complete photo in single mode."""
    if not paths or layout not in ("single", "collage"):
        raise WallpaperError("Choose photos and a supported wallpaper layout.")
    width, height = size
    if width < 320 or height < 320 or width * height > 34_000_000:
        raise WallpaperError("The wallpaper dimensions are outside the supported range.")
    if layout == "collage":
        from .photo_pile import compose_photo_pile
        return compose_photo_pile(paths, size)
    gutter = max(8, min(size) // 80)
    canvas = Image.new("RGB", size, "#182027")
    with Image.open(paths[0]) as opened:
        image = ImageOps.exif_transpose(opened).convert("RGB")
        fitted = ImageOps.contain(image, (width-2*gutter, height-2*gutter), Image.Resampling.LANCZOS)
    canvas.paste(fitted, ((width-fitted.width)//2, (height-fitted.height)//2))
    return canvas


def _remove_generation(path: Path, root: Path) -> None:
    safe_path(path)
    if (not GENERATION.fullmatch(path.name) or path.resolve().parent != root.resolve()
            or not path.is_dir()):
        raise WallpaperError("The generated wallpaper folder needs manual inspection.")
    for child in path.iterdir():
        safe_path(child)
        if not child.is_file() or not re.fullmatch(r"wallpaper-\d{2}\.jpg", child.name):
            raise WallpaperError("Unexpected files in the generated wallpaper folder were retained.")
    # Resolved absolute target was verified to be a direct child of our owned root.
    shutil.rmtree(path)


def generate_wallpapers(config, *, apply: bool = False, report=print, size=None) -> Path:
    """Caller holds the cache lock; publish only after a complete local render."""
    cache = Cache(config)
    cache.open()
    paths = [cache.photos / f"{key}.jpg" for key in cache.state["items"]]
    if not paths:
        raise WallpaperError("Download some photos before generating wallpapers.")
    root = wallpaper_dir(config)
    safe_path(root)
    marker = root / ".owner"
    safe_path(marker)
    if root.exists():
        if not marker.is_file() or marker.read_text(encoding="utf-8") != MARKER:
            raise WallpaperError("The wallpaper output folder is not owned by this app; its files were retained.")
    else:
        root.mkdir(parents=True)
        marker.write_text(MARKER, encoding="utf-8")
    # Reject foreign contents before touching old generations or desktop settings.
    for entry in root.iterdir():
        safe_path(entry)
        if entry.name not in (".owner", "current.json", "current.tmp") and not (entry.is_dir() and GENERATION.fullmatch(entry.name)):
            raise WallpaperError("Unexpected files in the wallpaper output folder were retained.")
    current = root / "current.json"
    previous = None
    active = None
    if current.exists():
        try:
            saved = json.loads(current.read_text(encoding="utf-8"))
            previous = saved["generation"]
            active = saved.get("active_generation")
            if not isinstance(previous, str) or not GENERATION.fullmatch(previous):
                raise ValueError
            if active is not None and (not isinstance(active, str) or not GENERATION.fullmatch(active)):
                raise ValueError
        except (ValueError, KeyError, TypeError):
            raise WallpaperError("The wallpaper output manifest is invalid; previous images were retained.") from None
    folder = root / ("generation-" + uuid.uuid4().hex)
    folder.mkdir()
    rng = random.SystemRandom()
    deck = paths[:]
    rng.shuffle(deck)
    # For one photo, prepare one image; larger libraries get 20 rotating frames.
    count = min(20, len(paths))
    images_per_frame = min(len(paths), config.wallpaper_photos_per_image if config.wallpaper_layout == "collage" else 1)
    dimensions = size or screen_size()
    total_bytes = 0
    applied = False
    try:
        for index in range(count):
            # Cycle fairly through a shuffled pool before starting the pool again.
            chosen = []
            while len(chosen) < images_per_frame:
                if not deck:
                    deck = paths[:]
                    rng.shuffle(deck)
                candidate = deck.pop()
                if candidate not in chosen:
                    chosen.append(candidate)
            image = compose(chosen, dimensions, config.wallpaper_layout)
            output = folder / f"wallpaper-{index:02d}.jpg"
            # Bound each frame too: detailed 4K collages can otherwise use
            # several MiB apiece even though the source cache is modest.
            frame_budget = MAX_GENERATION_BYTES // count
            encoded = b""
            for quality in (85, 78, 70, 62, 54, 46):
                stream = io.BytesIO()
                image.save(stream, "JPEG", quality=quality, optimize=True, subsampling=0)
                encoded = stream.getvalue()
                if len(encoded) <= frame_budget:
                    break
            output.write_bytes(encoded)
            total_bytes += len(encoded)
            if total_bytes > MAX_GENERATION_BYTES:
                raise WallpaperError("Generated wallpapers exceeded the 32 MiB generation limit; previous images were retained.")
        if apply:
            set_wallpaper_all(folder / "wallpaper-00.jpg")
            applied = True
        # Keep current + previous generation, so Windows can finish displaying an old frame.
        manifest = {"generation": folder.name, "layout": config.wallpaper_layout,
                    "images": count, "size": list(dimensions), "bytes": total_bytes,
                    "photos_per_image": images_per_frame,
                    "active_generation": folder.name if apply else active,
                    "rotation_remaining": [f"wallpaper-{n:02d}.jpg" for n in range(1, count)] if apply else [],
                    "rotation_current": "wallpaper-00.jpg" if apply else None}
        temporary = root / "current.tmp"
        safe_path(temporary)
        temporary.write_text(json.dumps(manifest), encoding="utf-8")
        temporary.replace(current)
    except Exception:
        # If Windows already selected this generation, retain it for recovery.
        if not applied:
            _remove_generation(folder, root)
        raise
    for old in root.iterdir():
        if old.is_dir() and old.name not in (folder.name, previous if apply else active):
            _remove_generation(old, root)
    report(f"Generated {count} {config.wallpaper_layout} wallpapers at {dimensions[0]} x {dimensions[1]} using local photos.")
    report(f"Wallpaper folder: {folder}")
    if apply:
        report("Applied the same wallpaper image to all monitors.")
    return folder


def rotate_wallpaper(config, report=print) -> None:
    """Caller holds cache lock. Rotate an existing set without Google or rendering."""
    if not config.windows_wallpaper:
        return
    root = wallpaper_dir(config)
    safe_path(root)
    marker, current = root / ".owner", root / "current.json"
    for path in (marker, current):
        safe_path(path)
    if not marker.is_file() or marker.read_text(encoding="utf-8") != MARKER:
        raise WallpaperError("Prepare this app's owned wallpapers before rotating.")
    data = json.loads(current.read_text(encoding="utf-8"))
    generation = data.get("active_generation")
    if not isinstance(generation, str) or not GENERATION.fullmatch(generation):
        raise WallpaperError("Enable wallpaper rotation first.")
    folder = root / generation
    safe_path(folder)
    names = sorted(p.name for p in folder.iterdir() if re.fullmatch(r"wallpaper-\d{2}\.jpg", p.name))
    remaining = data.get("rotation_remaining")
    if not isinstance(remaining, list) or any(name not in names for name in remaining):
        raise WallpaperError("The wallpaper rotation state is invalid.")
    if not remaining:
        remaining = names[:]
    choices = [name for name in remaining if name != data.get("rotation_current")] or remaining
    if not choices:
        raise WallpaperError("No generated wallpapers are available.")
    name = random.SystemRandom().choice(choices)
    path = folder / name
    safe_path(path)
    set_wallpaper_all(path)
    remaining.remove(name)
    data.update(rotation_current=name, rotation_remaining=remaining)
    temporary = root / "current.tmp"
    safe_path(temporary)
    temporary.write_text(json.dumps(data), encoding="utf-8")
    temporary.replace(current)
    report("Changed wallpaper on all monitors using the same local image.")
