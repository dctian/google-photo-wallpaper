# Third-party notices

The application source is MIT-licensed. Third-party dependencies retain their own licenses.
This source release does not bundle Python, Chrome, dependency wheels, or a frozen executable. Setup installs dependencies separately.
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

`pystray` is LGPLv3. Keep its GPL/LGPL notices and comply with its library-source and replacement/relinking requirements if distributing a bundled executable. Importing this dependency does not relicense our original application source. This release distributes source and installs the library separately.

`certifi` includes MPL-2.0-covered certificate data. Retain its notices and source-availability information when redistributing covered files. Other dependencies may include additional third-party notices within their distributions, especially native libraries and browser tooling.

Future frozen binaries need a separate audit of every bundled library and runtime. Chrome and JBS are not redistributed. No code is copied from JBS. The authentication design was informed by [notebooklm-py](https://github.com/teng-lin/notebooklm-py); it is not an application dependency.
