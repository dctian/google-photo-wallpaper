"""Offline format and failure tests; these never launch a browser or use Google."""

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from photo_cache.source import (
    GooglePhotosSource, LoginRequired, SourceError, _album_key, _albums_page,
    _decode_rpc, _image_url, _native_browser_executable, _prepare_profile, login,
)


def item(key, *, video=False, motion=False):
    details = {}
    if video:
        details["76647426"] = [0]
    if motion:
        details["146008172"] = [None, 1500]
    return [key, ["https://lh3.googleusercontent.com/test-" + key, 4000, 3000],
            12345678, "dedup-" + key, 0, 12345678, details]


def page(album_id, rows, count, token=None, metadata=True):
    detail = [None] * 22
    detail[0] = album_id
    detail[21] = count
    return [None, rows, token, detail if metadata else None]


class FakeSource(GooglePhotosSource):
    def __init__(self, pages, **kwargs):
        super().__init__("unused-profile", **kwargs)
        self._rpc = Mock(side_effect=pages)

    @staticmethod
    def _payloads():
        return SimpleNamespace(
            GetAlbumPage=lambda key, **kw: SimpleNamespace(key=key, **kw),
            GetAlbumsPage=lambda **kw: SimpleNamespace(**kw),
        )


class SourceTests(unittest.TestCase):
    def test_pagination_filters_video_and_keeps_motion_still(self):
        source = FakeSource([
            page("album", [item("photo"), item("video", video=True)], 3, "next"),
            page("album", [item("motion", motion=True)], 3, metadata=False),
        ])
        result = source.list_photos(["https://photos.google.com/album/album"])
        self.assertEqual([p.id for p in result], ["photo", "motion"])
        self.assertTrue(all(p.url.endswith("=w3840-h2160") for p in result))
        self.assertEqual(result[0].taken_at_ms, 12345678)
        self.assertEqual(result[0].timezone_offset_ms, 0)
        self.assertEqual(source._rpc.call_args_list[1].args[0].page_id, "next")

    def test_capture_time_preserves_capture_offset_and_missing_values(self):
        dated = item("dated")
        dated[2] = 1604212200000
        dated[4] = -25200000
        missing = item("missing")
        missing[2] = missing[4] = None
        photos = FakeSource([page("a", [dated, missing], 2)]).list_photos(
            ["https://photos.google.com/album/a"])
        self.assertEqual(photos[0].taken_at_ms, 1604212200000)
        self.assertEqual(photos[0].timezone_offset_ms, -25200000)
        self.assertIsNone(photos[1].taken_at_ms)
        self.assertIsNone(photos[1].timezone_offset_ms)

    def test_capture_metadata_rejects_unknown_schema(self):
        for position, value in ((2, "2020-10-31"), (2, True), (4, "-07:00"), (4, 86400000)):
            row = item("bad-date")
            row[position] = value
            with self.subTest(position=position, value=value), self.assertRaises(SourceError):
                FakeSource([page("a", [row], 1)]).list_photos(["https://photos.google.com/album/a"])

    def test_deduplicates_across_albums(self):
        source = FakeSource([
            page("a", [item("same")], 1), page("b", [item("same")], 1),
        ])
        result = source.list_photos(["https://photos.google.com/album/a", "https://photos.google.com/album/b"])
        self.assertEqual(len(result), 1)

    def test_valid_empty_album(self):
        source = FakeSource([page("a", None, 0)])
        self.assertEqual(source.list_photos(["https://photos.google.com/album/a"]), [])

    def test_missing_page_is_rejected(self):
        source = FakeSource([page("a", [item("one")], 2)])
        with self.assertRaisesRegex(SourceError, "declared size"):
            source.list_photos(["https://photos.google.com/album/a"])

    def test_changed_count_is_rejected(self):
        source = FakeSource([
            page("a", [item("one")], 2, "next"),
            page("a", [item("two")], 3),
        ])
        with self.assertRaisesRegex(SourceError, "changed while"):
            source.list_photos(["https://photos.google.com/album/a"])

    def test_repeated_token_is_rejected(self):
        source = FakeSource([
            page("a", [item("one")], 3, "same-token"),
            page("a", [item("two")], 3, "same-token"),
        ])
        with self.assertRaisesRegex(SourceError, "repeated a page"):
            source.list_photos(["https://photos.google.com/album/a"])

    def test_pagination_cannot_silently_repeat_items(self):
        source = FakeSource([
            page("a", [item("one")], 2, "next"),
            page("a", [item("one")], 2),
        ])
        with self.assertRaisesRegex(SourceError, "repeated an item"):
            source.list_photos(["https://photos.google.com/album/a"])

    def test_unknown_shape_or_inaccessible_album_is_not_empty_success(self):
        for data in ([None, None], [None, None, None], [None, [], None, ["a"]]):
            with self.subTest(data=data), self.assertRaises(SourceError):
                FakeSource([data]).list_photos(["https://photos.google.com/album/a"])

    def test_safety_page_limit(self):
        source = FakeSource([page("a", [item("one")], 2, "next")], max_pages=1)
        with self.assertRaisesRegex(SourceError, "safety limit"):
            source.list_photos(["https://photos.google.com/album/a"])

    def test_album_list_parsing(self):
        row = ["album", None, {"72930366": [None, "Family", None, 42]}]
        albums, token = _albums_page([[row], "page-two"], 0)
        self.assertEqual(albums[0].title, "Family")
        self.assertEqual(albums[0].item_count, 42)
        self.assertEqual(token, "page-two")
        with self.assertRaises(SourceError):
            _albums_page([[row[:-1]], None], 0)

    def test_live_three_page_album_list_shape_ends_with_empty_array(self):
        # Sanitized structural fixture from the live account: page lengths 4,
        # 2, 0; item counts 1, 60, 0. No account data appears in this fixture.
        def album_row(index):
            return [f"album-{index}", None, {"72930366": [None, f"Album {index}", None, index]}]
        source = FakeSource([
            [[album_row(0)], "page-two", None, None],
            [[album_row(index) for index in range(1, 61)], "page-three"],
            [],
        ])
        result = source.list_albums()
        self.assertEqual(len(result), 61)
        self.assertEqual(source._rpc.call_count, 3)
        self.assertEqual(source._rpc.call_args_list[2].args[0].page_id, "page-three")

    def test_album_list_omitted_token_and_malformed_types(self):
        row = ["album", None, {"72930366": [None, "Family", None, 42]}]
        self.assertEqual(_albums_page([[row]], 0)[1], None)
        self.assertEqual(_albums_page([], 0), ([], None))
        for invalid in (["not-rows"], [[row], 42], [["not-an-album"]],
                        [[["album", {"72930366": [None, "Family", None, "42"]}]]]):
            with self.subTest(invalid=invalid), self.assertRaises(SourceError):
                _albums_page(invalid, 0)

    def test_album_contents_empty_terminal_page_keeps_count_validation(self):
        source = FakeSource([page("a", [item("one")], 1, "terminal"), []])
        self.assertEqual(len(source.list_photos(["https://photos.google.com/album/a"])), 1)
        short = FakeSource([page("a", [item("one")], 2, "terminal"), []])
        with self.assertRaisesRegex(SourceError, "declared size"):
            short.list_photos(["https://photos.google.com/album/a"])

    def test_later_album_content_page_may_omit_token_and_metadata(self):
        source = FakeSource([page("a", [item("one")], 2, "last"), [None, [item("two")]]])
        self.assertEqual(len(source.list_photos(["https://photos.google.com/album/a"])), 2)
        with self.assertRaises(SourceError):
            FakeSource([[]]).list_photos(["https://photos.google.com/album/a"])

    def test_validates_private_urls_and_account(self):
        self.assertEqual(_album_key("https://photos.google.com/u/0/album/a", 0), "a")
        for url in ("https://photos.app.goo.gl/a", "http://photos.google.com/album/a",
                    "https://photos.google.com.evil.example/album/a", "https://photos.google.com/u/1/album/a"):
            with self.subTest(url=url), self.assertRaises(SourceError):
                _album_key(url, 0)

    def test_image_urls_use_only_google_image_hosts_without_crop(self):
        self.assertEqual(_image_url("https://lh3.googleusercontent.com/image=w100-h100-c", 1920, 1080),
                         "https://lh3.googleusercontent.com/image=w1920-h1080")
        for url in ("https://googleusercontent.com.evil.example/image", "http://lh3.googleusercontent.com/image",
                    "https://lh3.googleusercontent.com:443/image", "https://lh3.googleusercontent.com/image?token=secret"):
            with self.subTest(url=url), self.assertRaises(SourceError):
                _image_url(url, 1920, 1080)

    def test_rpc_decoder_verifies_requested_response(self):
        record = ["wrb.fr", "snAcKc", json.dumps([None, [], None]), None, None, None, "request"]
        body = ")]}'\n100\n" + json.dumps([record, ["di", 12]]) + "\n"
        self.assertEqual(_decode_rpc(body, "snAcKc", "request"), [None, [], None])
        for invalid in (body.replace('"request"', '"other"'), "<html>sign in secret</html>",
                        json.dumps([record, record])):
            with self.subTest(body=invalid), self.assertRaises(SourceError) as exc:
                _decode_rpc(invalid, "snAcKc", "request")
            self.assertNotIn("secret", str(exc.exception))

    def test_refuses_an_existing_non_dedicated_profile(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / "Cookies").write_text("private")
            with self.assertRaises(SourceError):
                _prepare_profile(path)

    def test_creates_and_reuses_own_profile(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "dedicated"
            self.assertEqual(_prepare_profile(path), path)
            (path / "Cookies").write_text("private")
            self.assertEqual(_prepare_profile(path), path)

    def test_profile_refuses_symlink_in_ancestor_or_marker(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            path = parent / "profile"
            for linked in (parent, path / ".photo-cache-profile"):
                with self.subTest(linked=linked), patch.object(
                        Path, "is_symlink", autospec=True, side_effect=lambda part: part == linked):
                    with self.assertRaisesRegex(SourceError, "symbolic links"):
                        _prepare_profile(path)

    def test_auth_failure_silently_renews_once(self):
        source = GooglePhotosSource("unused")
        payload = SimpleNamespace(rpcid="snAcKc", payload_id="request", data=["album"])
        body = json.dumps([["wrb.fr", "snAcKc", json.dumps([None, [], None]), None, None, None, "request"]])
        expired = Mock(status=401)
        success = Mock(status=200)
        success.text.return_value = body
        browser_page = Mock()
        source._context = SimpleNamespace(pages=[browser_page], request=Mock())
        source._context.request.post.side_effect = [expired, success]
        source._globals = {"SNlM0e": "old", "FdrFJe": "session", "cfb2h": "build", "Im6cmf": "/_/PhotosUi"}
        source._read_auth = Mock(return_value=source._globals | {"SNlM0e": "renewed"})
        self.assertEqual(source._rpc(payload), [None, [], None])
        self.assertEqual(source._context.request.post.call_count, 2)
        browser_page.goto.assert_called_once()
        self.assertEqual(source._context.request.post.call_args.kwargs["form"]["at"], "renewed")

    def test_auth_retry_is_bounded_and_does_not_expose_tokens(self):
        source = GooglePhotosSource("unused")
        payload = SimpleNamespace(rpcid="snAcKc", payload_id="request", data=["album"])
        source._context = SimpleNamespace(request=Mock())
        source._context.request.post.side_effect = [Mock(status=403), Mock(status=403)]
        source._globals = {"SNlM0e": "secret", "FdrFJe": "session", "cfb2h": "build", "Im6cmf": "/_/PhotosUi"}
        source._refresh_auth = Mock()
        with self.assertRaises(LoginRequired) as error:
            source._rpc(payload)
        self.assertNotIn("secret", str(error.exception))
        source._refresh_auth.assert_called_once()
        self.assertEqual(source._context.request.post.call_count, 2)

    def test_mutating_rpc_blocked_before_transport(self):
        source = GooglePhotosSource("unused")
        with self.assertRaisesRegex(SourceError, "read-only"):
            source._rpc(SimpleNamespace(rpcid="delete-everything"))

    def test_native_login_uses_only_normal_browser_flags_then_verifies(self):
        profile = Path(tempfile.gettempdir()) / "dedicated-login-test"
        with patch("photo_cache.source.GooglePhotosSource") as source_class, \
                patch("photo_cache.source._native_browser_executable", return_value=Path("C:/browser.exe")), \
                patch("photo_cache.source._prepare_profile", return_value=profile), \
                patch("photo_cache.source.subprocess.Popen") as launch, patch("builtins.print"):
            source = source_class.return_value
            source._home_url = "https://photos.google.com/u/0/"
            launch.return_value.wait.return_value = 0
            source.__enter__.side_effect = lambda: self.assertTrue(launch.return_value.wait.called)
            login(profile)
            self.assertEqual(launch.call_args.args[0], [
                str(Path("C:/browser.exe")), f"--user-data-dir={profile}",
                "--no-first-run", "--no-default-browser-check", source._home_url])
            self.assertFalse(launch.call_args.kwargs["shell"])
            launch.return_value.wait.assert_called_once_with(timeout=600)
            source.__enter__.assert_called_once()
            source.__exit__.assert_called_once()
            source._open.assert_not_called()

    def test_native_login_timeout_does_not_kill_browser(self):
        with patch("photo_cache.source.GooglePhotosSource") as source_class, \
                patch("photo_cache.source._native_browser_executable", return_value=Path("C:/browser.exe")), \
                patch("photo_cache.source._prepare_profile", return_value=Path("C:/dedicated")), \
                patch("photo_cache.source.subprocess.Popen") as launch, patch("builtins.print"):
            source_class.return_value._home_url = "https://photos.google.com/u/0/"
            launch.return_value.wait.side_effect = subprocess.TimeoutExpired("browser", 600)
            with self.assertRaisesRegex(LoginRequired, "still open"):
                login("unused")
            launch.return_value.kill.assert_not_called()
            launch.return_value.terminate.assert_not_called()
            source_class.return_value.__enter__.assert_not_called()

    def test_native_browser_search_checks_standard_installed_path(self):
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / "Google/Chrome/Application/chrome.exe"
            executable.parent.mkdir(parents=True)
            executable.touch()
            with patch.dict("os.environ", {"PROGRAMFILES": directory}, clear=True), \
                    patch("photo_cache.source.shutil.which", return_value=None):
                self.assertEqual(_native_browser_executable("chrome"), executable)

    def test_headless_reader_keeps_chromium_sandbox_enabled(self):
        with tempfile.TemporaryDirectory() as directory, \
                patch("playwright.sync_api.sync_playwright") as playwright:
            source = GooglePhotosSource(Path(directory) / "profile")
            source._open(headless=True)
            launch = playwright.return_value.start.return_value.chromium.launch_persistent_context
            self.assertTrue(launch.call_args.kwargs["chromium_sandbox"])
            self.assertTrue(launch.call_args.kwargs["headless"])
            self.assertNotIn("args", launch.call_args.kwargs)
            source.close()


if __name__ == "__main__":
    unittest.main()
