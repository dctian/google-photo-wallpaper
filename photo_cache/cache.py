from __future__ import annotations

import hashlib
import copy
import io
import json
import math
import os
import re
import time
import warnings
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable, Protocol
from urllib.parse import urljoin, urlparse

from .config import Config
from .hosts import is_google_photos_image_host


class CacheError(RuntimeError):
    pass


MAX_HOURLY_FETCH_ATTEMPTS = 50
FETCH_WINDOW_SECONDS = 3600


class Photo(Protocol):
    id: str
    url: str
    version: str


@dataclass(frozen=True)
class RefreshResult:
    downloaded: int
    failed: int
    photos: int
    bytes: int
    attempts: int = 0
    deferred: bool = False
    next_allowed_at: float | None = None


@dataclass(frozen=True)
class QuotaStatus:
    limit: int
    used: int
    remaining: int
    next_allowed_at: float | None


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_path(path: Path) -> None:
    """Reject symlinks/junctions before touching a managed cache."""
    for part in (path, *path.parents):
        if part.is_symlink() or (hasattr(part, "is_junction") and part.is_junction()):
            raise CacheError("Managed cache paths cannot contain symbolic links or junctions.")


@contextmanager
def file_lock(path: Path):
    """OS locks release on process exit, including crashes; no stale PID cleanup."""
    safe_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+b")
    try:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise CacheError("Another login, scan, or refresh is already running.") from exc
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    finally:
        handle.close()


def download_photo(photo: Photo, config: Config) -> bytes:
    """Download only Google photo CDN images, without account cookies."""
    import requests

    url = photo.url
    for _ in range(5):
        try:
            parsed = urlparse(url)
            host = parsed.hostname or ""
            if parsed.scheme != "https" or not is_google_photos_image_host(host) or parsed.username or parsed.password or parsed.port not in (None, 443):
                raise ValueError
        except ValueError:
            raise CacheError("The album returned an unexpected image host.") from None
        try:
            with requests.get(url, stream=True, timeout=(15, 60), allow_redirects=False) as response:
                if response.is_redirect:
                    url = urljoin(url, response.headers.get("Location", ""))
                    continue
                response.raise_for_status()
                if not response.headers.get("Content-Type", "").lower().startswith("image/"):
                    raise CacheError("Google did not return an image.")
                result = bytearray()
                for chunk in response.iter_content(64 * 1024):
                    if len(result) + len(chunk) > config.max_download_bytes:
                        raise CacheError("One image exceeded the download size limit.")
                    result.extend(chunk)
                return bytes(result)
        except requests.RequestException as exc:
            # requests errors often contain signed image URLs; never expose them.
            raise CacheError("Image download failed; the existing collection remains available.") from exc
    raise CacheError("Image download redirected too many times.")


def wallpaper_jpeg(raw: bytes, config: Config) -> bytes:
    from PIL import Image, ImageOps, UnidentifiedImageError

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw)) as opened:
                if opened.width * opened.height > 60_000_000:
                    raise CacheError("One image exceeded the pixel limit.")
                image = ImageOps.exif_transpose(opened)
                image.thumbnail((config.max_width, config.max_height), Image.Resampling.LANCZOS)
                if image.mode in ("RGBA", "LA") or "transparency" in image.info:
                    rgba = image.convert("RGBA")
                    result = Image.new("RGB", rgba.size, "black")
                    result.paste(rgba, mask=rgba.getchannel("A"))
                    image = result
                else:
                    image = image.convert("RGB")
                # No EXIF/GPS or other source metadata is copied into wallpaper derivatives.
                out = io.BytesIO()
                image.save(out, "JPEG", quality=config.jpeg_quality, optimize=True)
                content = out.getvalue()
    except (OSError, ValueError, UnidentifiedImageError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise CacheError("An image could not be safely decoded.") from exc
    if len(content) > config.max_image_bytes:
        raise CacheError("One wallpaper exceeded the configured image size limit.")
    return content


class Cache:
    MARKER = "google-photo-album-cache-v1\n"
    NAME = re.compile(r"[0-9a-f]{64}\.jpg")

    def __init__(self, config: Config):
        self.config = config
        self.root = config.cache_dir
        self.photos = self.root / "photos"
        self.state_file = self.root / "state.json"
        self.state: dict = {}

    def open(self) -> None:
        safe_path(self.root)
        self.root.mkdir(parents=True, exist_ok=True)
        marker = self.root / ".owner"
        safe_path(marker)
        if not marker.exists():
            if any(self.root.iterdir()):
                raise CacheError("Refusing to use a nonempty folder without the wallpaper cache marker.")
            marker.write_text(self.MARKER, encoding="utf-8")
        if marker.read_text(encoding="utf-8") != self.MARKER:
            raise CacheError("The cache ownership marker is invalid.")
        safe_path(self.photos)
        self.photos.mkdir(exist_ok=True)
        for file in self.photos.iterdir():
            safe_path(file)
            if not file.is_file() or not self.NAME.fullmatch(file.name):
                raise CacheError("The wallpaper folder contains an unmanaged file. Move it elsewhere first.")
        safe_path(self.state_file)
        if self.state_file.exists():
            try:
                self.state = json.loads(self.state_file.read_text(encoding="utf-8"))
                self._validate_state()
            except (ValueError, TypeError, KeyError, AttributeError) as exc:
                raise CacheError("Cache state is invalid; no cached photos were removed.") from exc
        else:
            if any(self.photos.iterdir()):
                raise CacheError("Cache state is missing; existing photos were left untouched.")
            self.state = {"schema": 1, "items": {}, "history": {}, "last_success": None}
        pending = self.root / "pending.jpg"
        safe_path(pending)
        if pending.exists():
            pending.unlink()
        # Recover only our generated files after an interrupted commit.
        for file in self.photos.iterdir():
            if file.stem not in self.state["items"]:
                file.unlink()
        for key in list(self.state["items"]):
            file = self.photos / f"{key}.jpg"
            if not file.exists():
                del self.state["items"][key]
            else:
                self.state["items"][key]["bytes"] = file.stat().st_size
        if "download_attempts" not in self.state:
            # Old versions did not record requests. Conservatively defer after
            # recent legacy activity, including a canceled initial bulk fill.
            self.state["download_attempts"] = self._legacy_download_attempts(time.time())
            self._update_quota_snapshot()
            self.save()

    def _validate_state(self) -> None:
        state = self.state
        if state["schema"] != 1 or not isinstance(state["items"], dict) or not isinstance(state["history"], dict):
            raise ValueError("schema")
        for key, item in state["items"].items():
            if not self.NAME.fullmatch(f"{key}.jpg") or not isinstance(item, dict) or not isinstance(item["version"], str) or type(item["selected"]) not in (int, float):
                raise ValueError("item")
        for field in ("history", "attempts"):
            values = state.get(field, {})
            if not isinstance(values, dict):
                raise ValueError(field)
            for key, selected in values.items():
                if (not self.NAME.fullmatch(f"{key}.jpg")
                        or type(selected) not in (int, float) or not math.isfinite(selected)):
                    raise ValueError(field)
        attempts = state.get("download_attempts", [])
        if not isinstance(attempts, list) or any(
                type(stamp) not in (int, float) or not math.isfinite(stamp) or stamp < 0
                for stamp in attempts):
            raise ValueError("download_attempts")

    def _legacy_download_attempts(self, at: float) -> list[float]:
        stamps = list(self.state.get("history", {}).values()) + list(self.state.get("attempts", {}).values())
        stamps.extend(item["selected"] for item in self.state.get("items", {}).values())
        markers = {}
        for name in ("last_attempt", "last_success"):
            try:
                markers[name] = datetime.fromisoformat(self.state.get(name) or "").timestamp()
                stamps.append(markers[name])
            except (TypeError, ValueError, OverflowError, OSError):
                pass
        recent = [stamp for stamp in stamps if type(stamp) in (int, float)
                  and math.isfinite(stamp) and stamp > at - FETCH_WINDOW_SECONDS]
        if not recent:
            return []
        unfinished = markers.get("last_attempt", 0) > markers.get("last_success", 0)
        latest = max(recent + ([at] if unfinished else []))
        return [latest] * MAX_HOURLY_FETCH_ATTEMPTS

    def quota_status(self, at: float | None = None) -> QuotaStatus:
        """Read the shared rolling-hour allowance without touching disk."""
        at = time.time() if at is None else at
        ledger = self.state.get("download_attempts")
        if ledger is None:
            ledger = self._legacy_download_attempts(at)
        active = sorted(stamp for stamp in ledger if stamp > at - FETCH_WINDOW_SECONDS)
        remaining = max(0, MAX_HOURLY_FETCH_ATTEMPTS - len(active))
        next_allowed = active[-MAX_HOURLY_FETCH_ATTEMPTS] + FETCH_WINDOW_SECONDS if not remaining else None
        return QuotaStatus(MAX_HOURLY_FETCH_ATTEMPTS, len(active), remaining, next_allowed)

    def _update_quota_snapshot(self, at: float | None = None) -> QuotaStatus:
        quota = self.quota_status(at)
        self.state["next_download_at"] = (
            datetime.fromtimestamp(quota.next_allowed_at, timezone.utc).isoformat()
            if quota.next_allowed_at is not None else None)
        return quota

    def deferred_result(self, report: Callable[[str], None] = print) -> RefreshResult:
        quota = self._update_quota_snapshot()
        self.save()
        if quota.next_allowed_at is not None:
            when = datetime.fromtimestamp(quota.next_allowed_at, timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
            report(f"Hourly photo allowance used. Next download available at {when}; existing wallpapers remain available.")
        return RefreshResult(0, 0, len(self.state["items"]), self.size(), 0, True, quota.next_allowed_at)

    def _reserve_download(self, key: str) -> bool:
        """Durably charge one attempt BEFORE any image network request."""
        stamp = time.time()
        if self.quota_status(stamp).remaining == 0:
            return False
        self.state["download_attempts"] = [
            value for value in self.state.get("download_attempts", [])
            if value > stamp - FETCH_WINDOW_SECONDS] + [stamp]
        self.state.setdefault("attempts", {})[key] = stamp
        self._update_quota_snapshot(stamp)
        try:
            self.save()
        except OSError:
            raise CacheError("Could not reserve the hourly photo allowance. No image was requested.") from None
        return True

    def save(self) -> None:
        temp = self.root / "state.tmp"
        safe_path(temp)
        with temp.open("w", encoding="utf-8") as handle:
            json.dump(self.state, handle, separators=(",", ":"), allow_nan=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, self.state_file)

    def size(self) -> int:
        return sum(item["bytes"] for item in self.state["items"].values())

    def _remove(self, key: str) -> None:
        path = self.photos / f"{key}.jpg"
        safe_path(path)
        try:
            path.unlink(missing_ok=True)
        except OSError as exc:
            raise CacheError("A cached image is in use. Try the refresh again later.") from exc
        del self.state["items"][key]

    def refresh(self, remote: Iterable[Photo], fetch: Callable = download_photo, report: Callable[[str], None] = print) -> RefreshResult:
        if self.quota_status().remaining == 0:
            return self.deferred_result(report)
        candidates = {}
        for photo in remote:
            if not isinstance(photo.id, str) or not photo.id:
                raise CacheError("The album scan returned an invalid photo identifier.")
            key = hashlib.sha256(photo.id.encode()).hexdigest()
            candidates.setdefault(key, photo)
        if not candidates:
            raise CacheError("No still photos were found. The previous collection was retained.")
        config = self.config
        items = self.state["items"]
        self.state["last_attempt"] = now()
        self.state["last_error"] = None
        self.save()
        # Reserve disk space for one verified JPEG while a replacement is staged.
        photo_budget = config.max_bytes - config.max_image_bytes
        if self.size() > photo_budget or len(items) > config.max_photos:
            raise CacheError("Existing cache exceeds the new limits. Restore the previous limits before refreshing.")
        pending = [(key, photo) for key, photo in candidates.items() if key not in items or items[key]["version"] != str(photo.version)]
        from .curation import rank_candidates, analyze_image, near_duplicate
        # Failed/filtered attempts are separate from displayed-photo history.
        # Deferring them prevents permanently unfit, highly ranked images from
        # monopolizing every bounded refresh window.
        self.state.setdefault("attempts", {})
        ranking_history = self.state["history"] | self.state["attempts"]
        pending = rank_candidates(pending, ranking_history, config)
        batch_limit = min(config.batch_size, MAX_HOURLY_FETCH_ATTEMPTS)
        target = min(len(pending), batch_limit, config.max_photos, self.quota_status().remaining)
        downloaded = failed = 0
        attempted = 0
        curated_out = 0
        published = set()
        # Failed and filtered photos consume the same per-run and hourly budget.
        attempt_limit = min(len(pending), batch_limit, self.quota_status().remaining)
        for key, photo in pending[:attempt_limit]:
            if downloaded >= target:
                break
            if not self._reserve_download(key):
                break
            attempted += 1
            try:
                raw = fetch(photo, config)
                if len(raw) > config.max_download_bytes:
                    raise CacheError("One image exceeded the download size limit.")
                content = wallpaper_jpeg(raw, config)
                analysis = analyze_image(content)
                if config.quality_filter:
                    if analysis.get("low_quality"):
                        curated_out += 1
                        self.state["attempts"][key] = time.time()
                        continue
                    duplicates = [item for other, item in items.items() if other != key and item.get("analysis")]
                    if any(near_duplicate(analysis, item["analysis"]) for item in duplicates):
                        curated_out += 1
                        self.state["attempts"][key] = time.time()
                        continue
            except (CacheError, OSError):
                failed += 1
                self.state["attempts"][key] = time.time()
                report("Skipped one photo after a download or image validation failure.")
                continue
            stage = self.root / "pending.jpg"
            safe_path(stage)
            try:
                with stage.open("wb") as handle:
                    handle.write(content)
                    handle.flush()
                    os.fsync(handle.fileno())
                previous_size = items.get(key, {}).get("bytes", 0)
                needed_count = len(items) + (key not in items)
                needed_bytes = self.size() - previous_size + len(content)
                # Never evict a photo published earlier in this same refresh.
                victims = sorted((k for k in items if k != key and k not in published), key=lambda k: (k in candidates, items[k]["selected"]))
                removals = []
                while needed_count > config.max_photos or needed_bytes > photo_budget:
                    if not victims:
                        break
                    victim = victims.pop(0)
                    victim_size = items[victim]["bytes"]
                    removals.append(victim)
                    needed_bytes -= victim_size
                    needed_count -= 1
                if needed_count > config.max_photos or needed_bytes > photo_budget:
                    break
                destination = self.photos / f"{key}.jpg"
                safe_path(destination)
                os.replace(stage, destination)
                selected = time.time_ns() / 1_000_000_000
                old_state = self.state
                self.state = copy.deepcopy(self.state)
                self.state["items"][key] = {"bytes": len(content), "version": str(photo.version), "selected": selected, "analysis": analysis}
                self.state["history"][key] = selected
                self.state["attempts"].pop(key, None)
                for victim in removals:
                    del self.state["items"][victim]
                try:
                    self.save()
                except OSError:
                    self.state = old_state
                    if key not in self.state["items"]:
                        destination.unlink(missing_ok=True)
                    raise CacheError("Could not save cache state. Previous wallpapers were retained.") from None
                items = self.state["items"]
                for victim in removals:
                    victim_path = self.photos / f"{victim}.jpg"
                    safe_path(victim_path)
                    victim_path.unlink(missing_ok=True)
                downloaded += 1
                published.add(key)
                if downloaded == 1 or downloaded % 25 == 0 or downloaded == target:
                    report(f"Downloaded {downloaded}/{target} wallpapers.")
            finally:
                if stage.exists():
                    stage.unlink()
        quota = self._update_quota_snapshot()
        self.state["curated_out"] = curated_out
        if curated_out:
            report(f"Skipped {curated_out} nearly blank or near-duplicate photos.")
        if not items or not any(key in candidates for key in items):
            self.state["last_error"] = "No photos from the selected albums could be prepared. Existing wallpapers were retained."
            self.save()
            if quota.remaining == 0:
                self.deferred_result(report)
                return RefreshResult(downloaded, failed, len(items), self.size(), attempted, True, quota.next_allowed_at)
            raise CacheError(self.state["last_error"])
        # Only prune old album membership after a complete scan and a usable replacement collection.
        if not failed and not curated_out:
            removals = [key for key in items if key not in candidates]
            if removals:
                old_state = self.state
                self.state = copy.deepcopy(self.state)
                for key in removals:
                    del self.state["items"][key]
                try:
                    self.save()
                except OSError:
                    self.state = old_state
                    raise CacheError("Could not save cache state. Previous wallpapers were retained.") from None
                items = self.state["items"]
                for key in removals:
                    path = self.photos / f"{key}.jpg"
                    safe_path(path)
                    path.unlink(missing_ok=True)
        self.state["history"] = {key: stamp for key, stamp in self.state["history"].items() if key in candidates}
        self.state["attempts"] = {key: stamp for key, stamp in self.state["attempts"].items() if key in candidates}
        self.state["source_count"] = len(candidates)
        if failed:
            self.state["last_error"] = f"{failed} image downloads failed; available photos were retained."
        elif pending and not downloaded and curated_out:
            self.state["last_error"] = "No replacements passed the photo filters. Existing wallpapers were retained; the next run will try other candidates."
        else:
            self.state["last_success"] = now()
        self.save()
        if quota.remaining == 0:
            self.deferred_result(report)
        return RefreshResult(downloaded, failed, len(items), self.size(), attempted,
                             quota.remaining == 0, quota.next_allowed_at)
