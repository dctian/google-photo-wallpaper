# Third-party notices

The application source is MIT-licensed. Third-party dependencies retain their own licenses.
Source setup installs dependencies separately. Windows installer releases bundle
Python, Tcl/Tk, application dependencies, and the Playwright Node driver. Chrome
and JBS are not bundled. The installed `_internal/licenses` directory contains
the runtime inventory and notices, with additional upstream notices retained in
package metadata and the Playwright driver directory.
The following inventory describes the pinned, tested Windows dependency set; copied upstream license texts are under `third_party/licenses/`.

| Package | Version | License | Notices |
| --- | --- | --- | --- |
| certifi | 2026.10.23 | MPL-2.0 | [LICENSE](third_party/licenses/certifi/LICENSE) |
| charset-normalizer | 3.5.2 | MIT | [LICENSE](third_party/licenses/charset-normalizer/LICENSE) |
| gpwc | 0.1 | MIT | [LICENCE](third_party/licenses/gpwc/LICENCE) |
| greenlet | 3.5.6 | MIT AND PSF-2.0 | [LICENSE](third_party/licenses/greenlet/LICENSE), [LICENSE.PSF](third_party/licenses/greenlet/LICENSE.PSF) |
| idna | 3.20 | BSD-3-Clause | [LICENSE.md](third_party/licenses/idna/LICENSE.md) |
| lxml | 6.1.3 | BSD-3-Clause | [LICENSE.txt](third_party/licenses/lxml/LICENSE.txt), [LICENSES.txt](third_party/licenses/lxml/LICENSES.txt) |
| pillow | 13.0.0 | MIT-CMU | [LICENSE](third_party/licenses/pillow/LICENSE) |
| playwright | 1.64.1 | Apache-2.0 | [LICENSE](third_party/licenses/playwright/LICENSE) |
| pyee | 14.0.0 | MIT | [LICENSE](third_party/licenses/pyee/LICENSE) |
| pystray | 0.19.5 | LGPL-3.0-or-later | [COPYING](third_party/licenses/pystray/COPYING), [COPYING.LGPL](third_party/licenses/pystray/COPYING.LGPL) |
| requests | 2.34.2 | Apache-2.0 | [LICENSE](third_party/licenses/requests/LICENSE), [NOTICE](third_party/licenses/requests/NOTICE) |
| six | 1.17.0 | MIT | [LICENSE](third_party/licenses/six/LICENSE) |
| typing_extensions | 4.16.0 | PSF-2.0 | [LICENSE](third_party/licenses/typing_extensions/LICENSE) |
| urllib3 | 2.8.0 | MIT | [LICENSE.txt](third_party/licenses/urllib3/LICENSE.txt) |

## Distribution notes

`gpwc` provides two read-only request payload schemas and is pinned to commit `651aa268d50529cb6128c8a42c9cd4ce668f2189` of [google_photos_web_client](https://github.com/xob0t/google_photos_web_client). Its MIT notice is retained.

`pystray` is LGPLv3-or-later. Installed builds load its unmodified `.py` files from
`_internal/pystray`, outside the frozen Python archive. Users may replace that
directory with a compatible modified library and debug those modifications.
Every binary release also includes its full matching `pystray-0.19.5.tar.gz`
source archive. GPL/LGPL notices are retained. Our original code remains MIT.

`certifi` includes MPL-2.0-covered certificate data. Retain its notices and source-availability information when redistributing covered files. Other dependencies may include additional third-party notices within their distributions, especially native libraries and browser tooling.

Python's PSF license and bundled-component notices, Tcl/Tk license terms, and an
exact Python/package version inventory accompany each installer. The Playwright
driver retains its Node `LICENSE`, package `LICENSE`, `NOTICE`, and
`ThirdPartyNotices.txt`. The installer is built with NSIS under its licenses,
including the LZMA linking exception. PyInstaller's bootloader distribution
exception permits the application's existing license. Build tools are unmodified.

Source availability: the version inventory identifies the exact packages. Their
matching source distributions are available from [PyPI](https://pypi.org/), with
`gpwc` pinned to the commit linked above. Python source is available from
[python.org](https://www.python.org/downloads/source/), and the unmodified
certificate bundle covered by MPL-2.0 is retained in `_internal/certifi`.

No code is copied from JBS. The authentication design was informed by
[notebooklm-py](https://github.com/teng-lin/notebooklm-py); it is not a dependency.
