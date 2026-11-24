import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from photo_cache.cache import Cache
from photo_cache.config import Config


class CacheLockingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        folder = Path(self.temporary.name)
        self.cache = Cache(Config(folder / 'cache', folder / 'browser'))
        self.cache.open()

    def tearDown(self):
        self.temporary.cleanup()

    def test_temporary_windows_lock_retries_same_state_without_extra_quota(self):
        real_replace = os.replace
        blocked = PermissionError('Temporary sharing conflict')
        blocked.winerror = 5
        replacements = 0
        def rename(source, target):
            nonlocal replacements
            replacements += 1
            if replacements < 3:
                raise blocked
            return real_replace(source, target)
        self.cache.state['download_attempts'] = [123.0]
        with patch('photo_cache.cache.os.replace', side_effect=rename), \
                patch('photo_cache.cache.time.sleep') as sleep, contextlib.redirect_stdout(io.StringIO()) as output:
            self.cache.save()
        self.assertEqual(replacements, 3)
        self.assertEqual(sleep.call_count, 2)
        self.assertEqual(json.loads(self.cache.state_file.read_text())['download_attempts'], [123.0])
        self.assertIn('saved after 2', output.getvalue())

    def test_permanent_windows_lock_preserves_error_after_bounded_retries(self):
        blocked = PermissionError('Temporary sharing conflict')
        blocked.winerror = 32
        before = self.cache.state_file.read_bytes()
        with patch('photo_cache.cache.os.replace', side_effect=blocked) as rename, \
                patch('photo_cache.cache.time.sleep'), contextlib.redirect_stdout(io.StringIO()), \
                self.assertRaises(PermissionError) as error:
            self.cache.save()
        self.assertEqual(rename.call_count, 6)
        self.assertEqual(error.exception.winerror, 32)
        self.assertEqual(self.cache.state_file.read_bytes(), before)
