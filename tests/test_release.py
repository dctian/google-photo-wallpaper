import contextlib
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from photo_cache.__main__ import main
from photo_cache.config import default_data


class ReleaseTests(unittest.TestCase):
    def test_default_data_is_per_user_and_not_a_developer_machine_path(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {'LOCALAPPDATA':folder}):
            data=default_data()
            self.assertEqual(Path(data['cache_dir']),Path(folder)/'GooglePhotosWallpaper'/'cache')
            self.assertEqual(Path(data['profile_dir']),Path(folder)/'GooglePhotosWallpaper'/'browser')
            self.assertEqual(data['albums'],[])

    def test_version_does_not_need_configuration_or_google(self):
        with patch('photo_cache.__main__.GooglePhotosSource') as source, contextlib.redirect_stdout(io.StringIO()) as output:
            with self.assertRaises(SystemExit) as done:
                main(['--version'])
        self.assertEqual(done.exception.code,0)
        self.assertIn('google-photo-wallpaper 0.1.0',output.getvalue())
        source.assert_not_called()


if __name__=='__main__':
    unittest.main()
