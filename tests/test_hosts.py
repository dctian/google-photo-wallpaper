import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from photo_cache.cache import CacheError, download_photo
from photo_cache.hosts import is_google_photos_image_host
from photo_cache.source import SourceError, _image_url


class PhotoHostTests(unittest.TestCase):
    def test_only_exact_fife_host_is_added(self):
        self.assertTrue(is_google_photos_image_host("photos.fife.usercontent.google.com"))
        self.assertTrue(is_google_photos_image_host("lh3.googleusercontent.com"))
        for host in ("photos.fife.usercontent.google.com.evil.example", "other.google.com",
                     "evil.photos.fife.usercontent.google.com", "photos.fife.usercontent.google.com.",
                     "googleusercontent.com.evil.example", "evilgoogleusercontent.com"):
            with self.subTest(host=host):
                self.assertFalse(is_google_photos_image_host(host))

    def test_source_accepts_observed_fife_path_and_retains_restrictions(self):
        url = "https://photos.fife.usercontent.google.com/pw/example"
        self.assertEqual(_image_url(url, 3840, 2160), url + "=w3840-h2160")
        for bad in (url.replace("https:", "http:"), url.replace(".com/", ".com:443/"),
                    url.replace("https://", "https://name@"), url + "?secret=value",
                    url + "#fragment", url.replace("google.com", "google.com.evil.example"),
                    url.replace("photos.fife.usercontent.google.com", "other.google.com")):
            with self.subTest(url=bad), self.assertRaises(SourceError):
                _image_url(bad, 3840, 2160)

    def test_download_accepts_fife_and_checks_redirect_destination(self):
        response = MagicMock()
        response.__enter__.return_value = response
        response.is_redirect = False
        response.headers = {"Content-Type": "image/jpeg"}
        response.iter_content.return_value = [b"image-bytes"]
        photo = SimpleNamespace(url="https://photos.fife.usercontent.google.com/pw/example=w3840-h2160")
        settings = SimpleNamespace(max_download_bytes=100)
        with patch("requests.get", return_value=response) as get:
            self.assertEqual(download_photo(photo, settings), b"image-bytes")
            get.assert_called_once()
        response.is_redirect = True
        response.headers = {"Location": "https://other.google.com/picture"}
        with patch("requests.get", return_value=response) as get:
            with self.assertRaises(CacheError):
                download_photo(photo, settings)
            get.assert_called_once()

    def test_download_rejects_host_spoofing_userinfo_and_non_https_ports(self):
        for url in ("https://photos.fife.usercontent.google.com.evil.example/pw/test",
                    "https://other.google.com/pw/test", "http://photos.fife.usercontent.google.com/pw/test",
                    "https://name@photos.fife.usercontent.google.com/pw/test",
                    "https://photos.fife.usercontent.google.com:8443/pw/test",
                    "https://photos.fife.usercontent.google.com:invalid/pw/test"):
            with self.subTest(url=url), patch("requests.get") as get, self.assertRaises(CacheError):
                download_photo(SimpleNamespace(url=url), SimpleNamespace(max_download_bytes=100))
            get.assert_not_called()


if __name__ == "__main__":
    unittest.main()
