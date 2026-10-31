# Contributing

This is a Windows desktop application. Start with Python 3.12 or 3.13 and an
isolated environment:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -q
```

Tests use synthetic images and mocked Google responses; they must not require
personal accounts, cookies, or network access to Google Photos. Manual sign-in
and live compatibility checks remain separate from the offline suite.

Keep the rolling download allowance, read-only RPC allowlist, owned-folder
checks, atomic publication, and credential isolation intact. Preserve the same
image on all monitors and keep wallpaper rotation independent of photo downloads.

Never commit private album URLs, browser profiles, cookies, configuration,
downloaded photos, generated wallpapers, or unredacted traces. Use synthetic
fixtures when reproducing a parser or layout problem. Do not add telemetry or
send user photos to external services.

For a pull request, explain the user-visible behavior and relevant validation.
Contributions are licensed under the project's MIT license; third-party code
retains its own license and notices.
