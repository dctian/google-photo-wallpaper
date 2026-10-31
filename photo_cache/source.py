"""Read-only Google Photos web access through a dedicated browser profile.

This is an unofficial integration. The pinned gpwc package supplies only the
two read-only request payloads; strict parsing here deliberately fails closed
when the web response changes. Cookies never leave the browser context.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlsplit

from .hosts import is_google_photos_image_host


class SourceError(RuntimeError):
    """A safe-to-display source failure, without account credentials or URLs."""


class LoginRequired(SourceError):
    """The dedicated profile needs the user's interactive Google sign-in."""


@dataclass(frozen=True)
class RemotePhoto:
    id: str
    url: str
    width: int
    height: int
    version: str = ""
    # Web AlbumItem.timestamp is capture time, not creation/upload time.
    # Both this timestamp and the capture timezone offset use milliseconds.
    taken_at_ms: int | None = None
    timezone_offset_ms: int | None = None


@dataclass(frozen=True)
class RemoteAlbum:
    id: str
    title: str
    url: str
    item_count: int


_PROFILE_MARKER = ".photo-cache-profile"
_ALLOWED_RPCS = frozenset({"Z5xsfc", "snAcKc"})
_KEY = re.compile(r"[A-Za-z0-9_-]+\Z")
_ALBUM_PATH = re.compile(r"/(?:u/(\d+)/)?album/([A-Za-z0-9_-]+)/?\Z")


def _key(value: Any) -> str:
    if not isinstance(value, str) or not _KEY.fullmatch(value):
        raise SourceError("Google returned an unrecognized photo or album identifier.")
    return value


def _count(value: Any) -> int:
    if type(value) is not int or value < 0:
        raise SourceError("Google returned an unrecognized album count.")
    return value


def _token(value: Any) -> str | None:
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise SourceError("Google returned an unrecognized pagination token.")
    return value


def _capture_time(timestamp: Any, offset: Any) -> tuple[int | None, int | None]:
    """Validate optional web metadata without guessing seconds versus millis."""
    if timestamp is not None and (type(timestamp) is not int
                                  or not -62135596800000 <= timestamp < 253402300800000):
        raise SourceError("Google returned an unrecognized photo capture date.")
    if offset is not None and (type(offset) is not int or not -86400000 < offset < 86400000):
        raise SourceError("Google returned an unrecognized photo timezone offset.")
    return timestamp, offset


def _album_key(url: str, account_index: int) -> str:
    try:
        parsed = urlsplit(url)
        match = _ALBUM_PATH.fullmatch(parsed.path)
        if (parsed.scheme != "https" or parsed.netloc != "photos.google.com"
                or not match or parsed.fragment):
            raise ValueError
        if match[1] is not None and int(match[1]) != account_index:
            raise SourceError("An album uses a different Google account index than this profile.")
        return _key(match[2])
    except (TypeError, ValueError):
        raise SourceError("Use a private Google Photos album URL copied from the album page.") from None


def _image_url(url: Any, width: int, height: int) -> str:
    if not isinstance(url, str):
        raise SourceError("Google returned an unrecognized image URL.")
    try:
        parsed = urlsplit(url)
        host = parsed.hostname or ""
        if (parsed.scheme != "https" or not is_google_photos_image_host(host)
                or parsed.port is not None or parsed.username or parsed.password
                or parsed.query or parsed.fragment or not parsed.path):
            raise ValueError
    except ValueError:
        raise SourceError("Google returned an unsupported image host or URL format.") from None
    # Google image sizing parameters are a suffix, not URL query parameters.
    base = url.split("=", 1)[0]
    return f"{base}=w{width}-h{height}"


def _decode_rpc(body: str, rpc: str, request_id: str) -> list:
    """Decode Google's length-prefixed, XSSI-protected batchexecute response."""
    matches = []
    try:
        for line in body.splitlines():
            line = line.strip()
            if not line.startswith("["):
                continue
            envelope = json.loads(line)
            if not isinstance(envelope, list):
                continue
            for record in envelope:
                if (isinstance(record, list) and len(record) >= 7
                        and record[0] == "wrb.fr" and record[1] == rpc
                        and record[6] == request_id):
                    if not isinstance(record[2], str):
                        raise ValueError
                    matches.append(json.loads(record[2]))
        if len(matches) != 1 or not isinstance(matches[0], list):
            raise ValueError
    except (TypeError, ValueError):
        raise SourceError("Google's album response could not be verified. The existing cache was kept.") from None
    return matches[0]


def _albums_page(data: list, account_index: int) -> tuple[list[RemoteAlbum], str | None]:
    # Google omits trailing null fields and can terminate an otherwise valid
    # paginated scan with []. This matches the pinned upstream safe_get parser.
    if not data:
        return [], None
    if data[0] is not None and not isinstance(data[0], list):
        raise SourceError("Google's album-list format changed.")
    albums = []
    for row in data[0] or []:
        if not isinstance(row, list) or not row or not isinstance(row[-1], dict):
            raise SourceError("Google's album-list format changed.")
        detail = row[-1].get("72930366")
        if not isinstance(detail, list) or len(detail) < 4:
            raise SourceError("Google's album-list metadata could not be verified.")
        album_id = _key(row[0])
        title = detail[1]
        if title is not None and not isinstance(title, str):
            raise SourceError("Google returned an unrecognized album title.")
        albums.append(RemoteAlbum(album_id, title or "Untitled album",
                                  f"https://photos.google.com/u/{account_index}/album/{album_id}",
                                  _count(detail[3])))
    return albums, _token(data[1] if len(data) > 1 else None)


def _album_page(data: list, album_id: str, first: bool,
                width: int, height: int) -> tuple[list[tuple[str, RemotePhoto | None]], str | None, int | None]:
    if not first and (data == [] or data == [None]):
        return [], None, None
    if len(data) < 2 or (data[1] is not None and not isinstance(data[1], list)):
        raise SourceError("Google's album-content format changed.")
    metadata = data[3] if len(data) > 3 else None
    count = None
    if metadata is not None:
        if not isinstance(metadata, list) or len(metadata) <= 21 or metadata[0] != album_id:
            raise SourceError("The requested album could not be verified.")
        count = _count(metadata[21])
    elif first:
        raise SourceError("Album access or its metadata could not be verified.")
    items = []
    for row in data[1] or []:
        if not isinstance(row, list) or len(row) < 6:
            raise SourceError("Google returned an unrecognized album item.")
        item_id = _key(row[0])
        dimensions = row[1]
        if (not isinstance(dimensions, list) or len(dimensions) < 3
                or type(dimensions[1]) is not int or type(dimensions[2]) is not int
                or dimensions[1] <= 0 or dimensions[2] <= 0):
            raise SourceError("Google returned an unsupported album item or image dimensions.")
        details = row[-1] if isinstance(row[-1], dict) else {}
        # Check marker presence, including zero-duration videos. A motion photo
        # has marker 146008172 and is allowed as its still-image representation.
        if "76647426" in details:
            items.append((item_id, None))
            continue
        version_data = [row[3], dimensions[1], dimensions[2]]
        version = hashlib.sha256(json.dumps(version_data).encode()).hexdigest()[:20]
        taken_at_ms, timezone_offset_ms = _capture_time(row[2], row[4])
        photo = RemotePhoto(item_id, _image_url(dimensions[0], width, height),
                            dimensions[1], dimensions[2], version,
                            taken_at_ms, timezone_offset_ms)
        items.append((item_id, photo))
    return items, _token(data[2] if len(data) > 2 else None), count


def _prepare_profile(profile_dir: Path) -> Path:
    """Never attach to an ordinary browser profile, even if misconfigured."""
    path = Path(profile_dir).expanduser().absolute()
    marker = path / _PROFILE_MARKER
    for part in (marker, path, *path.parents):
        if part.is_symlink() or (hasattr(part, "is_junction") and part.is_junction()):
            raise SourceError("The dedicated browser profile and its parents cannot contain symbolic links or junctions.")
    if path.exists():
        if not path.is_dir() or (not marker.is_file() and any(path.iterdir())):
            raise SourceError("Choose an empty directory for the dedicated photo browser profile.")
    else:
        path.mkdir(parents=True)
    if not marker.exists():
        marker.write_text("Dedicated Google Photos wallpaper browser profile\n", encoding="utf-8")
    return path


class GooglePhotosSource:
    def __init__(self, profile_dir: str | Path, max_width: int = 3840,
                 max_height: int = 2160, account_index: int = 0,
                 browser_channel: str = "chrome", max_pages: int = 10000):
        if (type(account_index) is not int or account_index < 0
                or not 1 <= max_width <= 16384 or not 1 <= max_height <= 16384
                or max_pages < 1):
            raise ValueError("Invalid source size, account index, or pagination limit.")
        if browser_channel not in {"chrome", "msedge", "chromium"}:
            raise ValueError("browser_channel must be chrome, msedge, or chromium.")
        self.profile_dir = Path(profile_dir)
        self.max_width = max_width
        self.max_height = max_height
        self.account_index = account_index
        self.browser_channel = browser_channel
        self.max_pages = max_pages
        self._playwright = None
        self._context = None
        self._globals = None

    def __enter__(self):
        self._open(headless=True)
        try:
            page = self._context.pages[0] if self._context.pages else self._context.new_page()
            page.goto(self._home_url, wait_until="domcontentloaded", timeout=45000)
            self._globals = self._read_auth(page)
            return self
        except SourceError:
            self.close()
            raise
        except Exception:
            self.close()
            raise SourceError("The photo browser could not connect. Try again or run login.") from None

    def __exit__(self, *_):
        self.close()

    @property
    def _home_url(self) -> str:
        return f"https://photos.google.com/u/{self.account_index}/"

    def _open(self, headless: bool) -> None:
        if self._context is not None:
            raise SourceError("This photo source is already open.")
        profile = _prepare_profile(self.profile_dir)
        try:
            from playwright.sync_api import sync_playwright
            self._playwright = sync_playwright().start()
            self._context = self._playwright.chromium.launch_persistent_context(
                str(profile), channel=self.browser_channel, headless=headless,
                chromium_sandbox=True,
                accept_downloads=False, timeout=45000,
                viewport={"width": 1280, "height": 900})
        except Exception:
            self.close()
            raise SourceError("The dedicated browser could not start. Install the configured browser and close any other photo-cache run.") from None

    @staticmethod
    def _read_auth(page) -> dict:
        if urlsplit(page.url).hostname != "photos.google.com":
            raise LoginRequired("Run login to sign in to the dedicated Google Photos browser.")
        try:
            data = page.evaluate("""() => {
                const d = window.WIZ_global_data || {};
                return Object.fromEntries(['SNlM0e','FdrFJe','cfb2h','Im6cmf','oPEP7c'].map(k => [k,d[k]]));
            }""")
        except Exception:
            raise LoginRequired("Google Photos sign-in could not be verified. Run login again.") from None
        if not isinstance(data, dict) or not isinstance(data.get("oPEP7c"), str) or "@" not in data["oPEP7c"]:
            raise LoginRequired("Run login to sign in to the dedicated Google Photos browser.")
        if any(not isinstance(data.get(k), str) or not data[k] for k in ("SNlM0e", "FdrFJe", "cfb2h", "Im6cmf")):
            raise SourceError("Google's browser authentication format changed.")
        if not re.fullmatch(r"/(?:u/\d+/)?_/PhotosUi", data["Im6cmf"]):
            raise SourceError("Google returned an unrecognized Photos endpoint.")
        data.pop("oPEP7c")  # Do not retain the account's email address.
        return data

    def close(self) -> None:
        try:
            if self._context is not None:
                self._context.close()
        except Exception:
            pass
        finally:
            self._context = None
            self._globals = None
            if self._playwright is not None:
                try:
                    self._playwright.stop()
                except Exception:
                    pass
                self._playwright = None

    def _refresh_auth(self) -> None:
        """Give the saved Google browser session one chance to renew app tokens."""
        try:
            page = self._context.pages[0] if self._context.pages else self._context.new_page()
            page.goto(self._home_url, wait_until="domcontentloaded", timeout=45000)
            self._globals = self._read_auth(page)
        except SourceError:
            raise
        except Exception:
            raise LoginRequired("The saved Google sign-in could not be renewed. Run login again.") from None

    def _rpc(self, payload, _retry_auth: bool = True) -> list:
        if payload.rpcid not in _ALLOWED_RPCS:
            raise SourceError("Only read-only album requests are permitted.")
        if self._context is None or self._globals is None:
            raise SourceError("Open GooglePhotosSource using a context manager first.")
        data = self._globals
        response = None
        try:
            response = self._context.request.post(
                f"https://photos.google.com{data['Im6cmf']}/data/batchexecute",
                params={"rpcids": payload.rpcid, "source-path": f"/u/{self.account_index}/",
                        "f.sid": data["FdrFJe"], "bl": data["cfb2h"], "rt": "c"},
                form={"f.req": json.dumps([[[payload.rpcid, json.dumps(payload.data), None, payload.payload_id]]]),
                      "at": data["SNlM0e"]},
                headers={"Origin": "https://photos.google.com", "Referer": self._home_url},
                timeout=45000, max_redirects=0)
            if response.status in {301, 302, 303, 307, 308, 401, 403}:
                if _retry_auth:
                    # The SSO browser session can outlive short-lived Photos
                    # tokens. Navigate normally, then retry this read once.
                    self._refresh_auth()
                    return self._rpc(payload, _retry_auth=False)
                raise LoginRequired("Google Photos needs sign-in again. Run login; the existing cache was kept.")
            if response.status != 200:
                raise SourceError(f"Google Photos temporarily refused the album request (HTTP {response.status}).")
            return _decode_rpc(response.text(), payload.rpcid, payload.payload_id)
        except SourceError:
            raise
        except Exception:
            raise SourceError("The album request failed. The existing cache was kept; try again later.") from None
        finally:
            if response is not None:
                try:
                    response.dispose()
                except Exception:
                    pass

    @staticmethod
    def _payloads():
        try:
            from gpwc import payloads
            return payloads
        except ImportError:
            raise SourceError("Install the project's pinned gpwc dependency before syncing.") from None

    def download_photo(self, photo: RemotePhoto, config) -> bytes:
        """Fetch one image using this browser's authenticated cookie jar.

        APIRequestContext buffers each response. Check both its declared and
        actual size, and dispose it immediately so buffers never accumulate for
        the entire batch. Redirect destinations are independently allowlisted.
        """
        if self._context is None:
            raise SourceError("Keep the Google Photos source open while downloading pictures.")
        url = photo.url
        for _ in range(5):
            response = None
            try:
                parsed = urlsplit(url)
                if (parsed.scheme != "https" or not is_google_photos_image_host(parsed.hostname or "")
                        or parsed.username or parsed.password or parsed.port not in (None, 443)):
                    raise SourceError("Google returned an unsupported image download host.")
                response = self._context.request.get(
                    url, headers={"Referer": self._home_url}, max_redirects=0, timeout=45000)
                headers = {name.lower(): value for name, value in response.headers.items()}
                if response.status in {301, 302, 303, 307, 308}:
                    location = headers.get("location")
                    if not isinstance(location, str) or not location:
                        raise SourceError("Google returned an incomplete image redirect.")
                    url = urljoin(url, location)
                    continue
                if response.status in {401, 403}:
                    raise LoginRequired("Google denied the image download. Run login again; the existing collection remains available.")
                if response.status != 200:
                    raise SourceError(f"Google could not provide one image (HTTP {response.status}).")
                if not headers.get("content-type", "").lower().startswith("image/"):
                    raise SourceError("Google did not return an image.")
                if "content-length" in headers:
                    try:
                        declared = int(headers["content-length"])
                    except (TypeError, ValueError):
                        raise SourceError("Google returned an unrecognized image length.") from None
                    if declared < 0 or declared > config.max_download_bytes:
                        raise SourceError("One image exceeded the download size limit.")
                content = response.body()
                if len(content) > config.max_download_bytes:
                    raise SourceError("One image exceeded the download size limit.")
                return content
            except SourceError:
                raise
            except Exception:
                # Browser/network errors often contain private image URLs.
                raise SourceError("Image download failed; the existing collection remains available.") from None
            finally:
                if response is not None:
                    try:
                        response.dispose()
                    except Exception:
                        pass
        raise SourceError("Image download redirected too many times.")

    def list_albums(self) -> list[RemoteAlbum]:
        payloads = self._payloads()
        result = {}
        token = None
        seen_tokens = set()
        for _ in range(self.max_pages):
            data = self._rpc(payloads.GetAlbumsPage(page_id=token, parse_response=False))
            albums, next_token = _albums_page(data, self.account_index)
            if next_token and not albums:
                raise SourceError("Google returned an empty intermediate album-list page.")
            for album in albums:
                if album.id in result:
                    raise SourceError("Album pagination repeated an item. Try again when the album list is stable.")
                result[album.id] = album
            if not next_token:
                return list(result.values())
            if next_token in seen_tokens:
                raise SourceError("Google's album-list pagination repeated a page.")
            seen_tokens.add(next_token)
            token = next_token
        raise SourceError("The album list exceeded the pagination safety limit.")

    def list_photos(self, album_urls: list[str]) -> list[RemotePhoto]:
        if not album_urls:
            raise SourceError("Choose at least one private Google Photos album first.")
        album_ids = list(dict.fromkeys(_album_key(url, self.account_index) for url in album_urls))
        payloads = self._payloads()
        result = {}
        for album_id in album_ids:
            token = None
            seen_tokens = set()
            item_ids = set()
            expected_count = None
            for page_number in range(self.max_pages):
                raw = self._rpc(payloads.GetAlbumPage(album_id, page_id=token, parse_response=False))
                items, next_token, count = _album_page(raw, album_id, page_number == 0,
                                                       self.max_width, self.max_height)
                if count is not None:
                    if expected_count is not None and expected_count != count:
                        raise SourceError("The album changed while reading it. Try again later.")
                    expected_count = count
                if next_token and not items:
                    raise SourceError("Google returned an empty intermediate album page.")
                for item_id, photo in items:
                    if item_id in item_ids:
                        raise SourceError("Album pagination repeated an item. Try again later.")
                    item_ids.add(item_id)
                    if photo is not None:
                        result[photo.id] = photo
                if not next_token:
                    if expected_count != len(item_ids):
                        raise SourceError("The album's declared size does not match its media. It may contain unsupported entries or have changed; the existing cache was kept.")
                    break
                if next_token in seen_tokens:
                    raise SourceError("Google's album pagination repeated a page.")
                seen_tokens.add(next_token)
                token = next_token
            else:
                raise SourceError("An album exceeded the pagination safety limit.")
        return list(result.values())


def _native_browser_executable(browser_channel: str) -> Path:
    """Find an ordinary installed browser; do not use Playwright for sign-in."""
    if browser_channel not in {"chrome", "msedge"}:
        raise SourceError("Interactive Google sign-in requires installed Chrome or Edge. Choose chrome or msedge as browser_channel.")
    if browser_channel == "chrome":
        relative = Path("Google/Chrome/Application/chrome.exe")
        command_names = ("google-chrome", "google-chrome-stable", "chrome")
        mac_path = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    else:
        relative = Path("Microsoft/Edge/Application/msedge.exe")
        command_names = ("microsoft-edge", "microsoft-edge-stable", "msedge")
        mac_path = Path("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge")
    candidates = [Path(os.environ[name]) / relative
                  for name in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA")
                  if os.environ.get(name)]
    candidates.append(mac_path)
    for name in command_names:
        found = shutil.which(name)
        if found:
            candidates.append(Path(found))
    for candidate in candidates:
        if candidate.is_file():
            return candidate.absolute()
    raise SourceError("The configured browser was not found. Install Chrome or Edge, or select the browser already installed.")


def login(profile_dir: str | Path, browser_channel: str = "chrome", account_index: int = 0,
          timeout: float = 600) -> None:
    """Sign in in a normal browser, close it, then verify the persisted session.

    The visible sign-in browser has no automation, debugging, or sandbox flags.
    It uses only the dedicated profile. Timeout leaves that browser alone.
    """
    if timeout <= 0:
        raise ValueError("The login timeout must be positive.")
    source = GooglePhotosSource(profile_dir, browser_channel=browser_channel, account_index=account_index)
    executable = _native_browser_executable(browser_channel)
    profile = _prepare_profile(source.profile_dir)
    print("Sign in to Google Photos in the new browser window. Once your library is visible, close that dedicated browser window to finish.")
    try:
        process = subprocess.Popen(
            [str(executable), f"--user-data-dir={profile}", "--no-first-run",
             "--no-default-browser-check", source._home_url],
            shell=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return_code = process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        raise LoginRequired("The sign-in window is still open. Close that dedicated browser window, then run login again. Your normal browser was left alone.") from None
    except OSError:
        raise SourceError("The normal sign-in browser could not start. Close any other photo-cache browser window and try again.") from None
    if return_code != 0:
        raise LoginRequired("The sign-in browser did not close successfully. Close its window and run login again.")
    # Reopen only after the user closes Chrome/Edge, so cookies are persisted and
    # no two processes share this profile. __enter__ validates authenticated data.
    with source:
        pass
