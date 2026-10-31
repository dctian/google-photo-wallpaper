import contextlib
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

from photo_cache.__main__ import config_fingerprint, main, show_status
from photo_cache.cache import Cache
from photo_cache.config import default_data, load_config
from photo_cache.source import LoginRequired, RemotePhoto, _PROFILE_MARKER


class StatusTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.config_path = self.root / 'config.json'
        values = default_data() | {
            'cache_dir': str(self.root / 'cache'),
            'profile_dir': str(self.root / 'browser'),
            'albums': ['https://photos.google.com/album/test-album'],
            'quality_filter': False,
        }
        self.config_path.write_text(json.dumps(values))
        self.config = load_config(self.config_path)
        self.cache = Cache(self.config)
        self.cache.open()
        buffer = io.BytesIO()
        Image.new('RGB', (40, 30), 'red').save(buffer, 'JPEG')
        photos = [RemotePhoto(key, '', 40, 30) for key in ('a', 'b')]
        self.cache.refresh(photos, fetch=lambda *_: buffer.getvalue(), report=lambda _: None)
        self.cache.state['config_fingerprint'] = config_fingerprint(self.config)
        self.cache.save()

    def tearDown(self):
        self.temp.cleanup()

    def status(self, config=None):
        with contextlib.redirect_stdout(io.StringIO()):
            return show_status(config or self.config, True)

    def test_ready_cache_is_accepted(self):
        self.assertEqual(self.status(), 0)

    def test_incomplete_attempt_is_not_ready(self):
        self.cache.state['last_attempt'] = (datetime.now(timezone.utc) + timedelta(seconds=1)).isoformat()
        self.cache.save()
        self.assertEqual(self.status(), 1)

    def test_staging_or_unmanaged_files_are_not_ready_and_are_not_deleted(self):
        for path in (self.cache.root / 'pending.jpg', self.cache.photos / ('f' * 64 + '.jpg')):
            with self.subTest(path=path.name):
                path.write_bytes(b'x')
                self.assertEqual(self.status(), 1)
                self.assertTrue(path.exists())
                path.unlink()
        self.assertEqual(self.status(), 0)

    def test_missing_owner_or_exceeded_limits_are_not_ready(self):
        marker = self.cache.root / '.owner'
        marker.unlink()
        self.assertEqual(self.status(), 1)
        marker.write_text(Cache.MARKER)
        lowered = replace(self.config, max_photos=1)
        self.cache.state['config_fingerprint'] = config_fingerprint(lowered)
        self.cache.save()
        self.assertEqual(self.status(lowered), 1)

    def test_auth_failure_retains_photos_but_invalidates_readiness(self):
        before = {path: path.read_bytes() for path in self.cache.photos.iterdir()}
        with patch('photo_cache.__main__.GooglePhotosSource') as source, contextlib.redirect_stdout(
            io.StringIO()
        ), contextlib.redirect_stderr(io.StringIO()):
            source.return_value.__enter__.side_effect = LoginRequired('Sign in again.')
            self.assertEqual(main(['--config', str(self.config_path), 'refresh']), 1)
        self.assertEqual(before, {path: path.read_bytes() for path in self.cache.photos.iterdir()})
        self.assertEqual(self.status(), 1)
        saved = json.loads(self.cache.state_file.read_text())
        self.assertEqual(saved['last_error'], 'Sign in again.')

    def test_interrupted_collection_is_schedulable_without_faking_success(self):
        self.config.profile_dir.mkdir()
        (self.config.profile_dir / _PROFILE_MARKER).write_text('Dedicated profile')
        self.cache.state['last_success'] = None
        self.cache.state['last_error'] = 'Previous refresh was interrupted.'
        self.cache.state.pop('config_fingerprint', None)
        self.cache.save()
        before = self.cache.state_file.read_bytes()
        with patch('photo_cache.__main__.GooglePhotosSource') as source, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(['--config', str(self.config_path), 'status', '--require-schedulable']), 0)
            source.assert_not_called()
        self.assertEqual(before, self.cache.state_file.read_bytes())
        self.assertEqual(self.status(), 1)

    def test_schedule_preflight_requires_profile_albums_and_intact_cache(self):
        def schedulable(config):
            with contextlib.redirect_stdout(io.StringIO()):
                return show_status(config, False, True)
        self.assertEqual(schedulable(self.config), 1)
        self.config.profile_dir.mkdir()
        (self.config.profile_dir / _PROFILE_MARKER).write_text('Dedicated profile')
        self.assertEqual(schedulable(self.config), 0)
        self.assertEqual(schedulable(replace(self.config, albums=())), 1)
        next(self.cache.photos.iterdir()).unlink()
        self.assertEqual(schedulable(self.config), 1)

    def test_refresh_downloads_inside_authenticated_browser_context(self):
        picture = io.BytesIO()
        Image.new('RGB', (40, 30), 'blue').save(picture, 'JPEG')
        active = False
        calls = []

        class Source:
            def __enter__(self):
                nonlocal active
                active = True
                return self

            def __exit__(self, *_):
                nonlocal active
                active = False

            def list_photos(self, _):
                return [RemotePhoto('new-photo', '', 40, 30)]

            def download_photo(self, photo, config):
                if not active:
                    raise AssertionError('Browser closed before authenticated image download')
                calls.append(photo.id)
                return picture.getvalue()

        with patch('photo_cache.__main__.GooglePhotosSource', return_value=Source()), \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(['--config', str(self.config_path), 'refresh']), 0)
        self.assertEqual(calls, ['new-photo'])
        self.assertFalse(active)
        self.assertEqual(self.status(), 0)


if __name__ == '__main__':
    unittest.main()
