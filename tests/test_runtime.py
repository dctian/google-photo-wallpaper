import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from photo_cache import runtime
from photo_cache.cache import Cache
from photo_cache.config import default_data, load_config


class RuntimeTests(unittest.TestCase):
    def test_installed_paths_use_current_user_and_executable_not_build_directory(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {'LOCALAPPDATA':folder}), \
                patch.object(sys,'frozen',True,create=True), \
                patch.object(sys,'executable',str(Path(folder)/'Programs'/'App'/'GooglePhotoWallpaper.exe')):
            self.assertEqual(runtime.default_config_path(),Path(folder)/'GooglePhotosWallpaper'/'config.json')
            self.assertEqual(runtime.command(['refresh']),[str(Path(folder)/'Programs'/'App'/'GooglePhotoWallpaper-cli.exe'),'refresh'])

    def test_resource_paths_and_source_commands_are_distinct_from_private_data(self):
        with patch.object(sys,'frozen',False,create=True):
            self.assertEqual(runtime.command(['status'],python='python.exe'),['python.exe','-m','photo_cache','status'])
            self.assertEqual(runtime.default_config_path(),runtime.application_dir()/'config.json')
        with tempfile.TemporaryDirectory() as folder, patch.object(sys,'frozen',True,create=True), \
                patch.object(sys,'_MEIPASS',folder,create=True):
            self.assertEqual(runtime.resource_dir(),Path(folder))

    def test_redirected_refresh_handles_unicode_paths_without_google(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)/'\u65c5\u9014'
            root.mkdir()
            config=root/'config.json'
            config.write_text(json.dumps(default_data()|{'cache_dir':str(root/'cache'),
                'profile_dir':str(root/'browser'),'albums':['https://photos.google.com/album/mock']}),encoding='utf-8')
            cache=Cache(load_config(config))
            cache.open()
            cache.state['download_attempts']=[time.time()]*50
            cache.save()
            child=subprocess.run([sys.executable,'-m','photo_cache','--config',str(config),'refresh'],
                stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                env={**os.environ,'PYTHONIOENCODING':'cp1252'},timeout=30)
            self.assertEqual(child.returncode,0,child.stdout.decode('utf-8',errors='replace'))
            self.assertIn(str(cache.photos),child.stdout.decode('utf-8'))


if __name__=='__main__':
    unittest.main()
