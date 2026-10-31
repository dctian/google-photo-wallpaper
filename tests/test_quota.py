import contextlib
import io
import json
import tempfile
import time
import unittest
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

from PIL import Image

from photo_cache.__main__ import main
from photo_cache.cache import Cache, CacheError
from photo_cache.config import Config, ConfigError, default_data, load_config
from photo_cache.source import RemotePhoto


def jpeg(color="red"):
    output = io.BytesIO()
    Image.new("RGB", (32, 24), color).save(output, "JPEG")
    return output.getvalue()


class QuotaTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.config = Config(self.root / "cache", self.root / "browser", quality_filter=False)
        self.cache = Cache(self.config)
        self.cache.open()
        self.photos = [RemotePhoto(str(i), "unused", 32, 24) for i in range(120)]
        self.fetch = Mock(return_value=jpeg())

    def tearDown(self):
        self.temp.cleanup()

    def refresh(self):
        return self.cache.refresh(self.photos, fetch=self.fetch, report=lambda _: None)

    def test_first_run_and_restarts_share_fifty_attempt_limit(self):
        with patch("photo_cache.cache.time.time", return_value=10000):
            first = self.refresh()
            self.assertEqual((first.downloaded, first.attempts, first.photos), (50, 50, 50))
            self.assertTrue(first.deferred)
            self.assertEqual(self.fetch.call_count, 50)
            before = {path: path.read_bytes() for path in self.cache.photos.iterdir()}
            self.cache = Cache(self.config)
            self.cache.open()
            self.assertEqual(self.cache.quota_status().remaining, 0)
            second = self.refresh()
            self.assertTrue(second.deferred)
            self.assertEqual(second.attempts, 0)
            self.assertEqual(self.fetch.call_count, 50)
            self.assertEqual(before, {path: path.read_bytes() for path in self.cache.photos.iterdir()})
        with patch("photo_cache.cache.time.time", return_value=13600):
            third = self.refresh()
            self.assertEqual(third.attempts, 50)
            self.assertEqual(self.fetch.call_count, 100)

    def test_window_is_rolling_and_smaller_batch_is_honored(self):
        self.cache.config = replace(self.config, batch_size=25)
        with patch("photo_cache.cache.time.time", return_value=1000):
            self.assertEqual(self.refresh().attempts, 25)
        with patch("photo_cache.cache.time.time", return_value=1100):
            self.assertEqual(self.refresh().attempts, 25)
        self.assertEqual(self.cache.quota_status(4599).remaining, 0)
        self.assertEqual(self.cache.quota_status(4600).remaining, 25)
        self.assertEqual(self.cache.quota_status(4699).remaining, 25)
        self.assertEqual(self.cache.quota_status(4700).remaining, 50)

    def test_rejected_and_failed_photos_consume_the_same_budget(self):
        for filtered in (False, True):
            with self.subTest(filtered=filtered):
                self.cache = Cache(replace(self.config, cache_dir=self.root / str(filtered), quality_filter=filtered))
                self.cache.open()
                self.fetch = Mock(return_value=jpeg("white")) if filtered else Mock(side_effect=CacheError("offline"))
                result = self.refresh()
                self.assertEqual(result.attempts, 50)
                self.assertEqual(result.downloaded, 0)
                self.assertTrue(result.deferred)
                self.assertEqual(self.fetch.call_count, 50)
                self.assertEqual(self.cache.quota_status().remaining, 0)
                self.assertEqual(len(json.loads(self.cache.state_file.read_text())["download_attempts"]), 50)

    def test_attempt_is_durable_before_network_even_if_process_is_interrupted(self):
        def interrupted(*_):
            saved = json.loads(self.cache.state_file.read_text())
            self.assertEqual(len(saved["download_attempts"]), 1)
            self.assertEqual(len(saved["attempts"]), 1)
            raise KeyboardInterrupt
        self.fetch = Mock(side_effect=interrupted)
        with self.assertRaises(KeyboardInterrupt):
            self.refresh()
        reopened = Cache(self.config)
        reopened.open()
        self.assertEqual(reopened.quota_status().used, 1)
        self.assertEqual(self.fetch.call_count, 1)

    def test_reservation_failure_prevents_network(self):
        real_save = self.cache.save
        calls = 0
        def fail_reservation():
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("disk unavailable")
            real_save()
        with patch.object(self.cache, "save", side_effect=fail_reservation), self.assertRaisesRegex(CacheError, "reserve"):
            self.refresh()
        self.fetch.assert_not_called()

    def test_exhausted_quota_does_not_consume_remote_iterator(self):
        self.cache.state["download_attempts"] = [time.time()] * 50
        def should_not_scan():
            raise AssertionError("remote scan must not happen")
            yield
        result = self.cache.refresh(should_not_scan(), fetch=self.fetch, report=lambda _: None)
        self.assertTrue(result.deferred)
        self.fetch.assert_not_called()

    def test_legacy_interrupted_fill_is_preserved_and_conservatively_deferred(self):
        self.cache.config = replace(self.config, batch_size=2)
        self.refresh()
        before = {path: path.read_bytes() for path in self.cache.photos.iterdir()}
        del self.cache.state["download_attempts"]
        self.cache.state["last_success"] = None
        self.cache.state["last_attempt"] = datetime.now(timezone.utc).isoformat()
        self.cache.state["last_error"] = "Previous interrupted refresh"
        self.cache.save()
        reopened = Cache(self.config)
        reopened.open()
        self.assertEqual(reopened.quota_status().remaining, 0)
        self.assertEqual(len(reopened.state["download_attempts"]), 50)
        self.assertEqual(before, {path: path.read_bytes() for path in reopened.photos.iterdir()})
        self.assertIsNone(reopened.state["last_success"])

    def test_cli_skips_browser_and_album_scan_when_quota_is_exhausted(self):
        self.cache.state["download_attempts"] = [time.time()] * 50
        self.cache.state["last_attempt"] = "unchanged"
        self.cache.save()
        config_path = self.root / "config.json"
        config_path.write_text(json.dumps(default_data() | {
            "cache_dir": str(self.config.cache_dir), "profile_dir": str(self.config.profile_dir),
            "albums": ["https://photos.google.com/album/selected"],
        }))
        with patch("photo_cache.__main__.GooglePhotosSource") as source, \
                contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(["--config", str(config_path), "refresh"]), 0)
        source.assert_not_called()
        self.assertIn("Hourly photo allowance used", output.getvalue())
        self.assertEqual(json.loads(self.cache.state_file.read_text())["last_attempt"], "unchanged")

    def test_config_disallows_batches_above_fifty(self):
        config_path = self.root / "config.json"
        config_path.write_text(json.dumps(default_data() | {"batch_size": 51}))
        with self.assertRaises(ConfigError):
            load_config(config_path)

    def test_malformed_ledger_is_not_silently_reset(self):
        self.cache.state["download_attempts"] = ["not a timestamp"]
        self.cache.save()
        with self.assertRaises(CacheError):
            Cache(self.config).open()


if __name__ == "__main__":
    unittest.main()
