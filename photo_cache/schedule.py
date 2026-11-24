"""Inspect and control the app's existing, configuration-owned Windows task."""

import json
import os
import subprocess
from pathlib import Path

from .runtime import resource_dir
from .connection_status import local_date


def task_command(config_path: Path, mode: str) -> list[str]:
    return ['powershell.exe', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
            '-File', str(resource_dir() / 'scripts' / 'Install-Task.ps1'),
            '-ConfigPath', str(config_path), '-Mode', mode]


def read_schedule(config_path: Path) -> dict:
    try:
        result = subprocess.run(task_command(config_path, 'Status'), capture_output=True,
                                encoding='utf-8', errors='replace', timeout=20,
                                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        if result.returncode:
            return {'state': 'unknown'}
        data = json.loads(result.stdout)
        return data if isinstance(data, dict) else {'state': 'unknown'}
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return {'state': 'unknown'}


def schedule_text(data: dict) -> str:
    if data.get('state') == 'on':
        next_run = local_date(data.get('next_run'))
        return 'Hourly downloads: ON · Next scheduled run: ' + (next_run or 'Waiting for Windows to schedule a run')
    if data.get('state') == 'off':
        return 'Hourly downloads: OFF · Use Download photos now, or turn hourly downloads on.'
    if data.get('state') == 'other_config':
        return 'Hourly schedule belongs to another configuration. It has been left unchanged.'
    return 'Hourly downloads: Could not read the Windows schedule. Retrying automatically…'
