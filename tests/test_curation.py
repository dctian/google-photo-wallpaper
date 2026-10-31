import io
import json
import unittest
from datetime import date, datetime, timezone
from types import SimpleNamespace

from PIL import Image, ImageDraw

from photo_cache.curation import (
    _anniversary_distance, _capture_date, analyze_image, near_duplicate, rank_candidates,
)
from photo_cache.source import RemotePhoto


def photo(key, when=None, width=4000, height=3000, offset=0):
    stamp = int(datetime.fromisoformat(when).replace(tzinfo=timezone.utc).timestamp() * 1000) if when else None
    return RemotePhoto(key, "unused", width, height, taken_at_ms=stamp, timezone_offset_ms=offset)


def config(**overrides):
    values = dict(batch_size=100, anniversary_fraction=0.3, anniversary_window_days=7,
                  quality_filter=True, min_long_edge=1600, min_short_edge=720,
                  max_width=3840, max_height=2160)
    return SimpleNamespace(**(values | overrides))


def encoded(image, quality=90):
    output = io.BytesIO()
    image.save(output, "JPEG", quality=quality)
    return output.getvalue()


def patterned_image(color="white"):
    image = Image.new("RGB", (240, 160), color)
    draw = ImageDraw.Draw(image)
    for index in range(12):
        x = (index * 37) % 210
        y = (index * 29) % 130
        draw.rectangle((x, y, x + 25, y + 25), fill="black")
    return image


class CurationTests(unittest.TestCase):
    def test_first_batch_has_anniversary_quota_without_losing_candidates(self):
        anniversaries = [(f"a{i}", photo(f"a{i}", "2020-10-31")) for i in range(60)]
        general = [(f"g{i}", photo(f"g{i}", "2020-04-12")) for i in range(140)]
        source = anniversaries + general
        result = rank_candidates(source, {}, config(), date(2026, 10, 31))
        self.assertEqual(sum(key.startswith("a") for key, _ in result[:100]), 30)
        self.assertEqual(sum(key.startswith("a") for key, _ in result[100:]), 30)
        self.assertEqual(len(result), 200)
        self.assertEqual({key for key, _ in result}, {key for key, _ in source})
        self.assertEqual(source, anniversaries + general)

    def test_small_anniversary_pool_backfills_general_pool(self):
        candidates = [("a", photo("a", "2020-10-31"))]
        candidates += [(f"g{i}", photo(f"g{i}")) for i in range(110)]
        result = rank_candidates(candidates, {}, config(), date(2026, 10, 31))
        self.assertEqual(len(result[:100]), 100)
        self.assertEqual(sum(key == "a" for key, _ in result[:100]), 1)

    def test_all_anniversary_or_all_general_still_returns_everything(self):
        for when in (None, "2020-10-31"):
            candidates = [(str(i), photo(str(i), when)) for i in range(151)]
            result = rank_candidates(candidates, {}, config(), date(2026, 10, 31))
            self.assertEqual(len(result), 151)
            self.assertEqual(len({key for key, _ in result}), 151)

    def test_unseen_then_least_recent_and_low_resolution_remains_eligible(self):
        candidates = [("recent", photo("recent")), ("old", photo("old")),
                      ("new-low", photo("new-low", width=100, height=100)),
                      ("new-high", photo("new-high"))]
        result = rank_candidates(candidates, {"recent": 200, "old": 100},
                                 config(anniversary_fraction=0), date(2026, 10, 31))
        self.assertEqual([key for key, _ in result], ["new-high", "new-low", "old", "recent"])

    def test_exact_anniversary_precedes_nearby_with_equal_history(self):
        candidates = [("near", photo("near", "2020-10-28")), ("exact", photo("exact", "2020-10-31"))]
        result = rank_candidates(candidates, {}, config(anniversary_fraction=1), date(2026, 10, 31))
        self.assertEqual([key for key, _ in result], ["exact", "near"])

    def test_anniversary_wrap_and_leap_day(self):
        self.assertEqual(_anniversary_distance(photo("a", "2020-12-31"), date(2026, 1, 1)), 1)
        self.assertEqual(_anniversary_distance(photo("a", "2020-01-01"), date(2026, 12, 31)), 1)
        self.assertEqual(_anniversary_distance(photo("a", "2020-02-29"), date(2026, 2, 28)), 0)
        self.assertEqual(_anniversary_distance(photo("a", "2020-02-29"), date(2024, 2, 29)), 0)
        self.assertIsNone(_anniversary_distance(photo("a", "2026-10-31"), date(2026, 10, 31)))

    def test_capture_timezone_preserves_local_date(self):
        original = photo("a", "2020-11-01T02:30:00", offset=-7 * 3600 * 1000)
        self.assertEqual(_capture_date(original), date(2020, 10, 31))
        self.assertEqual(_anniversary_distance(original, date(2026, 10, 31)), 0)

    def test_missing_dates_are_not_invented(self):
        self.assertIsNone(_capture_date(photo("missing")))
        self.assertIsNone(_anniversary_distance(photo("missing"), date(2026, 10, 31)))

    def test_image_analysis_is_normalized_and_serializable(self):
        result = analyze_image(encoded(patterned_image()))
        json.dumps(result, allow_nan=False)
        self.assertEqual(len(result["dhash"]), 16)
        self.assertTrue(result["hash_reliable"])
        self.assertFalse(result["low_quality"])

    def test_near_duplicate_detects_reencoded_picture(self):
        image = patterned_image()
        first = analyze_image(encoded(image, quality=95))
        second = analyze_image(encoded(image, quality=85))
        self.assertTrue(near_duplicate(first, second))

    def test_flat_images_do_not_collide(self):
        gray = analyze_image(encoded(Image.new("RGB", (100, 100), (120, 120, 120))))
        white = analyze_image(encoded(Image.new("RGB", (100, 100), "white")))
        black = analyze_image(encoded(Image.new("RGB", (100, 100), "black")))
        self.assertFalse(gray["hash_reliable"])
        self.assertFalse(gray["low_quality"])
        self.assertTrue(black["low_quality"])
        self.assertTrue(white["low_quality"])
        self.assertFalse(near_duplicate(gray, white))
        self.assertFalse(near_duplicate(white, black))
        self.assertFalse(near_duplicate("0000000000000000", "0000000000000000"))

    def test_colored_scenes_with_same_pattern_are_distinguished(self):
        first = analyze_image(encoded(patterned_image("red")))
        second = analyze_image(encoded(patterned_image("green")))
        self.assertFalse(near_duplicate(first, second))

    def test_hamming_threshold_and_malformed_hashes(self):
        value = int("0f0f0f0f0f0f0f0f", 16)
        self.assertTrue(near_duplicate(f"{value:016x}", f"{value ^ 7:016x}"))
        self.assertFalse(near_duplicate(f"{value:016x}", f"{value ^ 15:016x}"))
        self.assertFalse(near_duplicate({}, {}))
        self.assertFalse(near_duplicate("not-a-hash", "not-a-hash"))


if __name__ == "__main__":
    unittest.main()
