"""Private, credential-free sign-in observations shared by GUI and tasks."""

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from .cache import CacheError, safe_path


def read_connection(profile: Path) -> dict:
    try:
        path = Path(profile) / '.wallpaper-connection.json'
        safe_path(path)
        data = json.loads(path.read_text(encoding='utf-8'))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError, CacheError):
        return {}


def record_connection(profile: Path, status: str) -> None:
    """Caller holds the profile operation lock; never affect a download on failure."""
    temporary = None
    try:
        profile = Path(profile)
        safe_path(profile)
        if not (profile / '.photo-cache-profile').is_file():
            return
        data = read_connection(profile)
        stamp = datetime.now(timezone.utc).isoformat(timespec='seconds')
        data = {'status': status, 'checked_at': stamp,
                'verified_at': stamp if status == 'signed_in' else data.get('verified_at')}
        path = profile / '.wallpaper-connection.json'
        safe_path(path)
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=profile,
                                         prefix='.connection-', delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(data, stream)
        os.replace(temporary, path)
    except (OSError, CacheError):
        pass
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass


def local_date(value) -> str | None:
    try:
        stamp = (datetime.fromtimestamp(value, timezone.utc)
                 if type(value) in (int, float) else datetime.fromisoformat(value))
        return stamp.astimezone().strftime('%b %d, %Y, %I:%M %p')
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def connection_text(data: dict) -> str:
    checked = local_date(data.get('checked_at'))
    suffix = f' · Checked {checked}' if checked else ''
    if data.get('status') == 'signed_in':
        return 'Google: Signed in' + suffix
    if data.get('status') == 'sign_in_required':
        return 'Google: Sign-in required — click Sign in to Google' + suffix
    if data.get('status') == 'check_failed':
        return 'Google: Could not check sign-in · Check your connection and try again' + suffix
    return 'Google: Sign-in not checked yet'


def latest_download(state: dict) -> str:
    """Legacy caches already record the publication time of every photo."""
    stamp = local_date(state.get('last_download_at'))
    if stamp:
        return stamp
    dates = [item.get('selected') for item in state.get('items', {}).values()
             if isinstance(item, dict) and type(item.get('selected')) in (int, float)]
    return (local_date(max(dates)) if dates else None) or 'Not yet'
