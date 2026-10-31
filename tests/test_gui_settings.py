import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
import sys
from unittest.mock import Mock, patch

from photo_cache.config import default_data, load_config
from photo_cache.gui import WallpaperApp, _write_config


class Value:
    def __init__(self,value):
        self.value=value
    def get(self):
        return self.value
    def set(self,value):
        self.value=value


class GuiSettingsTests(unittest.TestCase):
    def make_app(self,folder):
        app=object.__new__(WallpaperApp)
        app.config_path=Path(folder)/'config.json'
        data=default_data()|{'cache_dir':str(Path(folder)/'cache'),'profile_dir':str(Path(folder)/'browser'),
            'albums':['https://photos.google.com/album/saved'], 'batch_size':17, 'windows_wallpaper':True}
        app.config_path.write_text(json.dumps(data),encoding='utf-8')
        app.config=load_config(app.config_path)
        app.busy=False
        app.dirty=True
        app.wallpaper_dirty=True
        app.wallpaper_layout=Value('collage')
        app.wallpaper_photos=Value('30')
        app.wallpaper_minutes=Value('7')
        app.root=Mock()
        app.status=Value('')
        return app

    def test_wallpaper_settings_preserve_downloader_values_and_unsaved_album_draft(self):
        with tempfile.TemporaryDirectory() as folder:
            app=self.make_app(folder)
            app.selected_ids={'unsaved-album'}
            self.assertTrue(app._save_wallpaper_settings())
            data=json.loads(app.config_path.read_text(encoding='utf-8'))
            self.assertEqual(data['albums'],['https://photos.google.com/album/saved'])
            self.assertEqual(data['batch_size'],17)
            self.assertEqual((data['wallpaper_photos_per_image'],data['wallpaper_interval_minutes']),(30,7))
            self.assertTrue(app.dirty)
            self.assertFalse(app.wallpaper_dirty)

    def test_invalid_wallpaper_count_keeps_saved_settings(self):
        with tempfile.TemporaryDirectory() as folder:
            app=self.make_app(folder)
            original=app.config_path.read_bytes()
            app.wallpaper_photos=Value('0')
            with patch('photo_cache.gui.messagebox.showerror') as error:
                self.assertFalse(app._save_wallpaper_settings())
            error.assert_called_once()
            self.assertEqual(app.config_path.read_bytes(),original)

    def test_refresh_dispatches_local_rotation_without_saving_or_downloading(self):
        with tempfile.TemporaryDirectory() as folder:
            app=self.make_app(folder)
            app._save=Mock(side_effect=AssertionError('Must not save downloader drafts'))
            app._save_wallpaper_settings=Mock(side_effect=AssertionError('Must not save wallpaper drafts'))
            app._python=lambda:'python.exe'
            app._run_process=Mock()
            app._start=lambda label,work:work()
            app._refresh_wallpaper()
            self.assertEqual(app._run_process.call_args.args[0],
                ['python.exe','-m','photo_cache','--config',str(app.config_path),'wallpaper-next'])
            self.assertTrue(app.dirty)
            self.assertTrue(app.wallpaper_dirty)

    def test_busy_refresh_does_not_start_an_overlapping_action(self):
        with tempfile.TemporaryDirectory() as folder:
            app=self.make_app(folder)
            app.busy=True
            app._start=Mock()
            app._refresh_wallpaper()
            app._start.assert_not_called()

    def test_tray_refresh_routes_to_same_action_without_showing_window(self):
        app=object.__new__(WallpaperApp)
        app._refresh_wallpaper=Mock()
        app._restore_window=Mock()
        self.assertTrue(app._handle_tray_event('tray_refresh'))
        app._refresh_wallpaper.assert_called_once()
        app._restore_window.assert_not_called()

    def test_tray_menu_refresh_posts_the_refresh_event(self):
        from photo_cache.tray import _create_icon
        class Menu:
            SEPARATOR=object()
            def __init__(self,*items):
                self.items=items
        backend=SimpleNamespace(Menu=Menu,
            MenuItem=lambda label,action,**kwargs:SimpleNamespace(text=label,action=action),
            Icon=lambda *args,**kwargs:SimpleNamespace(menu=kwargs['menu']))
        post=Mock()
        with patch.dict(sys.modules,{'pystray':backend}):
            icon=_create_icon(post)
        item=next(item for item in icon.menu.items if getattr(item,'text','')=='Refresh wallpaper')
        item.action(icon,item)
        post.assert_called_once_with('tray_refresh')

    def test_retired_settings_are_ignored_on_load_and_removed_on_save(self):
        with tempfile.TemporaryDirectory() as folder:
            app=self.make_app(folder)
            data=json.loads(app.config_path.read_text(encoding='utf-8'))
            data.update(aesthetic_filter=True,aesthetic_min_score=5)
            app.config_path.write_text(json.dumps(data),encoding='utf-8')
            self.assertFalse(hasattr(load_config(app.config_path),'aesthetic_filter'))
            _write_config(app.config_path,data)
            saved=json.loads(app.config_path.read_text(encoding='utf-8'))
            self.assertNotIn('aesthetic_filter',saved)
            self.assertNotIn('aesthetic_min_score',saved)


if __name__=='__main__':
    unittest.main()
