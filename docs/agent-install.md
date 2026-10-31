# Windows installation runbook for an AI assistant

Use a normal PowerShell session in the interactive user's Windows account. This
source release needs Python 3.11+ with Tkinter and installed Chrome (or Edge).
Setup is scriptable; the user must complete Google sign-in/MFA and decide which
albums to use. Do not promise unattended authentication or permanent sessions.

## 1. Install in a permanent writable folder

Download a release source ZIP and extract it, or clone this repository. Set the
working directory to the extracted project root, which contains `Setup.ps1`.
Avoid temporary folders and `Program Files`. Verify prerequisites:

```powershell
python -c "import sys, tkinter; print(sys.version); assert sys.version_info >= (3, 11)"
```

If Python or Chrome is missing, help the user install the official distribution.
Do not disable antivirus, browser sandboxing, or machine-wide execution policy.

## 2. Set up and validate dependencies

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Setup.ps1
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m photo_cache --version
.\.venv\Scripts\python.exe -m unittest discover -s tests -q
```

Check each command's exit code before continuing. Setup creates `.venv` and a
private `config.json` only when absent; rerunning preserves the configuration.
No Git installation is required for the release ZIP. Do not copy the developer's
configuration, session profile, or photo cache onto the new machine.

## 3. User-assisted account and album selection

Launch `Start-App.cmd`. On **Photo downloader**, the user clicks **Sign in to
Google** and signs in directly in the separate installed browser. They close
that browser window after Photos appears, then **Load my albums**, select their
albums, and **Save downloader settings**. Never ask them to paste credentials,
cookies, or MFA codes into chat. Stop login automation at any challenge.

Defaults put private data under `%LOCALAPPDATA%\GooglePhotosWallpaper`. If the
user wants another photo location, configure it before the first download.
Keep the browser profile separate from the photo cache. Do not enable sharing.

## 4. Prepare a bounded collection and schedule downloads

The user can click **Download photos now**, or run this once after album selection:

```powershell
.\.venv\Scripts\python.exe -m photo_cache refresh
.\.venv\Scripts\python.exe -m photo_cache status --require-schedulable
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\Install-Task.ps1
```

Install the task only if the preflight succeeds. Downloads attempt at most 50
photos per rolling hour across all entry points; filtering may leave fewer.
The first run does not fill 500 slots. Never repeatedly retry to fill the cache,
remove quota state, or bypass a lock. No unused credit accumulates during sleep.
The local status preflight does not verify current Google authentication.

## 5. Choose standalone wallpaper or an external tool

For standalone mode, use **Wallpaper**, choose photos per collage and change
interval, then **Apply settings & generate**. Defaults are 20 photos and ten
minutes. This applies the same complete picture to every monitor and installs
the independent rotation task. Pause competing wallpaper tools first.

For JBS or another tool, leave standalone rotation off and point that tool at
the configured cache's `photos` subfolder. No generated collages are required.

If the user wants the app window at sign-in:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\Install-Startup.ps1
```

## 6. Verify and hand off

```powershell
Get-ScheduledTask -TaskName GooglePhotosWallpaperRefresh
# For standalone mode only:
Get-ScheduledTask -TaskName GooglePhotosWallpaperRotation
.\.venv\Scripts\python.exe -m photo_cache status
```

Confirm the displayed photo path and, in standalone mode, the wallpaper on all
monitors with the user. Tasks run only while that Windows account is signed in.
Explain the tray menu and **Refresh wallpaper**, and leave a link to
[Windows scheduling and removal](windows.md). Record installed paths and task
names locally without including private album links or browser data in chat.

If Google rejects the saved session, have the user sign in again. If the web
format changes, preserve cached images and report a redacted bug; offline tests
cannot prove compatibility with Google's live site. To relocate later, remove
the tasks, close the app, move the source folder, recreate `.venv` with Setup,
then reinstall tasks and startup from the new location. Preserve private data.
