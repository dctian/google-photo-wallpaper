# Privacy policy

Google Photo Wallpaper downloads photos only from albums you select and stores
them on your Windows computer. It is an unofficial application, not a Google service.

## Network use

- Setup and maintainer builds retrieve public dependencies and build tools from
  their upstream distribution sites. The Windows installer includes the runtime
  and application dependencies.
- Google sign-in happens in installed Chrome or Edge with a separate local
  profile. Google receives the requests needed for sign-in, album listing, and
  image downloads. Google's services and the browser follow their own privacy
  policies. The app does not receive your Google password or MFA codes.
- Scheduled downloads contact Google for the albums you chose. Google access is
  read-only: the app does not upload, modify, share, or delete Google Photos data.
- Local collage generation and wallpaper rotation use local files.
- Clicking the optional support link opens Ko-fi in your browser. That visit and
  any payment are governed by Ko-fi and the payment provider; the app does not
  collect payment details or send your photos to them.
- There is no app telemetry, advertising network, remote image-scoring service,
  or automatic upload of diagnostics or photos to the maintainer.

## Local data

The private config contains selected album URLs and settings. A dedicated browser
profile retains the Google session. The photo cache, generated wallpapers, and
bounded local job logs remain on your computer. Default data is under
`%LOCALAPPDATA%\GooglePhotosWallpaper`; you can choose another photo-cache location.
Session data is sensitive. Do not share browser profiles, cookies, private album
links, personal photos, or unredacted logs in public bug reports.

Downloaded JPEG copies omit source EXIF/GPS metadata, but pictures themselves
can contain personal information. Choose suitable albums. The app performs no
face recognition or identification of sensitive content.

Uninstall removes application files and integration belonging to that install,
and preserves your private data. You can remove that data manually after closing
the app and its dedicated browser and stopping scheduled jobs.

References: [Google privacy](https://policies.google.com/privacy),
[Ko-fi privacy](https://more.ko-fi.com/privacy), [security reporting](SECURITY.md).
