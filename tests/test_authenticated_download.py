import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from photo_cache.source import GooglePhotosSource, LoginRequired, RemotePhoto, SourceError


def response(status=200, data=b"jpeg", headers=None):
    value = Mock(status=status, headers=headers or {"content-type": "image/jpeg"})
    value.body.return_value = data
    return value


class AuthenticatedDownloadTests(unittest.TestCase):
    def setUp(self):
        self.source = GooglePhotosSource("unused-profile")
        self.browser_request = Mock()
        self.source._context = SimpleNamespace(request=self.browser_request)
        self.photo = RemotePhoto("id", "https://photos.fife.usercontent.google.com/pw/private-photo", 100, 100)
        self.config = SimpleNamespace(max_download_bytes=100)

    def test_uses_existing_browser_request_cookie_jar_and_disposes(self):
        result = response()
        self.browser_request.get.return_value = result
        self.assertEqual(self.source.download_photo(self.photo, self.config), b"jpeg")
        self.browser_request.get.assert_called_once_with(
            self.photo.url, headers={"Referer": "https://photos.google.com/u/0/"},
            max_redirects=0, timeout=45000)
        result.dispose.assert_called_once()

    def test_each_redirect_is_checked_before_fetching(self):
        first = response(status=302, headers={"location": "https://other.google.com/private-photo"})
        self.browser_request.get.return_value = first
        with self.assertRaisesRegex(SourceError, "unsupported"):
            self.source.download_photo(self.photo, self.config)
        self.browser_request.get.assert_called_once()
        first.dispose.assert_called_once()

    def test_allowed_redirect_succeeds_and_both_responses_dispose(self):
        first = response(status=302, headers={"location": "https://lh3.googleusercontent.com/image"})
        second = response()
        self.browser_request.get.side_effect = [first, second]
        self.assertEqual(self.source.download_photo(self.photo, self.config), b"jpeg")
        self.assertEqual(self.browser_request.get.call_count, 2)
        first.dispose.assert_called_once()
        second.dispose.assert_called_once()

    def test_403_reports_safe_login_error(self):
        forbidden = response(status=403, data=b"private-url-secret")
        self.browser_request.get.return_value = forbidden
        with self.assertRaises(LoginRequired) as error:
            self.source.download_photo(self.photo, self.config)
        self.assertNotIn("private-photo", str(error.exception))
        self.assertNotIn("private-url-secret", str(error.exception))
        forbidden.body.assert_not_called()
        forbidden.dispose.assert_called_once()

    def test_declared_oversize_is_checked_before_requesting_body(self):
        large = response(headers={"content-type": "image/jpeg", "content-length": "101"})
        self.browser_request.get.return_value = large
        with self.assertRaisesRegex(SourceError, "size limit"):
            self.source.download_photo(self.photo, self.config)
        large.body.assert_not_called()
        large.dispose.assert_called_once()

    def test_actual_body_limit_is_checked_even_if_header_claims_smaller(self):
        large = response(data=b"x" * 101, headers={"content-type": "image/jpeg", "content-length": "10"})
        self.browser_request.get.return_value = large
        with self.assertRaisesRegex(SourceError, "size limit"):
            self.source.download_photo(self.photo, self.config)
        large.dispose.assert_called_once()

    def test_non_image_and_network_error_are_private(self):
        html = response(headers={"content-type": "text/html"})
        self.browser_request.get.return_value = html
        with self.assertRaisesRegex(SourceError, "not return an image"):
            self.source.download_photo(self.photo, self.config)
        html.body.assert_not_called()
        html.dispose.assert_called_once()
        self.browser_request.get.side_effect = RuntimeError("private-url-secret")
        with self.assertRaises(SourceError) as error:
            self.source.download_photo(self.photo, self.config)
        self.assertNotIn("private-url-secret", str(error.exception))

    def test_redirect_limit_is_bounded_and_all_responses_dispose(self):
        hops = [response(status=302, headers={"location": "/pw/loop"}) for _ in range(5)]
        self.browser_request.get.side_effect = hops
        with self.assertRaisesRegex(SourceError, "too many"):
            self.source.download_photo(self.photo, self.config)
        self.assertEqual(self.browser_request.get.call_count, 5)
        for hop in hops:
            hop.dispose.assert_called_once()


if __name__ == "__main__":
    unittest.main()
