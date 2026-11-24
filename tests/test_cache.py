import io
import json
import os
import tempfile
import unittest
import contextlib
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from photo_cache.cache import Cache, CacheError, file_lock, wallpaper_jpeg
from photo_cache.config import Config, ConfigError, load_config
from photo_cache.source import RemotePhoto


def jpeg(color="red", size=(100, 80)):
    stream = io.BytesIO()
    Image.new("RGB", size, color).save(stream, "JPEG")
    return stream.getvalue()


class CacheTests(unittest.TestCase):
    def test_permanent_windows_lock_stops_after_bounded_retries_with_error_code(self):
        blocked = PermissionError('Do not expose arbitrary exception detail')
        blocked.winerror = 32
        with patch('photo_cache.cache.os.replace', side_effect=blocked) as rename, \
                patch('photo_cache.cache.time.sleep'), contextlib.redirect_stdout(io.StringIO()), \
                self.assertRaisesRegex(CacheError, 'Windows error 32') as error:
            self.cache.activity('downloading')
        self.assertEqual(rename.call_count, 6)
        self.assertNotIn('arbitrary exception', str(error.exception))

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.config = Config(self.root / "cache", self.root / "browser", max_photos=3,
                             batch_size=2, quality_filter=False, anniversary_fraction=0)
        self.cache = Cache(self.config)
        self.cache.open()

    def tearDown(self):
        self.temp.cleanup()

    def photos(self, *keys):
        return [RemotePhoto(key, "https://lh3.googleusercontent.com/test", 100, 80) for key in keys]

    def refresh(self, *keys, fetch=None):
        return self.cache.refresh(self.photos(*keys), fetch=fetch or (lambda *_: jpeg()), report=lambda _: None)

    def test_rotation_limits_and_no_early_repeats(self):
        first = self.refresh("a", "b", "c", "d", "e", "f")
        self.assertEqual(first.downloaded, 2)
        first_keys = set(self.cache.state["history"])
        second = self.refresh("a", "b", "c", "d", "e", "f")
        self.assertEqual(second.photos, 3)
        self.assertEqual(len(self.cache.state["history"]), 4)
        self.assertTrue(first_keys <= set(self.cache.state["history"]))
        self.assertEqual(len(list(self.cache.photos.glob("*.jpg"))), 3)
        self.assertLessEqual(second.bytes, self.config.max_bytes)

    def test_last_download_is_retained_when_later_batch_is_interrupted(self):
        calls = 0
        def fetch(*_):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise KeyboardInterrupt()
            return jpeg()
        with self.assertRaises(KeyboardInterrupt):
            self.refresh('a', 'b', fetch=fetch)
        saved = json.loads((self.config.cache_dir / 'state.json').read_text())
        self.assertTrue(saved['last_download_at'])
        self.assertIsNone(saved['last_success'])
        self.assertEqual(len(saved['items']), 1)

    def test_live_progress_and_final_counts_include_failed_attempts(self):
        seen = []
        def fetch(*_):
            saved = json.loads(self.cache.state_file.read_text())
            seen.append(saved['download_activity'].copy())
            if len(seen) == 1:
                raise CacheError('Offline')
            return jpeg()
        result = self.refresh('a', 'b', fetch=fetch)
        self.assertEqual((result.downloaded, result.failed), (1, 1))
        self.assertEqual((seen[0]['current'], seen[0]['completed']), (1, 0))
        self.assertEqual((seen[1]['current'], seen[1]['completed'], seen[1]['failed']), (2, 1, 1))
        final = json.loads(self.cache.state_file.read_text())['download_activity']
        self.assertEqual((final['phase'], final['completed'], final['added'], final['failed']), ('finished', 2, 1, 1))

    def test_batch_larger_than_cache_does_not_evict_its_own_downloads(self):
        self.cache.config = replace(self.config, max_photos=2, batch_size=10)
        result = self.refresh("a", "b", "c", "d", "e")
        self.assertEqual(result.downloaded, 2)
        self.assertEqual(len(self.cache.state["history"]), 2)

    def test_staging_and_publication_never_exceed_byte_cap(self):
        self.cache.config = replace(self.config, max_photos=5, batch_size=1,
                                    max_bytes=1000, max_image_bytes=400)
        real_replace = os.replace
        observed = []
        def track_replace(source, destination):
            paths = list(self.cache.photos.glob('*.jpg')) + [self.cache.root / 'pending.jpg']
            observed.append(sum(path.stat().st_size for path in paths if path.exists()))
            return real_replace(source, destination)
        with patch('photo_cache.cache.wallpaper_jpeg', return_value=b'x' * 300), patch(
            'photo_cache.curation.analyze_image', return_value={}
        ), patch('photo_cache.cache.os.replace', side_effect=track_replace):
            first = self.refresh('a', 'b', 'c', 'd', 'e', 'f')
            second = self.refresh('a', 'b', 'c', 'd', 'e', 'f')
        self.assertEqual(first.downloaded, 1)
        self.assertEqual(second.downloaded, 1)
        self.assertEqual(second.photos, 2)
        self.assertLessEqual(max(observed), 1000)
        self.assertFalse((self.cache.root / 'pending.jpg').exists())

    def test_filtered_candidates_do_not_starve_other_photos(self):
        self.cache.config = replace(self.config, max_photos=1, batch_size=1, quality_filter=True)
        candidates = [RemotePhoto(f'blank{i}', '', 4000, 3000) for i in range(12)]
        candidates.append(RemotePhoto('good', '', 1000, 500))
        fetch = lambda photo, _: jpeg('red' if photo.id == 'good' else 'white')
        for _ in range(12):
            with self.assertRaises(CacheError):
                self.cache.refresh(candidates, fetch=fetch, report=lambda _: None)
        self.assertEqual(len(self.cache.state['attempts']), 12)
        self.assertEqual(len(self.cache.state['history']), 0)
        result = self.cache.refresh(candidates, fetch=fetch, report=lambda _: None)
        self.assertEqual(result.downloaded, 1)
        self.assertEqual(len(self.cache.state['history']), 1)

    def test_filtered_replacements_retain_existing_collection(self):
        self.refresh('a', 'b')
        before = set(self.cache.photos.iterdir())
        self.cache.config = replace(self.config, quality_filter=True)
        result = self.refresh('a', 'c', fetch=lambda *_: jpeg('white'))
        self.assertEqual(result.downloaded, 0)
        self.assertTrue(self.cache.state['last_error'])
        self.assertEqual(before, set(self.cache.photos.iterdir()))
        with self.assertRaises(CacheError):
            self.refresh('d', fetch=lambda *_: jpeg('white'))
        self.assertEqual(before, set(self.cache.photos.iterdir()))

    def test_empty_scan_retains_all_photos(self):
        self.refresh("a", "b")
        before = set(self.cache.photos.iterdir())
        with self.assertRaises(CacheError):
            self.refresh()
        self.assertEqual(before, set(self.cache.photos.iterdir()))

    def test_failed_replacements_do_not_prune_old_members(self):
        self.refresh("a", "b")
        before = set(self.cache.photos.iterdir())
        def fail(*_):
            raise CacheError("offline")
        result = self.refresh("a", "c", "d", fetch=fail)
        self.assertEqual(result.downloaded, 0)
        self.assertEqual(result.failed, 2)
        self.assertEqual(before, set(self.cache.photos.iterdir()))

    def test_failure_to_publish_keeps_previous_files(self):
        self.cache.config = replace(self.config, max_photos=2)
        self.refresh("a", "b")
        before = set(self.cache.photos.iterdir())
        real_save = self.cache.save
        def fail_new_state():
            if any(self.cache.photos / f'{key}.jpg' not in before for key in self.cache.state['items']):
                raise OSError("disk failure")
            real_save()
        with patch.object(self.cache, "save", side_effect=fail_new_state):
            with self.assertRaises(CacheError):
                self.refresh("c", "d")
        self.assertEqual(before, set(self.cache.photos.iterdir()))
        reloaded = Cache(self.config)
        reloaded.open()
        self.assertEqual(len(reloaded.state["items"]), 2)

    def test_source_edit_redownloads_same_identity(self):
        self.refresh("a")
        changed = [replace(self.photos("a")[0], version="changed")]
        result = self.cache.refresh(changed, fetch=lambda *_: jpeg("blue"), report=lambda _: None)
        self.assertEqual(result.downloaded, 1)
        self.assertEqual(result.photos, 1)

    def test_foreign_folder_is_never_adopted(self):
        other = self.root / "personal"
        other.mkdir()
        source = other / "original.jpg"
        source.write_bytes(jpeg())
        with self.assertRaises(CacheError):
            Cache(replace(self.config, cache_dir=other)).open()
        self.assertTrue(source.exists())

    def test_foreign_file_inside_cache_fails_before_cleanup(self):
        path = self.cache.photos / "personal.jpg"
        path.write_bytes(jpeg())
        with self.assertRaises(CacheError):
            Cache(self.config).open()
        self.assertTrue(path.exists())

    def test_image_sizing_and_bad_payload(self):
        data = wallpaper_jpeg(jpeg(size=(1000, 500)), replace(self.config, max_width=400, max_height=300))
        self.assertEqual(Image.open(io.BytesIO(data)).size, (400, 200))
        with self.assertRaises(CacheError):
            wallpaper_jpeg(b"<html>sign in</html>", self.config)

    def test_process_lock(self):
        with file_lock(self.root / "test.lock"):
            with self.assertRaises(CacheError):
                with file_lock(self.root / "test.lock"):
                    self.fail("lock was acquired twice")

    def test_relative_paths_and_bad_settings(self):
        config_path = self.root / "config.json"
        config_path.write_text(json.dumps({"cache_dir": "local", "profile_dir": "browser"}))
        self.assertEqual(load_config(config_path).cache_dir, self.root / "local")
        config_path.write_text(json.dumps({"max_bytes": 1}))
        with self.assertRaises(ConfigError):
            load_config(config_path)


if __name__ == "__main__":
    unittest.main()
