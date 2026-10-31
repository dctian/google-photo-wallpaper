# Changelog

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
