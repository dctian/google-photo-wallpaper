# google-photo-wallpaper

[![Tests](https://github.com/dctian/google-photo-wallpaper/actions/workflows/tests.yml/badge.svg)](https://github.com/dctian/google-photo-wallpaper/actions/workflows/tests.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

Private Google Photos albums on your Windows desktop. Download a bounded local
photo collection, create collages, and synchronize the same wallpaper on every
monitor. Or point John's Background Switcher (JBS) or another wallpaper tool at
the downloaded photo folder.

**Unofficial community project.** Uses undocumented Google Photos web endpoints.
Not affiliated with or endorsed by Google or JBS. Endpoints and sign-in behavior
can change without notice. Use is subject to Google's applicable terms; the
50-photo allowance is an implementation limit, not permission from Google.

## Features

- Select private albums without turning on link sharing.
- Reuse a dedicated Chrome profile after signing in yourself.
- Download at most 50 photo attempts per rolling hour, including the first run,
  manual refreshes, failures, and filtered photos. No catch-up bursts.
- Keep up to 500 local photos by default; replace older downloads after verified
  replacements arrive. Source JPEGs have a 1 GiB default budget.
- Mix in photos from this time of year in past years (30%, within seven days).
- Prefer adequate resolution and skip nearly blank frames and conservative
  near-duplicates. No aesthetic model or external image-analysis service.
- Make collages of loosely tossed photo prints with varied sizes, angles,
  overlap, smooth white borders, shadows, and a clear outer margin.
- Configure photos per collage and wallpaper timing (defaults: 20 and 10 minutes).
- Show the same complete image on every monitor, fitted separately, without spanning.
- Refresh wallpaper from the app or its system-tray menu.
- One dashboard for download activity, your photo collection, and optional desktop
  wallpaper. Focused settings dialogs keep the main window free of tabs and scrolling.

## Install on Windows

For Windows 10/11 on x64, download **`google-photo-wallpaper-0.2.0-windows-x64-setup.exe`**
from [Releases](https://github.com/dctian/google-photo-wallpaper/releases/latest).
Run it, then open **Google Photos Wallpaper** from the Start menu. Python and the
required libraries are included; no terminal or setup script is needed.

The installer runs for your current user without administrator rights, under
`%LOCALAPPDATA%\Programs\GooglePhotoWallpaper`. Private configuration lives in
`%LOCALAPPDATA%\GooglePhotosWallpaper\config.json`. Installed Chrome is required;
Edge can be selected with `browser_channel: "msedge"` in that configuration.
Complete Google sign-in yourself, choose albums, download the first small batch,
then enable hourly downloads and configure Wallpaper in the app.

This early installer is unsigned. The GitHub release includes SHA-256 checksums,
source, dependency notices, and the matching LGPL tray-library source. Uninstall
through Windows' installed-apps list; private configuration, photos and browser
data are preserved. Close the app before upgrading or uninstalling.

### Code signing policy

The SignPath Foundation application was submitted on October 31, 2026 and is
awaiting approval; current releases are unsigned.
See the [code signing policy](CODE_SIGNING_POLICY.md) for approval roles,
build verification, and signing status, and the [privacy policy](PRIVACY.md) for
network use and local data handling.

### Run from source

Source setup requires Python 3.12 or later with Tkinter and installed Chrome.

1. Install Python from [python.org](https://www.python.org/downloads/windows/),
   including the option to add Python to PATH. Install Chrome if needed.
2. Download the source ZIP from [Releases](https://github.com/dctian/google-photo-wallpaper/releases)
   and extract it to a permanent folder, or clone this repository.
3. Run **Setup.cmd**. It creates an isolated `.venv`, installs dependencies, and
   creates your private `config.json`. Internet access is required for setup.
4. Open **Start-App.cmd**.
5. Click **Sign in to Google**. Sign in yourself in the
   separate Chrome window. Once your Photos library appears, **close that browser
   window** so the app can verify and reuse the saved session.
6. Click **Choose albums**, select them, and **Save selection**. Click
   **Download now** for the first small batch, then **Enable hourly downloads**.
   The **Settings** button on Photo downloads opens download and storage preferences.
7. For desktop changes, open **Settings** on the Desktop wallpaper card, choose
   the collage size and interval, and save. Click **Turn wallpaper on**. Preparing the 4K set can take a
   few minutes. Pause JBS or other wallpaper programs to avoid competing updates.

The app shows the **latest photo download** in your local time, even if a batch
was interrupted. Google sign-in is checked when the app opens, after login, and
during downloads. The displayed status includes when it was checked; **Check
connection** verifies it again without downloading photos. If **Google Photos needs sign-in**
appears, click **Sign in to Google** to reconnect. Status and download dates
update automatically while the app is open, including changes from scheduled runs.

For a PowerShell setup instead of the batch launcher:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Setup.ps1
```

The execution-policy override applies only to that setup process.

Installing with an AI assistant? Give it this repository and the
[agent installation runbook](docs/agent-install.md). Dependency setup, checks,
and scheduling are scriptable; you complete Google sign-in and choose albums.

## Two independent jobs

For downloads only, click **Turn wallpaper off** on the Desktop wallpaper card. This
pauses the wallpaper rotation task and stops automatic collage generation after
downloads. Photo downloads and your selected albums are unchanged. The existing
desktop image stays in place, and the photo folder still works with JBS or other
wallpaper apps. Click **Turn wallpaper on** to restore desktop changes.

| Job | Default | What it does |
| --- | --- | --- |
| Photo downloader | Every hour | Reads selected albums and attempts up to the remaining hourly photo allowance |
| Wallpaper rotation | Every 10 minutes | Selects another already generated local image and applies it to all monitors |

Windows Task Scheduler runs both jobs while you are signed in, even when the app
window is closed. This does **not** depend on Windows' built-in wallpaper slideshow.
The app does not wake a sleeping computer. Missed download intervals never build
up credit for a bulk download.

The downloader shows whether hourly downloads are **ON** or **OFF** and the next
run reported by Windows. Turning downloads on again preserves an existing
schedule and creates no duplicate jobs. **Pause hourly downloads** pauses
future automatic runs; a running batch can finish and manual downloads still work.
The activity display distinguishes connecting, reading albums, and downloading,
with counts of photos added, skipped, and failed. During downloads the progress
bar measures completed photo attempts, including skipped or failed photos. During
other actions it animates without a percentage; it is hidden when idle. Updates
from scheduled downloads appear within five seconds. If the hourly allowance is
used, its reset time is shown separately from the next scheduled run.

Click **Open logs** at the bottom of the app to inspect photo-download, wallpaper,
and manual-action logs. The viewer shows timestamps in local time; **Reload**
reads new entries and **Open log folder** opens the original files. Logs stay on
your computer and retain at most two 1 MiB files per category. Temporary Windows
file locks during cache-state updates are retried and recorded in these logs.

When wallpaper is on, hourly runs renew the collage set from local photos. **Next wallpaper**
switches immediately to another prepared image without contacting Google or saving
pending settings. The tray's **Refresh wallpaper** does the same thing. Saving
wallpaper settings applies them immediately when wallpaper is on; it stays off otherwise.
Minimize to the system tray; closing the app with **X** exits only the window.

To open the app at Windows sign-in, run:

```powershell
.\scripts\Install-Startup.ps1
```

See [Windows scheduling and removal](docs/windows.md) for task names, logs, and
uninstallation. If you move the app folder later, update its tasks and startup
shortcut to the new path.

## Storage and configuration

Default paths are private to the current Windows user:

| Data | Default path |
| --- | --- |
| Downloaded photos, usable with JBS | `%LOCALAPPDATA%\GooglePhotosWallpaper\cache\photos` |
| Browser session | `%LOCALAPPDATA%\GooglePhotosWallpaper\browser` |
| Generated wallpapers | `%LOCALAPPDATA%\GooglePhotosWallpaper\wallpapers` |

You can change paths and advanced options in private `config.json`; see
[config.example.json](config.example.json). Existing installations retain their
saved locations. Keep the browser profile and photo cache in separate folders.
Custom cache directories use separate wallpaper output folders; **Open wallpapers**
in Wallpaper settings opens the resolved folder. No developer-machine paths are defaults.

Up to **20 wallpapers are active**, with the previous set retained during turnover:
up to 40 generated JPEGs, bounded to approximately **64 MiB** across two successful
sets. Each collage contains up to the configured photo count. This budget is
separate from the source-photo cache. Browser data, installed dependencies, and
logs are separate too; each job's logs rotate at 2 MiB combined.

Wallpaper copies preserve image proportions and omit source EXIF/GPS. Print overlap
can hide parts of pictures. The layout uses geometry, not face recognition.
The basic photo filters do not recognize documents, sensitive pictures, closed
eyes, or personal significance. Choose suitable albums; no photograph in Google
Photos is modified or deleted.

## Authentication and limitations

The initial sign-in uses ordinary installed Chrome with a separate profile.
Background reads use that profile headlessly, with Chromium sandboxing enabled.
Session cookies stay in the browser context. The app allows only two read-only
Google Photos RPCs: album listing and album contents. It tries one silent session
renewal before asking you to sign in again.

Google removed broad third-party library access from the official Photos API in
March 2025. This project uses the website's undocumented interface, which may
break or be rejected. A rate limit does not guarantee continued access or account
safety. Existing local pictures remain usable after an authentication or network
failure. The tests use synthetic images and mocked responses; passing tests do not
prove that Google's current website accepts this integration.

References: [Google API changes](https://developers.google.com/photos/support/updates),
[Google terms](https://policies.google.com/terms),
[NotebookLM client session-persistence approach](https://github.com/teng-lin/notebooklm-py).

## Development

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -q
.\.venv\Scripts\python.exe -m photo_cache --help
.\.venv\Scripts\python.exe -m photo_cache status
```

[Contributing](CONTRIBUTING.md) explains testing and privacy requirements.
Report vulnerabilities privately as described in [SECURITY.md](SECURITY.md).
Never attach browser profiles, cookies, private album links, personal images, or
unredacted logs to public issues.

## License

Our original code is licensed under [MIT](LICENSE). Dependencies retain their own
licenses; see [third-party notices](THIRD_PARTY_NOTICES.md). Chrome and JBS are not
included. Installed builds retain runtime licenses and ship the LGPL tray library
as replaceable source. See [Windows build instructions](docs/building-windows.md).

## Support

All features are free. If you enjoy the app, [support the project on Ko-fi](https://ko-fi.com/davidtian).
Coffee **$5**, lunch **$15**, or dinner **$25** are playful suggestions for optional
tips. Ko-fi represents larger amounts as more coffees. Support is never required.
