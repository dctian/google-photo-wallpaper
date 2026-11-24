import json
from dataclasses import replace
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from photo_cache.config import default_data, load_config
from photo_cache.dashboard import reset_download_draft, reset_wallpaper_draft, reset_album_draft, sync


class Value:
    def __init__(self, value=''):
        self.value = value
    def get(self):
        return self.value
    def set(self, value):
        self.value = value


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        folder = Path(self.temporary.name)
        path = folder / 'config.json'
        path.write_text(json.dumps(default_data() | {'cache_dir':str(folder/'cache'),
            'profile_dir':str(folder/'browser'), 'albums':['https://photos.google.com/album/saved'],
            'windows_wallpaper':False}))
        self.app = SimpleNamespace(config_path=path, config=load_config(path), dirty=True, wallpaper_dirty=True,
            batch_size=Value('10'), max_photos=Value('100'), cache_mib=Value('200'), resolution=Value('1920 × 1080'),
            quality_filter=Value(False), anniversaries=Value(False), wallpaper_layout=Value('single'),
            wallpaper_photos=Value('7'), wallpaper_minutes=Value('90'), selected_ids={'draft'},
            album_tree=Mock(), album_rows={'row':{'id':'saved'}}, _update_selection=Mock())
        self.original = path.read_bytes()

    def tearDown(self):
        self.temporary.cleanup()

    def test_cancel_download_settings_discards_only_its_draft(self):
        reset_download_draft(self.app)
        self.assertEqual(self.app.batch_size.get(), str(self.app.config.batch_size))
        self.assertFalse(self.app.dirty)
        self.assertTrue(self.app.wallpaper_dirty)
        self.assertEqual(self.app.wallpaper_minutes.get(), '90')
        self.assertEqual(self.app.config_path.read_bytes(), self.original)

    def test_cancel_wallpaper_settings_preserves_download_draft_and_off_state(self):
        reset_wallpaper_draft(self.app)
        self.assertEqual(self.app.wallpaper_layout.get(), self.app.config.wallpaper_layout)
        self.assertFalse(self.app.wallpaper_dirty)
        self.assertEqual(self.app.batch_size.get(), '10')
        self.assertTrue(self.app.dirty)
        self.assertFalse(self.app.config.windows_wallpaper)
        self.assertEqual(self.app.config_path.read_bytes(), self.original)

    def test_cancel_album_selection_restores_saved_choices_without_writing(self):
        reset_album_draft(self.app)
        self.assertEqual(self.app.selected_ids, {'saved'})
        self.app.album_tree.set.assert_called_once_with('row', 'chosen', '✓')
        self.assertEqual(self.app.config_path.read_bytes(), self.original)

    def prepare_sync(self):
        self.app.dashboard_variables = {key:Value() for key in ('account','checked','next','last','collection','plan','wallpaper_plan','activity','detail')}
        for name in ('account_dot','schedule_badge','reconnect_button','download_button','schedule_button'):
            setattr(self.app, name, Mock())
        self.app._schedule_data = {'state':'on','next_run':'2026-11-24T12:00:00+00:00'}
        self.app._dashboard_state = {'items':{},'last_error':'Raw error ' * 1000,'last_attempt':'2026-11-23T12:00:00+00:00'}
        self.app._dashboard_downloading = False
        self.app.cache_status = Value('0 downloaded photos')
        self.app.download_status = Value('Idle')
        self.app.status = Value('Ready')
        self.app.busy = False
        self.app._refresh = Mock()
        self.app._sign_in = Mock()

    def test_historical_error_is_dated_and_does_not_replace_current_account_state(self):
        self.prepare_sync()
        with patch('photo_cache.dashboard.read_connection', return_value={'status':'signed_in'}):
            sync(self.app)
        variables = self.app.dashboard_variables
        self.assertEqual(variables['account'].get(), 'Google Photos connected')
        self.assertEqual(variables['activity'].get(), 'Ready for the next download')
        self.assertIn('Last run had an issue', variables['detail'].get())
        self.assertNotIn('Raw error', variables['detail'].get())

    def test_paused_schedule_and_busy_download_are_distinct(self):
        self.prepare_sync()
        self.app._schedule_data = {'state':'off'}
        with patch('photo_cache.dashboard.read_connection', return_value={}):
            sync(self.app)
            self.assertEqual(self.app.dashboard_variables['next'].get(), 'Paused')
            self.assertEqual(self.app.dashboard_variables['activity'].get(), 'Automatic downloads paused')
            self.app._dashboard_downloading = True
            self.app._dashboard_state = {'download_activity':{'phase':'downloading'}}
            self.app.download_status.set('Downloading photo 8 of 50')
            sync(self.app)
        self.assertEqual(self.app.dashboard_variables['activity'].get(), 'Downloading photos')
        self.assertEqual(self.app.download_button.configure.call_args.kwargs['state'], 'disabled')

    def test_first_run_prioritizes_sign_in_and_waits_for_photos_before_scheduling(self):
        self.prepare_sync()
        self.app.config = replace(self.app.config, albums=())
        self.app._schedule_data = {'state':'off'}
        self.app._dashboard_state = {'items':{}}
        with patch('photo_cache.dashboard.read_connection', return_value={}):
            sync(self.app)
        self.assertEqual(self.app.download_button.configure.call_args.kwargs['text'], 'Sign in to Google')
        self.assertIs(self.app.download_button.configure.call_args.kwargs['command'], self.app._sign_in)
        self.assertEqual(self.app.schedule_button.configure.call_args.kwargs['state'], 'disabled')
