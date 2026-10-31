import io
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from PIL import Image

from photo_cache.cache import Cache
from photo_cache.config import Config, default_data, load_config, ConfigError
from photo_cache.wallpapers import compose, generate_wallpapers, rotate_wallpaper
from photo_cache.windows_wallpaper import WallpaperError


class WallpaperTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.config = Config(self.root / 'cache', self.root / 'browser')
        cache = Cache(self.config)
        cache.open()
        self.photos = []
        for n, color in enumerate(('red', 'green', 'blue', 'white')):
            key = f'{n:064x}'
            path = cache.photos / f'{key}.jpg'
            Image.new('RGB', (100, 200), color).save(path)
            self.photos.append(path)
            cache.state['items'][key] = {'version':'1', 'selected':float(n), 'bytes':path.stat().st_size}
        cache.save()

    def tearDown(self):
        self.temporary.cleanup()

    def generate(self, apply=False):
        return generate_wallpapers(self.config, apply=apply, size=(640, 480), report=lambda _:None)

    def test_portrait_photo_is_fitted_without_crop_or_stretch(self):
        result = compose(self.photos[:1], (640, 480), 'single')
        self.assertEqual(result.size, (640, 480))
        self.assertEqual(result.getpixel((0, 0)), (24,32,39))
        self.assertGreater(result.getpixel((320, 240))[0], 240)
        self.assertEqual(result.getpixel((50,240)), (24,32,39))

    def test_collage_contains_all_four_photos(self):
        import random
        from photo_cache.photo_pile import compose_photo_pile
        result = compose_photo_pile(self.photos, (640,480), rng=random.Random(42))
        colors=result.getcolors(640*480)
        for path in self.photos:
            with Image.open(path) as source:
                color=source.getpixel((50,100))
            self.assertGreater(sum(count for count, value in colors if value==color),500)

    def test_generation_is_local_and_bounded_and_keeps_active_during_previews(self):
        with patch('photo_cache.wallpapers.set_wallpaper_all') as enable:
            active = self.generate(True)
            enable.assert_called_once_with(active/'wallpaper-00.jpg')
            preview = self.generate()
            another = self.generate()
        self.assertTrue(active.exists())
        self.assertFalse(preview.exists())
        self.assertTrue(another.exists())
        self.assertEqual(len(list(another.parent.glob('generation-*'))),2)
        self.assertEqual(len(list(another.glob('*.jpg'))),4)
        self.assertEqual(len(list((self.config.cache_dir/'photos').glob('*.jpg'))),4)

    def test_native_failure_retains_previous_images_and_removes_new_stage(self):
        old = self.generate()
        with patch('photo_cache.wallpapers.set_wallpaper_all', side_effect=WallpaperError('Unavailable')):
            with self.assertRaises(WallpaperError):
                self.generate(True)
        self.assertTrue(old.exists())
        self.assertEqual(len(list(old.parent.glob('generation-*'))),1)
        manifest=json.loads((old.parent/'current.json').read_text())
        self.assertEqual(manifest['generation'],old.name)

    def test_unowned_output_folder_is_never_adopted(self):
        output=self.root/'wallpapers'
        output.mkdir()
        personal=output/'personal.txt'
        personal.write_text('Keep me')
        with self.assertRaises(WallpaperError):
            self.generate()
        self.assertEqual(personal.read_text(),'Keep me')

    def test_config_validates_native_mode(self):
        config_path=self.root/'config.json'
        for invalid in ({'windows_wallpaper':'yes'}, {'wallpaper_layout':'unknown'}, {'wallpaper_interval_minutes':0}):
            config_path.write_text(json.dumps(default_data()|invalid))
            with self.assertRaises(ConfigError):
                load_config(config_path)

    def test_hourly_run_renews_wallpapers_without_google_when_download_quota_is_used(self):
        from photo_cache.__main__ import main
        from contextlib import redirect_stdout
        cache = Cache(self.config)
        cache.open()
        cache.state['download_attempts'] = [time.time()] * 50
        cache.save()
        config_path = self.root / 'config.json'
        config_path.write_text(json.dumps(default_data() | {
            'cache_dir':str(self.config.cache_dir), 'profile_dir':str(self.config.profile_dir),
            'albums':['https://photos.google.com/album/test'], 'windows_wallpaper':True,
        }))
        with patch('photo_cache.wallpapers.generate_wallpapers') as generate, \
                patch('photo_cache.__main__.GooglePhotosSource') as source, redirect_stdout(io.StringIO()):
            self.assertEqual(main(['--config',str(config_path),'refresh']),0)
        source.assert_not_called()
        generate.assert_called_once()
        self.assertTrue(generate.call_args.kwargs['apply'])

    def test_storage_failure_retains_previous_wallpaper_set(self):
        old=self.generate()
        with patch('photo_cache.wallpapers.MAX_GENERATION_BYTES',100):
            with self.assertRaises(WallpaperError):
                self.generate()
        self.assertTrue(old.exists())
        self.assertEqual(len(list(old.parent.glob('generation-*'))),1)

    def test_twenty_photos_all_appear_in_collage(self):
        import random
        from photo_cache.photo_pile import compose_photo_pile
        paths=[]
        for i in range(20):
            path=self.root/f'color-{i}.png'
            Image.new('RGB',(100,100),(i*10,20,30)).save(path)
            paths.append(path)
        output=compose_photo_pile(paths,(1000,800),rng=random.Random(99))
        # Even with print overlap, every distinctive photo must remain visible.
        colors=set(output.get_flattened_data())
        for i in range(20):
            self.assertIn((i*10,20,30),colors)

    def test_print_frames_and_source_aspect_ratios_are_preserved(self):
        import random
        from photo_cache.photo_pile import _plan, compose_photo_pile
        before={path:path.read_bytes() for path in self.photos}
        plans=_plan(self.photos,(1000,800),random.Random(15))
        for placement in plans:
            self.assertAlmostEqual(placement.width/placement.height,.5,delta=.01)
            self.assertTrue(-25<=placement.angle<=25)
        image=compose_photo_pile(self.photos,(1000,800),rng=random.Random(15))
        self.assertEqual(image.mode,'RGB')
        self.assertGreater(sum(count for count,color in image.getcolors(800000) if color==(255,255,255)),1000)
        self.assertEqual(before,{path:path.read_bytes() for path in self.photos})

    def test_loose_pile_has_size_angle_variety_and_clear_outer_margin(self):
        import math,random
        from photo_cache.photo_pile import _plan
        plan=_plan(self.photos*5,(1920,1080),random.Random(22))
        areas=[p.width*p.height for p in plan]
        self.assertGreater(max(areas)/min(areas),3)
        self.assertGreater(max(p.angle for p in plan)-min(p.angle for p in plan),30)
        for p in plan:
            angle=math.radians(abs(p.angle))
            bw=p.width*math.cos(angle)+p.height*math.sin(angle)
            bh=p.height*math.cos(angle)+p.width*math.sin(angle)
            self.assertGreaterEqual(p.x-bw/2,1920*.05)
            self.assertLessEqual(p.x+bw/2,1920*.95)
            self.assertGreaterEqual(p.y-bh/2,1080*.065)
            self.assertLessEqual(p.y+bh/2,1080*.935)

    def test_rotated_white_edges_have_smooth_alpha_and_no_dark_fringe(self):
        from photo_cache.photo_pile import _render_print
        card=_render_print(self.photos[0],240,360,17.3,6)
        alpha=card.getchannel('A')
        self.assertGreater(len(set(alpha.get_flattened_data())),64)
        edge=[pixel for pixel in card.get_flattened_data() if 15<pixel[3]<240]
        self.assertGreater(len(edge),300)
        self.assertGreater(sum(min(pixel[:3])>245 for pixel in edge)/len(edge),.98)

    def test_rotation_uses_local_images_once_per_cycle_and_applies_one_path_to_all_monitors(self):
        from dataclasses import replace
        with patch('photo_cache.wallpapers.set_wallpaper_all') as setter:
            folder=self.generate(True)
            config=replace(self.config,windows_wallpaper=True)
            for _ in range(3):
                rotate_wallpaper(config,report=lambda _:None)
            seen=[call.args[0] for call in setter.call_args_list]
            self.assertEqual(len(set(seen)),4)
            self.assertTrue(all(path.parent==folder for path in seen))
            rotate_wallpaper(config,report=lambda _:None)
            self.assertNotEqual(setter.call_args.args[0],seen[-1])


if __name__ == '__main__':
    unittest.main()
