# Windows installer builds

Build on x64 Windows using a current supported Python, Tkinter, and a clean
virtual environment. The release workflow uses Python 3.14.10 and verifies its
runtime inventory. Chrome is installed by the user, never bundled.

The build fails for runtimes below the reviewed security baseline: Python
3.12.16, 3.13.18, 3.14.10, or 3.15.2. Later final patch releases in those branches
are accepted. Review this policy when new security fixes become available.

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

## SignPath onboarding and production signing

The [code signing policy](../CODE_SIGNING_POLICY.md) records current status and
maintainer roles. The SignPath application is separate from account login; after
approval the maintainer must complete account/MFA setup and authorize the
SignPath GitHub App for this repository. No private key is handled by this project.

Create a SignPath project linked to this public GitHub repository. Configure
`app-executables` and `installer` from `.github/signpath/*.xml`, with a required
`version` parameter, and a production signing policy with **manual approval**.
Restrict source to the upstream `main` branch and GitHub-hosted runners. Use
submitter-only API credentials. Store `SIGNPATH_API_TOKEN` as a GitHub Actions
secret, and these nonsecret repository variables:

- `SIGNPATH_ORGANIZATION_ID`
- `SIGNPATH_PROJECT_SLUG`
- `SIGNPATH_POLICY_SLUG`

Run **Windows installer** with `sign` enabled only after approval and configuration.
The workflow uploads only the two application executables for the first request,
verifies their publisher and timestamps, rebuilds NSIS with those signed files,
then separately submits and verifies the final installer. Upstream libraries keep
their original signatures and licenses. An unsigned build never silently becomes
a signed release; missing credentials or invalid signatures fail the signing path.

The production path is prepared but cannot be exercised before SignPath approves
the project and the maintainer approves actual signing requests. Verify the exact
certificate subject at onboarding; `Verify-Signatures.ps1` expects the publisher
`SignPath Foundation`. Generate release hashes only after final signing.
