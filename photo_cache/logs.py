"""Bounded local logs shared by task launchers and the desktop log viewer."""

import os
import re
from datetime import datetime, timezone
from pathlib import Path

from .cache import CacheError, file_lock, safe_path
from .runtime import application_dir, frozen


LOG_LIMIT = 1024 * 1024


def log_directory(config_path: Path) -> Path:
    return (config_path.absolute().parent if frozen() else application_dir()) / '.state'


class BoundedLog:
    """Retain the current log and one previous file, up to 1 MiB each."""

    def __init__(self, path: Path):
        self.path = path
        safe_path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, data: bytes) -> None:
        for offset in range(0, len(data), 8192):
            chunk = data[offset:offset + 8192]
            size = self.path.stat().st_size if self.path.exists() else 0
            if size + len(chunk) > LOG_LIMIT:
                previous = self.path.with_suffix('.log.1')
                safe_path(previous)
                os.replace(self.path, previous)
            with self.path.open('ab') as stream:
                stream.write(chunk)


def append_app_log(config_path: Path, message: str) -> None:
    try:
        folder = log_directory(config_path)
        safe_path(folder)
        with file_lock(folder / 'app-log.lock'):
            safe_message = re.sub(r'https?://\S+', '[private URL]', message)
            stamp = datetime.now(timezone.utc).isoformat(timespec='seconds')
            BoundedLog(folder / 'app.log').write(f'[{stamp}] {safe_message}\n'.encode('utf-8'))
    except (OSError, CacheError):
        # A logging failure must never interrupt a photo download or sign-in.
        pass


def read_log(folder: Path, name: str) -> str:
    """Read bounded snapshots; display ISO task timestamps in local time."""
    if name not in ('task.log', 'wallpaper.log', 'app.log'):
        raise ValueError('Unknown log')
    sections = []
    for filename in (name + '.1', name):
        path = folder / filename
        try:
            safe_path(path)
            with path.open('rb') as stream:
                stream.seek(max(0, path.stat().st_size - LOG_LIMIT))
                body = stream.read(LOG_LIMIT).decode('utf-8', errors='replace')
            sections.append(f'--- {filename} ---\n{body}')
        except FileNotFoundError:
            continue
        except (OSError, CacheError):
            sections.append(f'{filename} could not be read. Try Reload or Open log folder.')
    if not sections:
        return 'No entries yet. Scheduled runs and app actions will appear here.'
    def local_header(match):
        try:
            stamp = datetime.fromisoformat(match[1])
            if stamp.tzinfo is None:
                return match[0]
            return '[' + stamp.astimezone().strftime('%Y-%m-%d %I:%M:%S %p %Z') + ']'
        except ValueError:
            return match[0]
    return re.sub(r'\[([^\]\r\n]+)\]', local_header, '\n\n'.join(sections))
