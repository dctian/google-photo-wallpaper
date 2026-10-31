"""Run the refresh without a Windows console and preserve its process exit code."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone
if not getattr(sys, 'frozen', False):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from photo_cache.runtime import frozen, application_dir, command as app_command

PROJECT_ROOT = application_dir()
LOG_LIMIT = 1024 * 1024


class BoundedLog:
    """Keep at most two 1 MiB files, including during a running refresh."""

    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, data: bytes) -> None:
        # Chunking also bounds a single unusually large child write.
        for offset in range(0, len(data), 8192):
            chunk = data[offset : offset + 8192]
            size = self.path.stat().st_size if self.path.exists() else 0
            if size + len(chunk) > LOG_LIMIT:
                os.replace(self.path, self.path.with_suffix('.log.1'))
            with self.path.open('ab') as stream:
                stream.write(chunk)


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    rotation = len(argv) == 3 and argv[2] == '--wallpaper-next'
    log_root = Path(argv[1]).resolve().parent if frozen() and len(argv) >= 2 else PROJECT_ROOT
    log = BoundedLog(log_root / '.state' / ('wallpaper.log' if rotation else 'task.log'))
    if len(argv) not in (2, 3) or argv[0] != '--config' or (len(argv) == 3 and argv[2] != '--wallpaper-next'):
        log.write(b'Launcher usage error: expected --config PATH.\n')
        return 2
    config_path = Path(argv[1]).resolve()
    command = 'wallpaper-next' if len(argv) == 3 else 'refresh'
    python_path = PROJECT_ROOT / '.venv' / 'Scripts' / 'python.exe'
    started = datetime.now(timezone.utc).isoformat(timespec='seconds')
    log.write(f'\n[{started}] {command} started.\n'.encode('ascii'))
    try:
        with subprocess.Popen(
            app_command(['--config', str(config_path), command], python=str(python_path)),
            cwd=PROJECT_ROOT,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env={**os.environ, 'PYTHONIOENCODING': 'utf-8', 'PYTHONUNBUFFERED': '1'},
            creationflags=subprocess.CREATE_NO_WINDOW,
        ) as child:
            assert child.stdout is not None
            while chunk := child.stdout.read(8192):
                log.write(chunk)
            result = child.wait()
        log.write(f'Refresh exited with code {result}.\n'.encode('ascii'))
        return result
    except OSError as error:
        # Keep authentication URLs and configuration contents out of launcher errors.
        code = error.winerror if hasattr(error, 'winerror') else error.errno
        log.write(f'Unable to start or log refresh (OS error {code}). Check project setup and write access.\n'.encode('ascii'))
        return 1


if __name__ == '__main__':
    sys.exit(main())
