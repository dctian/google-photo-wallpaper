"""A local desktop setup window; Google credentials stay in its browser profile."""

from __future__ import annotations

import json
import os
from pathlib import Path
import queue
import re
import subprocess
import sys
import tempfile
import threading
import webbrowser
from typing import Callable
import tkinter as tk
from tkinter import messagebox, ttk
from tkinter.scrolledtext import ScrolledText

from .cache import Cache, CacheError, file_lock
from .config import ConfigError, default_data, load_config
from .source import GooglePhotosSource, SourceError, login
from .tray import TrayIcon
from .wallpapers import wallpaper_dir
from .runtime import resource_dir, command as app_command
from .connection_status import connection_text, latest_download, read_connection, local_date
from .schedule import read_schedule, schedule_text, task_command
from .download_status import ACTIVE_PHASES, activity_text
from .logs import append_app_log, log_directory, read_log


PROJECT_ROOT = resource_dir()
SUPPORT_URL = "https://ko-fi.com/davidtian"


def _safe_output(text: str) -> str:
    """Even an unexpected child error must not display signed photo URLs."""
    return re.sub(r"https?://\S+", "[private URL]", text)


def _album_id(url: str) -> str:
    return url.split("?", 1)[0].rstrip("/").rsplit("/", 1)[-1]


def _write_config(path: Path, data: dict) -> None:
    """Validate a same-directory temporary file, then replace atomically."""
    data = {key: value for key, value in data.items() if key not in ("aesthetic_filter", "aesthetic_min_score")}
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=".photo-config-", suffix=".json", delete=False) as stream:
            temp = Path(stream.name)
            json.dump(data, stream, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        load_config(temp)
        os.replace(temp, path)
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)


class WallpaperApp:
    def __init__(self, root: tk.Tk, config_path: Path):
        self.root = root
        self.config_path = config_path.absolute()
        self.config = load_config(self.config_path)
        self.events: queue.Queue = queue.Queue()
        self.tray = TrayIcon(lambda event: self.events.put((event, None, None)))
        self._tray_minimize_pending = False
        self._hidden_to_tray = False
        self._closing = False
        self.busy = False
        self.loaded_albums = False
        self.album_rows: dict[str, dict] = {}
        self.selected_ids = {_album_id(url) for url in self.config.albums}
        self.buttons: list[ttk.Button] = []
        self.dirty = False
        self.status = tk.StringVar(value="Ready.")
        self.selection = tk.StringVar(value=f"{len(self.config.albums)} saved albums")
        self.cache_status = tk.StringVar()
        self.connection_status = tk.StringVar()
        self.download_status = tk.StringVar(value='Idle · No photo download is running.')
        self.schedule_status = tk.StringVar(value='Checking the Windows download schedule…')
        self.wallpaper_feature_status = tk.StringVar()
        self._schedule_data = {'state': 'unknown'}
        self._schedule_query_running = False
        self._schedule_poll_count = 0
        self.collection_hint = tk.StringVar()
        self.batch_size = tk.StringVar(value=str(self.config.batch_size))
        self.max_photos = tk.StringVar(value=str(self.config.max_photos))
        self.cache_mib = tk.StringVar(value=str(self.config.max_bytes // (1024 * 1024)))
        self.resolution = tk.StringVar(value=f"{self.config.max_width} × {self.config.max_height}")
        self.quality_filter = tk.BooleanVar(value=getattr(self.config, "quality_filter", True))
        self.anniversaries = tk.BooleanVar(value=getattr(self.config, "anniversary_fraction", 0.3) > 0)
        self.wallpaper_layout = tk.StringVar(value=self.config.wallpaper_layout)
        self.wallpaper_photos = tk.StringVar(value=str(self.config.wallpaper_photos_per_image))
        self.wallpaper_minutes = tk.StringVar(value=str(self.config.wallpaper_interval_minutes))
        self.wallpaper_dirty = False
        self._update_collection_hint()
        self._build()
        self._update_cache_status()
        self.root.protocol("WM_DELETE_WINDOW", self._close)
        self.root.bind("<Unmap>", self._on_unmap, add="+")
        self.root.bind("<Destroy>", self._on_destroy, add="+")
        self.root.after(100, self._poll)
        self.root.after(300, self._check_sign_in)
        self.root.after(5000, self._watch_status)
        self.root.after(100, self._query_schedule)

    def _build(self) -> None:
        from .dashboard import build
        build(self)

    def _sync_dashboard(self) -> None:
        from .dashboard import sync
        sync(self)

    def _open_logs(self) -> None:
        folder = log_directory(self.config_path)
        dialog = tk.Toplevel(self.root)
        dialog.title('Google Photos Wallpaper — Logs')
        dialog.geometry('1000x650')
        panel = ttk.Frame(dialog, padding=16)
        panel.pack(fill='both', expand=True)
        ttk.Label(panel, text='Local logs · Timestamps shown in local time · Latest entries at the bottom').pack(anchor='w', pady=(0, 10))
        sources = {'Photo downloads': 'task.log', 'Wallpaper rotation': 'wallpaper.log',
                   'App actions / manual downloads': 'app.log'}
        source = tk.StringVar(value='Photo downloads')
        selector = ttk.Combobox(panel, state='readonly', textvariable=source, values=tuple(sources), width=35)
        selector.pack(anchor='w', pady=(0, 12))
        text = ScrolledText(panel, wrap='word', font=('Consolas', 10))
        text.pack(fill='both', expand=True)
        def reload_logs():
            text.configure(state='normal')
            text.delete('1.0', 'end')
            text.insert('1.0', read_log(folder, sources[source.get()]))
            text.configure(state='disabled')
            text.see('end')
        selector.bind('<<ComboboxSelected>>', lambda _: reload_logs())
        def open_folder():
            try:
                folder.mkdir(parents=True, exist_ok=True)
                os.startfile(folder)
            except OSError:
                messagebox.showerror('Open logs', 'Could not open the log folder: ' + str(folder), parent=dialog)
        actions = ttk.Frame(panel)
        actions.pack(fill='x', pady=(10, 0))
        ttk.Button(actions, text='Reload', command=reload_logs).pack(side='left')
        ttk.Button(actions, text='Open log folder', command=open_folder).pack(side='left', padx=8)
        ttk.Button(actions, text='Close', command=dialog.destroy).pack(side='right')
        reload_logs()

    def _support(self) -> None:
        dialog = tk.Toplevel(self.root)
        dialog.title("Support this project")
        dialog.transient(self.root)
        panel = ttk.Frame(dialog, padding=24)
        panel.pack(fill="both", expand=True)
        ttk.Label(panel, text="Enjoying Google Photos Wallpaper?", font=("Segoe UI", 14, "bold")).pack(anchor="w")
        ttk.Label(panel, text="Coffee $5   ·   Lunch $15   ·   Dinner $25", padding=(0, 16)).pack(anchor="w")
        ttk.Label(panel, text="These are playful suggestions for optional tips.\nKo-fi displays larger amounts as more coffees.\nAll app features are free, with or without support.").pack(anchor="w")
        ttk.Button(panel, text="Open Ko-fi", command=lambda: webbrowser.open(SUPPORT_URL)).pack(side="left", pady=(20, 0))
        ttk.Button(panel, text="Close", command=dialog.destroy).pack(side="right", pady=(20, 0))

    def _command(self, *arguments: str) -> list[str]:
        return app_command(list(arguments), python=self._python())

    def _button(self, parent, label: str, action: Callable) -> ttk.Button:
        button = ttk.Button(parent, text=label, command=action)
        self.buttons.append(button)
        return button

    def _mark_dirty(self) -> None:
        self.dirty = True
        self._update_collection_hint()

    def _update_collection_hint(self) -> None:
        try:
            batch, limit = int(self.batch_size.get()), int(self.max_photos.get())
            text = f"Adds up to {batch} new photos per hour, gradually reaching {limit}; older downloads then rotate out."
        except ValueError:
            text = "Each refresh downloads one batch; the collection grows gradually up to its limit."
        self.collection_hint.set(text)

    def _start(self, label: str, work: Callable, finish: Callable | None = None) -> None:
        if self.busy:
            return
        self.busy = True
        append_app_log(self.config_path, label)
        self.status.set(label)
        for button in self.buttons:
            button.configure(state="disabled")
        self.progress.configure(mode='indeterminate', value=0)
        self.progress.grid()
        self.progress.start(12)
        self._sync_dashboard()

        def run():
            try:
                result = work()
                append_app_log(self.config_path, 'Action completed.')
                self.events.put(("done", result, finish))
            except (SourceError, ConfigError, CacheError) as exc:
                append_app_log(self.config_path, 'Action failed: ' + _safe_output(str(exc)))
                self.events.put(("error", str(exc), None))
            except Exception:
                append_app_log(self.config_path, 'Action failed unexpectedly. Check local setup.')
                self.events.put(("error", "This action could not finish. Check the local setup and try again.", None))
        threading.Thread(target=run, name="photo-wallpaper-action", daemon=True).start()

    def _poll(self) -> None:
        try:
            while True:
                event, value, finish = self.events.get_nowait()
                if self._handle_tray_event(event):
                    if self._closing:
                        return
                    continue
                if event == "progress":
                    self.status.set(_safe_output(value))
                    self._sync_dashboard()
                    continue
                if event == 'schedule':
                    self._schedule_query_running = False
                    self._schedule_data = value
                    self._show_schedule()
                    continue
                self.busy = False
                self.progress.stop()
                self.progress.configure(value=0)
                self.progress.grid_remove()
                for button in self.buttons:
                    button.configure(state="normal")
                if event == "error":
                    self.status.set(_safe_output(value))
                    if self._hidden_to_tray:
                        self._restore_window()
                    messagebox.showerror("Could not finish", _safe_output(value), parent=self.root)
                elif finish:
                    finish(value)
                else:
                    self.status.set(str(value or "Done."))
                self._show_schedule()
                self._update_cache_status()
        except queue.Empty:
            pass
        if not self._closing:
            self.root.after(100, self._poll)

    def _on_unmap(self, event) -> None:
        if event.widget is self.root and not self._closing:
            self.root.after_idle(self._minimize_to_tray)

    def _minimize_to_tray(self) -> None:
        if self._closing or self.root.state() != "iconic":
            return
        self._tray_minimize_pending = True
        self.tray.show()

    def _handle_tray_event(self, event: str) -> bool:
        if event == "tray_ready":
            if self._tray_minimize_pending and self.root.state() == "iconic":
                self._hidden_to_tray = True
                self.root.withdraw()
            self._tray_minimize_pending = False
        elif event == "tray_show":
            self._restore_window()
        elif event == "tray_refresh":
            self._refresh_wallpaper()
        elif event == "tray_folder":
            self._open_wallpaper_folder()
        elif event == "tray_exit":
            # Existing busy/unsaved-change checks need a visible parent window.
            self._restore_window()
            self._close()
        elif event == "tray_error":
            self._restore_window()
            self.status.set("The notification-area icon could not start. The app window is still available.")
        else:
            return False
        return True

    def _restore_window(self) -> None:
        if self._closing:
            return
        self._tray_minimize_pending = False
        self._hidden_to_tray = False
        self.root.deiconify()
        self.root.state("normal")
        self.root.lift()
        self.root.focus_force()
        self._update_cache_status()

    def _on_destroy(self, event) -> None:
        if event.widget is self.root:
            self._closing = True
            self.tray.close()

    def _with_source(self, action: Callable):
        config = load_config(self.config_path)
        with file_lock(config.profile_dir.parent / "operation.lock"):
            with GooglePhotosSource(config.profile_dir, max_width=config.max_width,
                                    max_height=config.max_height, browser_channel=config.browser_channel) as source:
                return action(source)

    def _sign_in(self) -> None:
        browser_name = 'Edge' if self.config.browser_channel == 'msedge' else 'Chrome'
        def work():
            config = load_config(self.config_path)
            with file_lock(config.profile_dir.parent / "operation.lock"):
                login(config.profile_dir, browser_channel=config.browser_channel)
            return None

        def verified(_result):
            self.status.set('Google sign-in saved. Choose albums to change your selection.')

        self._start(
            f"Sign in in {browser_name}. When your Photos library appears, close that browser window to finish connecting.",
            work, verified)

    def _check_sign_in(self) -> None:
        def work():
            try:
                self._with_source(lambda source: None)
                return "Google sign-in verified. Hourly downloads can use this session."
            except (SourceError, CacheError) as error:
                return str(error)
        self._start("Checking Google sign-in…", work)

    def _watch_status(self) -> None:
        if not self._closing:
            self._update_cache_status()
            self._schedule_poll_count += 1
            if self._schedule_poll_count % 6 == 0:
                self._query_schedule()
            self.root.after(5000, self._watch_status)

    def _query_schedule(self) -> None:
        if self._closing or self._schedule_query_running:
            return
        self._schedule_query_running = True
        def work():
            self.events.put(('schedule', read_schedule(self.config_path), None))
        threading.Thread(target=work, name='download-schedule-status', daemon=True).start()

    def _show_schedule(self) -> None:
        state = self._schedule_data.get('state')
        self.schedule_status.set(schedule_text(self._schedule_data))
        self.schedule_button.configure(
            text='Pause hourly downloads' if state == 'on' else 'Enable hourly downloads',
            state='normal' if not self.busy and state in ('on', 'off') else 'disabled')
        self._sync_dashboard()

    def _toggle_schedule(self) -> None:
        state = self._schedule_data.get('state')
        if state not in ('on', 'off'):
            self._query_schedule()
            return
        if state == 'off' and self.dirty and not self._save():
            return
        mode = 'Off' if state == 'on' else 'On'
        def finish(message):
            self.status.set(message)
            self._query_schedule()
        self._start('Updating hourly photo downloads…', lambda: self._run_process(
            task_command(self.config_path, mode),
            'Hourly downloads are off; an active batch can finish.' if mode == 'Off'
            else 'Hourly downloads are on. The next run is shown above.'), finish)

    def _load_albums(self) -> None:
        def finish(albums):
            saved_urls = { _album_id(url): url for url in self.config.albums }
            selected = set(self.selected_ids)
            self.album_tree.delete(*self.album_rows)
            self.album_rows.clear()
            for album in sorted(albums, key=lambda item: item.title.casefold()):
                row = {"id": album.id, "url": album.url, "title": album.title, "count": album.item_count}
                self._add_album_row(row, album.id in selected)
            listed = {row["id"] for row in self.album_rows.values()}
            # Keep saved choices that this album-list endpoint could not enumerate.
            for album_id in selected - listed:
                url = saved_urls.get(album_id)
                if url:
                    self._add_album_row({"id": album_id, "url": url, "title": "Previously selected album (not listed)",
                                         "count": "—"}, True)
            self.loaded_albums = True
            if hasattr(self, 'album_search'):
                self.album_search.set('')
            self._update_selection()
            self.status.set("Click an album to include or exclude it, then save your selection.")
        self._start("Loading your private albums…", lambda: self._with_source(lambda source: source.list_albums()), finish)

    def _add_album_row(self, row: dict, selected: bool) -> None:
        item = self.album_tree.insert("", "end", values=("✓" if selected else "", row["title"], row["count"]))
        self.album_rows[item] = row

    def _toggle(self, item: str) -> None:
        if self.busy or item not in self.album_rows:
            return
        row = self.album_rows[item]
        if row["id"] in self.selected_ids:
            self.selected_ids.remove(row["id"])
        else:
            self.selected_ids.add(row["id"])
        self.album_tree.set(item, "chosen", "✓" if row["id"] in self.selected_ids else "")
        self.album_tree.focus(item)
        self._update_selection()
        self._mark_dirty()

    def _toggle_album(self, event) -> None:
        self._toggle(self.album_tree.identify_row(event.y))

    def _toggle_keyboard(self, _event) -> str:
        self._toggle(self.album_tree.focus())
        return "break"

    def _select_all(self, selected: bool) -> None:
        if self.busy or not self.loaded_albums:
            return
        self.selected_ids = {row["id"] for row in self.album_rows.values()} if selected else set()
        for item, row in self.album_rows.items():
            self.album_tree.set(item, "chosen", "✓" if selected else "")
        self._update_selection()
        self._mark_dirty()

    def _update_selection(self) -> None:
        self.selection.set(f"{len(self.selected_ids)} albums selected")

    def _save(self) -> bool:
        if self.busy:
            return False
        try:
            current = load_config(self.config_path)
            selected = [row["url"] for row in self.album_rows.values() if row["id"] in self.selected_ids] if self.loaded_albums else list(current.albums)
            try:
                batch, count, mib = int(self.batch_size.get()), int(self.max_photos.get()), int(self.cache_mib.get())
                width, height = [int(value.strip()) for value in self.resolution.get().split("×")]
            except ValueError:
                raise ConfigError("Photo counts, disk limit, and image dimensions must be whole numbers.") from None
            with file_lock(current.profile_dir.parent / "operation.lock"):
                data = json.loads(self.config_path.read_text(encoding="utf-8-sig"))
                data.update(albums=selected, batch_size=batch, max_photos=count, max_bytes=mib * 1024 * 1024,
                            max_width=width, max_height=height)
                self._save_optional_settings(data)
                _write_config(self.config_path, data)
            self.config = load_config(self.config_path)
            self.dirty = False
            self.status.set(f"Saved {len(selected)} albums. Download photos now to prepare the local collection.")
            return True
        except (ConfigError, CacheError) as exc:
            messagebox.showerror("Settings not saved", str(exc), parent=self.root)
        except (OSError, ValueError):
            messagebox.showerror("Settings not saved", "The configuration could not be saved. Check write access and try again.", parent=self.root)
        return False

    def _save_optional_settings(self, data: dict) -> None:
        data["quality_filter"] = self.quality_filter.get()
        data["anniversary_fraction"] = 0.3 if self.anniversaries.get() else 0.0
        # Preserve a manually configured date window; its standard value is ±7 days.
        data.setdefault("anniversary_window_days", 7)

    def _run_process(self, arguments: list[str], success: str) -> str:
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        last_lines = []
        with subprocess.Popen(arguments, cwd=PROJECT_ROOT, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
                              creationflags=flags, env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"}) as process:
            assert process.stdout is not None
            for line in process.stdout:
                safe = _safe_output(line.strip())
                if safe:
                    append_app_log(self.config_path, safe)
                    last_lines = (last_lines + [safe])[-5:]
                    self.events.put(("progress", safe, None))
            result = process.wait()
        if result:
            detail = "\n".join(last_lines)
            raise CacheError(detail or "The action did not finish successfully. The existing wallpaper folder is still available.")
        return success

    def _python(self) -> str:
        path = Path(sys.executable)
        return str(path.with_name("python.exe")) if os.name == "nt" else str(path)

    def _mark_wallpaper_dirty(self) -> None:
        self.wallpaper_dirty = True

    def _save_wallpaper_settings(self) -> bool:
        if self.busy:
            return False
        try:
            current = load_config(self.config_path)
            with file_lock(current.profile_dir.parent / "operation.lock"):
                data = json.loads(self.config_path.read_text(encoding="utf-8-sig"))
                data.update(wallpaper_layout=self.wallpaper_layout.get(),
                            wallpaper_photos_per_image=int(self.wallpaper_photos.get()),
                            wallpaper_interval_minutes=int(self.wallpaper_minutes.get()))
                _write_config(self.config_path, data)
            self.config = load_config(self.config_path)
            self.wallpaper_dirty = False
            return True
        except (ValueError, OSError, ConfigError, CacheError) as exc:
            messagebox.showerror("Wallpaper settings", str(exc), parent=self.root)
            return False

    def _apply_wallpaper(self) -> None:
        if not self._save_wallpaper_settings():
            return
        enabled = self.config.windows_wallpaper
        self._start("Generating wallpapers from local photos; this can take a few minutes…", lambda: self._run_process(
            self._command("--config", str(self.config_path), "wallpapers", *(['--enable'] if enabled else [])),
            "Wallpaper settings applied. Both monitors will change together." if enabled
            else 'Wallpaper images generated. Desktop wallpaper changes remain off.'))

    def _toggle_wallpaper(self) -> None:
        if self.busy:
            return
        enabled = load_config(self.config_path).windows_wallpaper
        self._start('Turning wallpaper off…' if enabled else 'Preparing and turning wallpaper on…',
            lambda: self._run_process(
                self._command('--config', str(self.config_path), 'wallpapers', '--disable' if enabled else '--enable'),
                'Wallpaper is off. Photo downloading continues; the current desktop image stays in place.' if enabled
                else 'Wallpaper is on. Both monitors will change together.'))

    def _show_wallpaper_mode(self) -> None:
        try:
            self.config = load_config(self.config_path)
        except (OSError, ConfigError):
            return
        enabled = self.config.windows_wallpaper
        self.wallpaper_feature_status.set('Your desktop changes automatically. Both screens show the same image.' if enabled
            else 'Download-only mode. Photos keep downloading; your desktop stays as it is.')
        if hasattr(self, 'wallpaper_badge'):
            self.wallpaper_badge.configure(text='ON' if enabled else 'OFF',
                background='#e3f3ec' if enabled else '#eef2f7', foreground='#16835d' if enabled else '#596b80')
        self.wallpaper_toggle_button.configure(text='Turn wallpaper off' if enabled else 'Turn wallpaper on',
                                              state='disabled' if self.busy else 'normal')
        self.wallpaper_refresh_button.configure(state='normal' if enabled and not self.busy else 'disabled')

    def _refresh_wallpaper(self) -> None:
        if self.busy:
            self.status.set("An action is already running. Refresh wallpaper when it finishes.")
            return
        def work():
            if not load_config(self.config_path).windows_wallpaper:
                raise CacheError("Wallpaper is off. Use Turn wallpaper on from the dashboard to enable desktop changes.")
            return self._run_process(
                self._command("--config", str(self.config_path), "wallpaper-next"),
                "Wallpaper refreshed on both monitors.")
        self._start("Refreshing wallpaper from the prepared local set…", work)

    def _open_wallpaper_folder(self) -> None:
        folder = wallpaper_dir(self.config)
        if folder.is_dir():
            os.startfile(folder)
        else:
            self._restore_window()
            messagebox.showinfo("No wallpapers yet", "Apply wallpaper settings to generate your first set.", parent=self.root)

    def _refresh(self) -> None:
        if self.dirty and not self._save():
            return
        if not self.config.albums:
            messagebox.showinfo("Choose albums", "Sign in, then use Choose albums to save a selection first.", parent=self.root)
            return
        self._start("Preparing fresh wallpapers…", lambda: self._run_process(
            self._command("--config", str(self.config_path), "refresh"),
            "Photo download finished. Your local collection is ready."))

    def _open_folder(self) -> None:
        folder = self.config.cache_dir / "photos"
        if not folder.is_dir():
            messagebox.showinfo("No wallpapers yet", "Choose your albums and run the first refresh to create this folder.", parent=self.root)
            return
        try:
            os.startfile(folder)
        except OSError:
            messagebox.showerror("Could not open folder", "Open the displayed wallpaper folder in File Explorer.", parent=self.root)

    def _update_cache_status(self) -> None:
        self._show_wallpaper_mode()
        self.connection_status.set(connection_text(read_connection(self.config.profile_dir)))
        try:
            state = json.loads((self.config.cache_dir / "state.json").read_text(encoding="utf-8"))
            self._dashboard_state = state
            items = state.get("items", {})
            size = sum(item.get("bytes", 0) for item in items.values()) / (1024 * 1024)
            stamp = latest_download(state)
            self.cache_status.set(f"{len(items)} downloaded photos · {size:.1f} MiB\nLatest photo download: {stamp}")
            self._update_download_status(state)
        except (OSError, ValueError, TypeError, AttributeError):
            self._dashboard_state = {}
            self._dashboard_downloading = False
            self.cache_status.set("No photos have been downloaded yet.")
        self._sync_dashboard()

    def _update_download_status(self, state: dict) -> None:
        activity = state.get('download_activity', {})
        active = False
        if activity.get('phase') in ACTIVE_PHASES:
            lock = self.config.cache_dir.parent / f'.{self.config.cache_dir.name}.lock'
            if lock.is_file():
                try:
                    with file_lock(lock):
                        pass
                except CacheError:
                    active = True
        text = activity_text(state, active)
        self._dashboard_downloading = active
        cache = Cache(self.config)
        cache.state = state
        quota = cache.quota_status()
        if quota.next_allowed_at:
            text += f'\nHourly allowance resets: {local_date(quota.next_allowed_at)}'
        self.download_status.set(_safe_output(text))
        if active:
            self.progress.grid()
            self.progress.stop()
            total = activity.get('total', 0)
            if activity.get('phase') == 'downloading' and total:
                self.progress.configure(mode='determinate', maximum=total, value=activity.get('completed', 0))
            else:
                self.progress.configure(mode='indeterminate')
                self.progress.start(12)
        elif not self.busy:
            self.progress.stop()
            self.progress.configure(value=0)
            self.progress.grid_remove()

    def _close(self) -> None:
        if self.busy:
            messagebox.showinfo("An action is running",
                                "Wait for this action to finish. To finish or cancel sign-in, close the dedicated Google browser window first.",
                                parent=self.root)
            return
        if (self.dirty or self.wallpaper_dirty) and not messagebox.askyesno("Unsaved changes", "Close without saving your changes?", parent=self.root):
            return
        self._closing = True
        self.tray.close()
        self.root.destroy()


def launch(config_path: Path) -> None:
    config_path = Path(config_path).absolute()
    if not config_path.exists():
        _write_config(config_path, default_data())
    root = tk.Tk()
    try:
        app = WallpaperApp(root, config_path)
    except (ConfigError, OSError) as exc:
        root.withdraw()
        messagebox.showerror("Google Photos Wallpaper", str(exc), parent=root)
        root.destroy()
        return
    try:
        root.mainloop()
    finally:
        # Also cover a programmatic quit that bypasses WM_DELETE_WINDOW.
        app._closing = True
        app.tray.close()
