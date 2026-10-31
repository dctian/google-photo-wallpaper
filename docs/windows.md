# Hourly refresh on Windows

## Open the app at Windows sign-in

The **Google Photos Wallpaper** shortcut in your current user's Startup folder opens
the app when you sign in to Windows. Install it with `scripts/Install-Startup.ps1`. It uses the project's
`pythonw.exe`, so the app opens without a terminal and does not request
administrator rights.

This shortcut opens the app window. The hourly **GooglePhotosWallpaperRefresh**
task runs independently, so closing the app does not stop scheduled downloads.
Minimizing hides the window in the notification area. Use the tray icon's
**Show app** menu item to restore it, **Refresh wallpaper** to immediately change
both monitors, **Open wallpaper folder** to open the generated wallpaper folder,
or **Exit app** to quit. The **X** button also exits the app.

To stop opening the app at sign-in, press **Win+R**, enter `shell:startup`, and
delete **Google Photos Wallpaper.lnk**. This removes only the startup shortcut;
the app, photos, browser profile, and hourly task remain available. If you move
the project, update this shortcut's target, arguments, and working directory.

## Schedule background refreshes

Finish Python setup, choose your albums, sign in using the separate browser profile,
and prepare a local photo collection. The installer uses the read-only
`status --require-schedulable` check: it verifies selected albums, the dedicated
browser profile marker, and an intact owned collection within the current limits.
An interrupted batch can resume on schedule; installation does not download more
photos, claim that the interrupted batch succeeded, or recheck Google sign-in.
The separate `status --require-ready` check still requires a completed successful
refresh under the current settings.

From the project folder in a normal PowerShell window:

```powershell
.\scripts\Run-Refresh.ps1
.\scripts\Install-Task.ps1
```

The task is named `GooglePhotosWallpaperRefresh`. It runs every hour, beginning
one hour after installation. All refreshes share a persistent limit of **50 photo
download attempts per rolling hour**, including the first batch, manual refreshes,
and app restarts. Failed downloads and pictures discarded by filtering also count.
An empty collection fills gradually toward 500 photos; there is no initial bulk
download. Once the collection is full, verified replacements retire the oldest
photos. Unused hours do not accumulate extra download credit. To choose a
longer interval, use `Install-Task.ps1 -IntervalHours 6`; 24 means once every 24
hours. Use `-ConfigPath` and `-TaskName` consistently when
maintaining more than one configuration. Re-running the installer updates the
matching task; it refuses to overwrite a task for another configuration.

The task runs only while your Windows account is signed in, including when the
screen is locked. It requests no administrator rights or account password. A
missed start can run when Windows becomes available; it does not wake a sleeping
laptop. It allows battery power and does not require a particular network profile.
If the network or Google session is unavailable, the refresh fails and the existing
cache remains available. The next scheduled run tries again within the shared
hourly limit. A missed start can resume work but cannot create a catch-up burst.

The scheduled action uses the virtual environment's `pythonw.exe` and a hidden
child process, so it does not open a terminal. It waits for the refresh and preserves
the Python exit code in Task Scheduler's **Last Run Result**. Overlapping scheduled
runs are ignored; a run is limited to one hour. Console output is kept in
`.state\task.log` with one rotated backup, at most 2 MiB total. Logs should contain
status and redacted errors, never authentication cookies or album URLs.

To inspect or run the task manually:

```powershell
Get-ScheduledTaskInfo -TaskName GooglePhotosWallpaperRefresh
Start-ScheduledTask -TaskName GooglePhotosWallpaperRefresh
Get-Content .\.state\task.log -Tail 30
```

To remove the schedule:

```powershell
.\scripts\Remove-Task.ps1
```

Removing the task preserves your photo cache and browser profile. If you move this
project, remove its task first, move the folder, then install it from the new
location. Both install and removal support PowerShell's `-WhatIf` preview.

If local script execution is blocked, run a single script with
`powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\Install-Task.ps1`.
This applies only to that PowerShell process and does not change your machine's
execution policy.

Task behavior follows Microsoft's
[principal documentation](https://learn.microsoft.com/en-us/powershell/module/scheduledtasks/new-scheduledtaskprincipal)
and [settings documentation](https://learn.microsoft.com/en-us/powershell/module/scheduledtasks/new-scheduledtasksettingsset).


## Wallpaper rotation is separate from photo downloads

The app has **Photo downloader** and **Wallpaper** settings tabs. The hourly
`GooglePhotosWallpaperRefresh` task downloads a bounded photo batch. The
`GooglePhotosWallpaperRotation` task changes prepared local wallpapers at the
interval chosen in the Wallpaper tab, defaulting to ten minutes. It uses the
Windows wallpaper API to apply the same image to every monitor, independently
of Windows' built-in slideshow and whether the app window is open.

Choose photos per collage (default 20) and minutes between changes (default 10),
then use **Apply settings & generate** to rebuild the set and update the task.
**Refresh wallpaper** in the window or tray immediately switches to another
prepared image without Google access or saving pending settings.

At most 20 wallpapers are active, plus the previous set; the generated JPEGs
are bounded to 64 MiB across two successful generations. Rotation logs use
`.state/wallpaper.log` plus one rotated copy, bounded to 2 MiB combined.

To remove only rotation, use
`Unregister-ScheduledTask -TaskName GooglePhotosWallpaperRotation -Confirm:$false`.
Setting `windows_wallpaper` to `false` in config.json also stops future desktop
updates while keeping downloaded photos and generated images.
