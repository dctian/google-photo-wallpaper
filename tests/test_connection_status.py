import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from photo_cache.connection_status import (
    connection_text, latest_download, local_date, read_connection, record_connection,
)
from photo_cache.source import GooglePhotosSource, LoginRequired, SourceError


class ConnectionStatusTests(unittest.TestCase):
    def test_legacy_cache_uses_photo_publication_not_successful_batch(self):
        self.assertEqual(latest_download({'last_success': None, 'items': {
            'a': {'selected': 1700000000}, 'b': {'selected': 1700001000}}}),
            local_date(1700001000))
        self.assertEqual(latest_download({'last_success': '2026-11-15T00:00:00+00:00'}), 'Not yet')

    def test_explicit_last_download_survives_empty_or_rotated_cache(self):
        stamp = '2026-11-15T12:00:00+00:00'
        self.assertEqual(latest_download({'last_download_at': stamp, 'items': {}}), local_date(stamp))

    def test_source_persists_verified_login_and_mid_operation_expiry(self):
        with tempfile.TemporaryDirectory() as folder:
            profile = Path(folder)
            (profile / '.photo-cache-profile').write_text('marker')
            source = GooglePhotosSource(profile)
            page = Mock()
            source._context = Mock(pages=[page])
            with patch.object(source, '_open'), patch.object(source, '_read_auth', return_value={}), \
                    patch.object(source, 'close'):
                with self.assertRaises(LoginRequired):
                    with source:
                        signed = read_connection(profile)
                        self.assertEqual(signed['status'], 'signed_in')
                        raise LoginRequired('Expired')
            expired = read_connection(profile)
            self.assertEqual(expired['status'], 'sign_in_required')
            self.assertEqual(expired['verified_at'], signed['verified_at'])
            self.assertIn('click Sign in to Google', connection_text(expired))

    def test_network_failure_is_not_reported_as_signed_out(self):
        with tempfile.TemporaryDirectory() as folder:
            profile = Path(folder)
            (profile / '.photo-cache-profile').write_text('marker')
            source = GooglePhotosSource(profile)
            with patch.object(source, '_open', side_effect=SourceError('Offline')), \
                    patch.object(source, 'close'):
                with self.assertRaises(SourceError):
                    with source:
                        pass
            status = read_connection(profile)
            self.assertEqual(status['status'], 'check_failed')
            self.assertIn('Could not check', connection_text(status))

    def test_status_write_failure_does_not_change_authentication_result(self):
        with tempfile.TemporaryDirectory() as folder:
            profile = Path(folder)
            (profile / '.photo-cache-profile').write_text('marker')
            with patch('photo_cache.connection_status.os.replace', side_effect=OSError('Read only')):
                record_connection(profile, 'signed_in')
            self.assertEqual(list(profile.glob('.connection-*')), [])

    def test_missing_or_corrupt_status_is_unknown(self):
        with tempfile.TemporaryDirectory() as folder:
            profile = Path(folder)
            self.assertEqual(read_connection(profile), {})
            (profile / '.wallpaper-connection.json').write_text('bad json')
            self.assertEqual(read_connection(profile), {})
            self.assertIn('not checked', connection_text({}))

    def test_no_credentials_or_error_details_are_stored(self):
        with tempfile.TemporaryDirectory() as folder:
            profile = Path(folder)
            (profile / '.photo-cache-profile').write_text('marker')
            record_connection(profile, 'signed_in')
            self.assertEqual(set(read_connection(profile)), {'status', 'checked_at', 'verified_at'})


if __name__ == '__main__':
    unittest.main()
