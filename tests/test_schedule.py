import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from photo_cache.schedule import read_schedule, schedule_text
from photo_cache.download_status import activity_text


class DownloadStatusTests(unittest.TestCase):
    def test_running_photo_counts_and_interrupted_run_are_distinct(self):
        state = {'download_activity': {'phase': 'downloading', 'current': 8,
                 'total': 50, 'completed': 7, 'added': 5, 'skipped': 1, 'failed': 1}}
        self.assertIn('photo 8 of 50', activity_text(state, True))
        self.assertIn('5 added · 1 skipped · 1 failed', activity_text(state, True))
        self.assertIn('stopped before finishing', activity_text(state, False))

    def test_album_enumeration_is_not_presented_as_downloads(self):
        self.assertIn('No photos are being downloaded yet', activity_text(
            {'download_activity': {'phase': 'reading_albums'}}, True))

    def test_schedule_read_does_not_modify_or_enable_task(self):
        with patch('photo_cache.schedule.subprocess.run') as run:
            run.return_value.returncode = 0
            run.return_value.stdout = json.dumps({'state': 'on', 'next_run': '2026-11-16T08:00:00Z'})
            data = read_schedule(Path('config.json'))
        self.assertEqual(run.call_args.args[0][-2:], ['-Mode', 'Status'])
        self.assertIn('Next scheduled run:', schedule_text(data))
        self.assertIn('OFF', schedule_text({'state': 'off'}))

    def test_failed_schedule_query_is_unknown_not_off(self):
        with patch('photo_cache.schedule.subprocess.run', side_effect=subprocess.TimeoutExpired('powershell', 20)):
            self.assertEqual(read_schedule(Path('config.json'))['state'], 'unknown')


@unittest.skipUnless(shutil.which('powershell.exe'), 'Requires Windows PowerShell')
class TaskControlTests(unittest.TestCase):
    def control(self, mode, foreign=False):
        with tempfile.TemporaryDirectory() as directory:
            wrapper = Path(directory) / 'control.ps1'
            wrapper.write_text('''param($Target, $ConfigPath, $Mode, [int]$Foreign)
$ErrorActionPreference = 'Stop'
$global:enabledCalls = 0
$global:disabledCalls = 0
$global:registrations = 0
$global:description = 'Google Photos wallpaper cache: ' + $ConfigPath
if ($Foreign) { $global:description = 'another configuration' }
function Get-ScheduledTask { param($TaskName, $TaskPath, $ErrorAction)
    [pscustomobject]@{ Description = $global:description; State = 'Ready'; Settings = @{ Enabled = $true } }
}
function Enable-ScheduledTask { param($InputObject) $global:enabledCalls++ }
function Disable-ScheduledTask { param($InputObject) $global:disabledCalls++ }
function Register-ScheduledTask { $global:registrations++; throw 'Must not recreate existing task' }
$failure = $false
try { 1..3 | ForEach-Object { & $Target -ConfigPath $ConfigPath -Mode $Mode | Out-Null } }
catch { $failure = $true }
@{ enabled = $global:enabledCalls; disabled = $global:disabledCalls;
   registrations = $global:registrations; failed = $failure } | ConvertTo-Json -Compress
''', encoding='utf-8')
            result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-File', str(wrapper),
                '-Target', str(Path(__file__).resolve().parents[1] / 'scripts' / 'Install-Task.ps1'),
                '-ConfigPath', str(Path(directory) / 'config.json'), '-Mode', mode, '-Foreign', str(int(foreign))],
                capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr)
            return json.loads(result.stdout)

    def test_repeated_enable_never_registers_or_resets_existing_task(self):
        self.assertEqual(self.control('On'), {'enabled': 3, 'disabled': 0, 'registrations': 0, 'failed': False})

    def test_pause_preserves_task_for_resuming(self):
        self.assertEqual(self.control('Off'), {'enabled': 0, 'disabled': 3, 'registrations': 0, 'failed': False})

    def test_another_config_cannot_be_paused_or_enabled(self):
        for mode in ('On', 'Off'):
            data = self.control(mode, foreign=True)
            self.assertTrue(data['failed'])
            self.assertEqual((data['enabled'], data['disabled'], data['registrations']), (0, 0, 0))
