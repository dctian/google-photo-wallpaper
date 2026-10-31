# Working in this repository

For installation on another Windows machine, follow
[docs/agent-install.md](docs/agent-install.md). The README is the user guide.

- Use a normal Windows user account; administrator rights are not required.
- Keep Google sign-in and MFA with the user. Never request passwords, export
  cookies, or copy another installation's browser profile.
- Keep `config.json`, profiles, caches, logs, reports, and personal photos private.
- Preserve existing configuration and data when updating an installation.
- Keep the persistent 50-attempt rolling-hour limit, including failures and
  rejected pictures. Do not reset quota state to test downloads.
- Google access must stay read-only. Offline tests use synthetic images and
  mocked responses, not a real account.
- Run `python -m unittest discover -s tests -q` with the project environment
  after code changes, and `python -m pip check` after dependency changes.
- Keep third-party notices and licenses when updating dependencies. The current
  release distributes source, not Python, Chrome, or frozen executables.
