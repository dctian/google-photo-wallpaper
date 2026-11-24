import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from photo_cache.logs import BoundedLog, LOG_LIMIT, append_app_log, log_directory, read_log


class LogTests(unittest.TestCase):
    def test_viewer_includes_previous_log_and_converts_headers_without_changing_files(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            old = '[2026-11-24T06:13:59+00:00] refresh started.\nEarlier run\n'
            new = '[2026-11-24T07:13:59+00:00] refresh started.\nCurrent run\n'
            (folder / 'task.log.1').write_text(old)
            (folder / 'task.log').write_text(new)
            result = read_log(folder, 'task.log')
            self.assertLess(result.index('Earlier run'), result.index('Current run'))
            self.assertIn('refresh started.', result)
            self.assertNotIn('T07:13:59+00:00', result)
            self.assertEqual((folder / 'task.log').read_text(), new)

    def test_missing_log_is_explained_and_arbitrary_paths_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertIn('No entries yet', read_log(Path(directory), 'task.log'))
            with self.assertRaises(ValueError):
                read_log(Path(directory), '../config.json')

    def test_app_actions_are_redacted_and_logging_failure_is_nonfatal(self):
        with tempfile.TemporaryDirectory() as directory, patch('photo_cache.logs.log_directory', return_value=Path(directory)):
            append_app_log(Path(directory) / 'config.json', 'Failed https://photos.google.com/private-token')
            text = (Path(directory) / 'app.log').read_text()
            self.assertIn('[private URL]', text)
            self.assertNotIn('private-token', text)
            with patch('photo_cache.logs.BoundedLog.write', side_effect=PermissionError('blocked')):
                append_app_log(Path(directory) / 'config.json', 'Nonfatal failure')

    def test_log_directory_matches_source_and_installed_task_layouts(self):
        with patch('photo_cache.logs.frozen', return_value=True):
            self.assertEqual(log_directory(Path('user/config.json')), Path('user/config.json').absolute().parent / '.state')
        with patch('photo_cache.logs.frozen', return_value=False), patch('photo_cache.logs.application_dir', return_value=Path('project')):
            self.assertEqual(log_directory(Path('user/config.json')), Path('project/.state'))
