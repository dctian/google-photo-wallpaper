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
from datetime import datetime
from typing import Callable
import tkinter as tk
from tkinter import messagebox, ttk

from .cache import CacheError, file_lock
from .config import ConfigError, default_data, load_config
from .source import GooglePhotosSource, SourceError, login
from .tray import TrayIcon
from .wallpapers import wallpaper_dir
from .runtime import resource_dir, command as app_command


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
        self.status = tk.StringVar(value="Manage photo downloads and wallpaper rotation in the tabs above.")
        self.selection = tk.StringVar(value=f"{len(self.config.albums)} saved albums")
        self.cache_status = tk.StringVar()
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

    def _build(self) -> None:
        root = self.root
        root.title("Google Photos Wallpaper")
        root.geometry("960x820")
        root.minsize(850, 700)
        style = ttk.Style(root)
        if "vista" in style.theme_names():
            style.theme_use("vista")
        style.configure("TLabel", font=("Segoe UI", 10))
        style.configure("TButton", font=("Segoe UI", 10), padding=(10, 3))
        style.configure("Title.TLabel", font=("Segoe UI", 21, "bold"))
        style.configure("Subtitle.TLabel", foreground="#536171")
        style.configure("Hint.TLabel", font=("Segoe UI", 9), foreground="#536171")
        style.configure("Treeview", font=("Segoe UI", 10), rowheight=30)
        style.configure("Treeview.Heading", font=("Segoe UI", 10, "bold"))
        outer = ttk.Frame(root, padding=20)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(1, weight=1)
        ttk.Label(outer, text="Your albums, on your desktop", style="Title.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 15))
        notebook = ttk.Notebook(outer)
        notebook.grid(row=1, column=0, sticky="nsew")
        downloader = ttk.Frame(notebook, padding=12)
        wallpaper = ttk.Frame(notebook, padding=18)
        notebook.add(downloader, text="Photo downloader")
        notebook.add(wallpaper, text="Wallpaper")
        downloader.columnconfigure(0, weight=1)
        downloader.rowconfigure(1, weight=1)
        connection = ttk.Frame(downloader)
        connection.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        self._button(connection, "1  Sign in to Google", self._sign_in).pack(side="left")
        self._button(connection, "2  Load my albums", self._load_albums).pack(side="left", padx=(10, 0))
        ttk.Label(connection, text="Private albums stay private", style="Subtitle.TLabel").pack(side="right")

        albums_box = ttk.LabelFrame(downloader, text="Albums", padding=8)
        albums_box.grid(row=1, column=0, sticky="nsew")
        albums_box.columnconfigure(0, weight=1)
        albums_box.rowconfigure(0, weight=1)
        self.album_tree = ttk.Treeview(albums_box, columns=("chosen", "title", "count"), show="headings",
                                       selectmode="none", height=9)
        self.album_tree.heading("chosen", text="Use")
        self.album_tree.heading("title", text="Album")
        self.album_tree.heading("count", text="Items")
        self.album_tree.column("chosen", width=50, anchor="center", stretch=False)
        self.album_tree.column("title", width=600, anchor="w")
        self.album_tree.column("count", width=80, anchor="e", stretch=False)
        self.album_tree.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(albums_box, orient="vertical", command=self.album_tree.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.album_tree.configure(yscrollcommand=scroll.set)
        self.album_tree.bind("<Button-1>", self._toggle_album)
        self.album_tree.bind("<space>", self._toggle_keyboard)
        footer = ttk.Frame(albums_box)
        footer.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        ttk.Label(footer, textvariable=self.selection).pack(side="left")
        self._button(footer, "Select all", lambda: self._select_all(True)).pack(side="right")
        self._button(footer, "Clear", lambda: self._select_all(False)).pack(side="right", padx=(0, 8))

        settings = ttk.LabelFrame(downloader, text="Download & cache settings", padding=8)
        settings.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        for col in (1, 3, 5):
            settings.columnconfigure(col, weight=1)
        ttk.Label(settings, text="Photo attempts per hour").grid(row=0, column=0, sticky="w")
        ttk.Spinbox(settings, textvariable=self.batch_size, from_=1, to=50, width=7,
                    command=self._mark_dirty).grid(row=0, column=1, sticky="w", padx=(8, 20))
        ttk.Label(settings, text="Keep up to").grid(row=0, column=2, sticky="w")
        ttk.Spinbox(settings, textvariable=self.max_photos, from_=1, to=10000, width=7,
                    command=self._mark_dirty).grid(row=0, column=3, sticky="w", padx=(8, 20))
        ttk.Label(settings, text="Disk limit (MiB)").grid(row=0, column=4, sticky="w")
        ttk.Spinbox(settings, textvariable=self.cache_mib, from_=32, to=102400, width=8,
                    command=self._mark_dirty).grid(row=0, column=5, sticky="w", padx=(8, 0))
        ttk.Label(settings, text="Downloaded image size").grid(row=1, column=0, sticky="w", pady=(12, 0))
        resolution = ttk.Combobox(settings, textvariable=self.resolution, state="readonly", width=18,
                                  values=("1920 × 1080", "2560 × 1440", "3840 × 2160", "5120 × 2880", "7680 × 4320"))
        resolution.grid(row=1, column=1, columnspan=2, sticky="w", padx=(8, 20), pady=(12, 0))
        resolution.bind("<<ComboboxSelected>>", lambda event: self._mark_dirty())
        ttk.Label(settings, text="Aspect ratio is preserved; photos are never cropped.",
                  style="Subtitle.TLabel").grid(row=1, column=3, columnspan=3, sticky="w", pady=(12, 0))
        self.optional_settings = ttk.Frame(settings)
        self.optional_settings.grid(row=2, column=0, columnspan=6, sticky="ew", pady=(10, 0))
        ttk.Checkbutton(self.optional_settings, text="Prefer higher resolution; skip near-duplicates",
                        variable=self.quality_filter, command=self._mark_dirty).pack(anchor="w")
        ttk.Checkbutton(self.optional_settings, text="Include this time of year from past years (30%, ±7 days)",
                        variable=self.anniversaries, command=self._mark_dirty).pack(anchor="w", pady=(4, 0))
        ttk.Label(self.optional_settings, text="Local date and image checks, not Google’s curation model.",
                  style="Hint.TLabel").pack(anchor="w", pady=(4, 0))
        ttk.Label(self.optional_settings, textvariable=self.collection_hint,
                  style="Hint.TLabel").pack(anchor="w", pady=(2, 0))
        for variable in (self.batch_size, self.max_photos, self.cache_mib):
            variable.trace_add("write", lambda *_: self._mark_dirty())
        actions = ttk.Frame(downloader)
        actions.grid(row=3, column=0, sticky="ew", pady=(12, 0))
        self._button(actions, "Save downloader settings", self._save).pack(side="left")
        self._button(actions, "Download photos now", self._refresh).pack(side="left", padx=8)
        self._button(actions, "Enable hourly downloads", self._enable_schedule).pack(side="right")
        info = ttk.Frame(downloader)
        info.grid(row=4, column=0, sticky="ew", pady=(10, 0))
        info.columnconfigure(0, weight=1)
        ttk.Label(info, text=str(self.config.cache_dir / "photos"), style="Hint.TLabel", wraplength=650).grid(row=0, column=0, sticky="w")
        self._button(info, "Open photos", self._open_folder).grid(row=0, column=1, padx=(10, 0))

        wallpaper.columnconfigure(0, weight=1)
        ttk.Label(wallpaper, text="Wallpaper generation & rotation", font=("Segoe UI", 15, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(wallpaper, text="Uses photos already on your laptop. Both monitors show the same image.",
                  style="Subtitle.TLabel").grid(row=1, column=0, sticky="w", pady=(8, 20))
        controls = ttk.LabelFrame(wallpaper, text="Wallpaper settings", padding=16)
        controls.grid(row=2, column=0, sticky="ew")
        ttk.Label(controls, text="Layout").grid(row=0, column=0, sticky="w", pady=8)
        layout = ttk.Combobox(controls, textvariable=self.wallpaper_layout, state="readonly", values=("collage", "single"), width=18)
        layout.grid(row=0, column=1, sticky="w", padx=20)
        layout.bind("<<ComboboxSelected>>", lambda _: self._mark_wallpaper_dirty())
        ttk.Label(controls, text="Photos per collage").grid(row=1, column=0, sticky="w", pady=8)
        ttk.Spinbox(controls, textvariable=self.wallpaper_photos, from_=1, to=100, width=8,
                    command=self._mark_wallpaper_dirty).grid(row=1, column=1, sticky="w", padx=20)
        ttk.Label(controls, text="Change wallpaper every (minutes)").grid(row=2, column=0, sticky="w", pady=8)
        ttk.Spinbox(controls, textvariable=self.wallpaper_minutes, from_=1, to=1440, width=8,
                    command=self._mark_wallpaper_dirty).grid(row=2, column=1, sticky="w", padx=20)
        for variable in (self.wallpaper_photos, self.wallpaper_minutes):
            variable.trace_add("write", lambda *_: self._mark_wallpaper_dirty())
        ttk.Label(controls, text="Scattered photo prints, varied angles and sizes, smooth white borders, and soft shadows.",
                  style="Hint.TLabel", wraplength=720).grid(row=3, column=0, columnspan=2, sticky="w", pady=(12, 0))
        wall_actions = ttk.Frame(wallpaper)
        wall_actions.grid(row=3, column=0, sticky="ew", pady=18)
        self._button(wall_actions, "Apply settings & generate", self._apply_wallpaper).pack(side="left")
        self._button(wall_actions, "Refresh wallpaper", self._refresh_wallpaper).pack(side="left", padx=10)
        self._button(wall_actions, "Open wallpapers", self._open_wallpaper_folder).pack(side="left")
        ttk.Label(wallpaper, text="Apply rebuilds the wallpaper set and updates the rotation interval.\nRefresh switches to another prepared collage immediately, using the saved settings.",
                  style="Hint.TLabel", wraplength=760).grid(row=4, column=0, sticky="w")
        ttk.Label(wallpaper, text=str(wallpaper_dir(self.config)), style="Hint.TLabel", wraplength=760).grid(row=5, column=0, sticky="w", pady=(15, 0))
        ttk.Label(wallpaper, text="Pause other wallpaper apps such as JBS when using this mode.",
                  style="Hint.TLabel").grid(row=6, column=0, sticky="w", pady=(15, 0))

        ttk.Label(outer, textvariable=self.cache_status, style="Subtitle.TLabel").grid(row=2, column=0, sticky="w", pady=(10, 0))
        self.progress = ttk.Progressbar(outer, mode="indeterminate")
        self.progress.grid(row=3, column=0, sticky="ew", pady=(8, 6))
        status_label = ttk.Label(outer, textvariable=self.status, wraplength=850)
        status_label.grid(row=4, column=0, sticky="ew")
        outer.bind("<Configure>", lambda event: status_label.configure(wraplength=max(300, event.width-40)))
        support = ttk.Frame(outer)
        support.grid(row=5, column=0, sticky="ew", pady=(10, 0))
        ttk.Label(support, text="Free and open source. Optional support keeps it growing.", style="Hint.TLabel").pack(side="left")
        ttk.Button(support, text="Support this project ☕", command=self._support).pack(side="right")

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
        self.status.set(label)
        for button in self.buttons:
            button.configure(state="disabled")
        self.progress.start(12)

        def run():
            try:
                result = work()
                self.events.put(("done", result, finish))
            except (SourceError, ConfigError, CacheError) as exc:
                self.events.put(("error", str(exc), None))
            except Exception:
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
                    continue
                self.busy = False
                self.progress.stop()
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
        def work():
            config = load_config(self.config_path)
            with file_lock(config.profile_dir.parent / "operation.lock"):
                login(config.profile_dir, browser_channel=config.browser_channel)
            return None

        def verified(_result):
            # _poll has cleared the completed login's busy state before invoking
            # this callback. Album loading starts its own worker and busy state.
            self._load_albums()

        self._start(
            "Sign in in the dedicated Google browser window. When your Google Photos library appears, "
            "CLOSE that browser window. This app will then verify sign-in and load your albums.",
            work, verified)

    def _load_albums(self) -> None:
        def finish(albums):
            saved_urls = { _album_id(url): url for url in self.config.albums }
            selected = set(self.selected_ids)
            self.album_tree.delete(*self.album_tree.get_children())
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
            if not selected:
                raise ConfigError("Load your albums and select at least one before saving.")
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
        self._start("Generating wallpapers from local photos; this can take a few minutes…", lambda: self._run_process(
            self._command("--config", str(self.config_path), "wallpapers", "--enable"),
            "Wallpaper settings applied. Both monitors will change together."))

    def _refresh_wallpaper(self) -> None:
        if self.busy:
            self.status.set("An action is already running. Refresh wallpaper when it finishes.")
            return
        def work():
            if not load_config(self.config_path).windows_wallpaper:
                raise CacheError("Apply wallpaper settings first to prepare and enable your wallpaper set.")
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
            messagebox.showinfo("Choose albums", "Sign in, load your albums, and save a selection first.", parent=self.root)
            return
        self._start("Preparing fresh wallpapers…", lambda: self._run_process(
            self._command("--config", str(self.config_path), "refresh"),
            "Photo download finished. Your local collection is ready."))

    def _enable_schedule(self) -> None:
        if self.dirty and not self._save():
            return
        script = PROJECT_ROOT / "scripts" / "Install-Task.ps1"
        self._start("Setting up hourly refreshes…", lambda: self._run_process(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(script),
             "-ConfigPath", str(self.config_path)],
            "Hourly photo downloads are enabled while you are signed in to Windows."))

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
        try:
            state = json.loads((self.config.cache_dir / "state.json").read_text(encoding="utf-8"))
            items = state.get("items", {})
            size = sum(item.get("bytes", 0) for item in items.values()) / (1024 * 1024)
            last = state.get("last_success")
            stamp = datetime.fromisoformat(last).astimezone().strftime("%b %d, %I:%M %p") if last else "not yet"
            self.cache_status.set(f"{len(items)} downloaded photos · {size:.1f} MiB · Last completed download: {stamp}")
        except (OSError, ValueError, TypeError, AttributeError):
            self.cache_status.set("No photos have been downloaded yet.")

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
