# Changelog

## 0.2.0 - 2026-10-31


- Add a Windows x64 installer with a bundled Python runtime and per-user paths.
- Add optional Ko-fi support links and coffee/lunch/dinner suggestions.
- Preserve failure exit codes after exhausting the hourly download allowance.
- Use UTF-8 for redirected CLI output and scheduled refresh jobs.
- Isolate generated wallpaper sets belonging to sibling photo caches.
- Retain source setup, privacy boundaries, and the rolling hourly download limit.

## 0.1.0 - 2026-10-31

Initial Windows source release.

- Select private Google Photos albums through a dedicated signed-in Chrome profile.
- Download at most 50 photo attempts per rolling hour, shared across manual and scheduled runs.
- Rotate a bounded local collection, defaulting to 500 photos and a 1 GiB source-photo budget.
- Prefer anniversary dates, adequate resolution, and conservative near-duplicate filtering.
- Generate scattered photo-print collages with varied sizes, rotations, overlap, smooth frames, and an outer margin.
- Configure photos per collage and rotation timing, defaulting to 20 photos and 10 minutes.
- Synchronize the same complete wallpaper on all monitors through Windows Task Scheduler.
- Minimize to the system tray and refresh wallpaper from its context menu.
- Use the photo folder independently with JBS or another wallpaper tool.

This integration uses undocumented Google Photos web endpoints and is not endorsed by Google.
