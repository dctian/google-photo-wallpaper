"""The narrowly allowed Google Photos image CDN hosts.

The FIFE host was observed in authenticated album responses in October 2026.
It is an exact host allowance, not permission to fetch arbitrary google.com.
"""


def is_google_photos_image_host(host: str) -> bool:
    return host.endswith(".googleusercontent.com") or host == "photos.fife.usercontent.google.com"
