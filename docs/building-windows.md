# Windows installer builds

Build on x64 Windows using a current supported Python, Tkinter, and a clean
virtual environment. The release workflow uses Python 3.14.10 and verifies its
runtime inventory. Chrome is installed by the user, never bundled.

```powershell
python -m venv .state/build-venv
.\.state\build-venv\Scripts\python.exe -m pip install -r requirements-build.txt
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\Build-Windows.ps1 -Python .state/build-venv/Scripts/python.exe
```

The build downloads NSIS 3.13 from its official SourceForge distribution and
verifies a pinned SHA-256 checksum. Use `-NsisCompiler` to select an existing
trusted compiler. PyInstaller produces a shared runtime, GUI executable, and
console worker. NSIS wraps these in a per-user installer. Neither build step
copies private `config.json`, caches, logs, photos, or browser profiles.

The installed app defaults to `%LOCALAPPDATA%\GooglePhotosWallpaper` for writable
data. Resources and executable paths resolve at runtime, independent of the build
machine. Scheduled jobs call the installed GUI executable with `--run-task`,
which logs and invokes the bundled console worker without a terminal window.
Source checkouts continue to use their local virtual environment and config.

`GooglePhotoWallpaper-cli.exe --self-test` exercises Tk, synthetic collage
rendering, the external tray-library source, certificates, Google payload schemas,
and the Node browser driver without opening a browser or contacting Google.
CI also installs and uninstalls in an isolated directory, checks paths and job
actions, and verifies that private data survives uninstallation. No real account
or personal photos are used.

The LGPL tray library remains replaceable `.py` source at `_internal/pystray`.
Include its matching source archive and all notices with binary releases. Runtime
licenses and a version inventory are under `_internal/licenses/runtime`; other
dependency licenses are retained in package metadata and copied notices.

Publish the tested installer, the tagged source ZIP, `pystray-0.19.5.tar.gz`, and
`SHA256SUMS.txt` as GitHub Release assets. The current build is unsigned; code
signing requires a maintainer-controlled signing identity and is a separate step.
