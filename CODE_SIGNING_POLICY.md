# Code signing policy

Status: **The SignPath Foundation application was submitted on October 31, 2026
and is awaiting approval. No release currently claims a SignPath signature.**
Existing unsigned releases are labeled as such.

If the project is approved, the attribution will be: Free code signing provided
by [SignPath.io](https://about.signpath.io/), certificate by
[SignPath Foundation](https://signpath.org/).

- Author, reviewer and release approver: [David Tian (@dctian)](https://github.com/dctian).
- Outside contributions require maintainer review before entering the release branch.
- Sign only this project's GUI, console worker, and installer. Preserve upstream
  signatures and notices; do not sign third-party libraries as our own code.
- Signing inputs must come from the public repository's `main` branch, on
  GitHub-hosted Windows runners, with a patched runtime and successful checks.
- Each production signing request requires manual approval by the release approver
  in SignPath. Maintainer accounts must use MFA on GitHub and SignPath.
- Project name and version metadata must match the artifact configuration.
- Verify trusted Authenticode signatures and timestamps before publishing.
- Sign application executables first, rebuild the installer with those files,
  then sign and verify the final installer. Generate checksums afterward.
- Keep API tokens in GitHub Actions secrets with submitter-only permissions.
  Never commit tokens or request private signing keys in chat.

See [privacy policy](PRIVACY.md) and [Windows builds](docs/building-windows.md).
Signing identifies the publisher and detects changes to signed files; it does
not replace code review, dependency maintenance, or testing.
