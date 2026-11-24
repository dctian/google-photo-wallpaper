"""A compact dashboard with focused editors, without page tabs or nested scrolling."""

import tkinter as tk
from tkinter import ttk, messagebox

from .config import load_config
from .connection_status import local_date, read_connection


BG = '#f3f5f9'
INK = '#172638'
MUTED = '#596b80'
BLUE = '#215cd6'


def label(parent, text='', variable=None, style='TLabel', **kwargs):
    return ttk.Label(parent, text=text, textvariable=variable, style=style, **kwargs)


def card(parent):
    border = tk.Frame(parent, background='white', highlightthickness=1, highlightbackground='#dbe2ec')
    content = ttk.Frame(border, style='Card.TFrame', padding=18)
    content.pack(fill='both', expand=True)
    content.columnconfigure(0, weight=1)
    return border, content


def build(app):
    root = app.root
    root.title('Google Photos Wallpaper')
    root.geometry('960x660')
    root.minsize(860, 610)
    root.configure(background=BG)
    style = ttk.Style(root)
    style.theme_use('clam')
    style.configure('.', font=('Segoe UI', 10), foreground=INK)
    style.configure('TFrame', background='white')
    style.configure('Card.TFrame', background='white')
    style.configure('Page.TFrame', background=BG)
    style.configure('TLabel', background='white', foreground=INK)
    style.configure('Muted.TLabel', foreground=MUTED, background='white', font=('Segoe UI', 9))
    style.configure('Page.TLabel', background=BG, foreground=MUTED, font=('Segoe UI', 9))
    style.configure('Title.TLabel', background=BG, font=('Segoe UI', 21, 'bold'), foreground=INK)
    style.configure('Heading.TLabel', font=('Segoe UI', 14, 'bold'), foreground=INK)
    style.configure('Number.TLabel', font=('Segoe UI', 19, 'bold'))
    style.configure('Strong.TLabel', font=('Segoe UI', 11, 'bold'))
    style.configure('TButton', background='#f8fafc', foreground=INK, bordercolor='#cbd5e2',
                    lightcolor='#f8fafc', darkcolor='#f8fafc', padding=(12, 8), relief='flat')
    style.map('TButton', background=[('active', '#e9eff8'), ('disabled', '#f1f3f6')],
              foreground=[('disabled', '#8793a4')])
    style.configure('Primary.TButton', background=BLUE, foreground='white', bordercolor=BLUE,
                    lightcolor=BLUE, darkcolor=BLUE, font=('Segoe UI', 10, 'bold'))
    style.map('Primary.TButton', background=[('active', '#1849ac'), ('disabled', '#a7b7d6')],
              foreground=[('disabled', '#ffffff')])
    style.configure('Quiet.TButton', borderwidth=0, background='white', foreground=BLUE, padding=(8, 7))
    style.configure('TCheckbutton', background='white', padding=(0, 5))
    style.configure('TEntry', padding=6)
    style.configure('TCombobox', padding=5)
    style.configure('TSpinbox', padding=5)
    style.configure('Treeview', rowheight=30, background='white', fieldbackground='white', borderwidth=0)
    style.configure('Treeview.Heading', background='#edf2f8', font=('Segoe UI', 10, 'bold'), padding=8)
    style.configure('Horizontal.TProgressbar', background=BLUE, troughcolor='#e8edf5', borderwidth=0, thickness=6)
    app.dashboard_variables = {name: tk.StringVar(root) for name in
        ('account', 'checked', 'next', 'last', 'collection', 'plan', 'wallpaper_plan', 'activity', 'detail')}
    app._dialogs = {}
    outer = ttk.Frame(root, style='Page.TFrame', padding=18)
    outer.pack(fill='both', expand=True)
    outer.columnconfigure(0, weight=1)
    outer.rowconfigure(2, weight=1)
    header = ttk.Frame(outer, style='Page.TFrame')
    header.grid(row=0, column=0, sticky='ew', pady=(0, 12))
    label(header, 'Google Photos Wallpaper', style='Title.TLabel').pack(anchor='w')

    account_border, account = card(outer)
    account_border.grid(row=1, column=0, sticky='ew', pady=(0, 12))
    account.configure(padding=(16, 10))
    app.account_dot = tk.Label(account, text='●', background='white', foreground=MUTED, font=('Segoe UI', 13))
    app.account_dot.grid(row=0, column=0, rowspan=2, padx=(0, 10))
    account.columnconfigure(0, weight=0)
    account.columnconfigure(1, weight=1)
    label(account, variable=app.dashboard_variables['account'], style='Strong.TLabel').grid(row=0, column=1, sticky='w')
    label(account, variable=app.dashboard_variables['checked'], style='Muted.TLabel').grid(row=1, column=1, sticky='w')
    app.reconnect_button = app._button(account, 'Sign in to Google', app._sign_in)
    app.reconnect_button.grid(row=0, column=2, rowspan=2, padx=(12, 8))
    app._button(account, 'Check connection', app._check_sign_in).grid(row=0, column=3, rowspan=2)

    body = ttk.Frame(outer, style='Page.TFrame')
    body.grid(row=2, column=0, sticky='nsew')
    body.columnconfigure(0, weight=3, uniform='main')
    body.columnconfigure(1, weight=2, uniform='main')
    body.rowconfigure(0, weight=1)
    download_border, download = card(body)
    download.configure(padding=14)
    download_border.grid(row=0, column=0, sticky='nsew', padx=(0, 14), pady=(0, 14))
    title = ttk.Frame(download)
    title.grid(row=0, column=0, sticky='ew')
    label(title, 'Photo downloads', style='Heading.TLabel').pack(side='left')
    app.schedule_badge = tk.Label(title, text='CHECKING', background='#eef2f7', foreground=MUTED,
                                 font=('Segoe UI', 9, 'bold'), padx=8, pady=4)
    app.schedule_badge.pack(side='left', padx=10)
    settings = app._button(title, 'Settings', lambda: open_download_settings(app))
    settings.configure(style='Quiet.TButton')
    settings.pack(side='right')
    label(download, variable=app.dashboard_variables['plan'], style='Muted.TLabel').grid(row=1, column=0, sticky='w', pady=(4, 10))
    dates = ttk.Frame(download)
    dates.grid(row=2, column=0, sticky='ew')
    dates.columnconfigure((0, 1), weight=1, uniform='date')
    label(dates, 'NEXT AUTOMATIC DOWNLOAD', style='Muted.TLabel').grid(row=0, column=0, sticky='w')
    label(dates, 'LAST PHOTO SAVED', style='Muted.TLabel').grid(row=0, column=1, sticky='w', padx=(12, 0))
    label(dates, variable=app.dashboard_variables['next'], style='Strong.TLabel', wraplength=230).grid(row=1, column=0, sticky='nw', pady=(4, 0))
    label(dates, variable=app.dashboard_variables['last'], style='Strong.TLabel', wraplength=230).grid(row=1, column=1, sticky='nw', padx=(12, 0), pady=(4, 0))
    ttk.Separator(download).grid(row=3, column=0, sticky='ew', pady=10)
    label(download, variable=app.dashboard_variables['activity'], style='Strong.TLabel').grid(row=4, column=0, sticky='w')
    tk.Label(download, textvariable=app.dashboard_variables['detail'], foreground=MUTED, background='white',
             font=('Segoe UI', 9), wraplength=400, height=3, justify='left', anchor='nw').grid(
                 row=5, column=0, sticky='nw', pady=(4, 0))
    app.progress = ttk.Progressbar(download, mode='indeterminate')
    app.progress.grid(row=6, column=0, sticky='ew', pady=(0, 4))
    app.progress.grid_remove()
    download.rowconfigure(7, weight=1)
    actions = ttk.Frame(download)
    actions.grid(row=8, column=0, sticky='ew', pady=(8, 0))
    primary = app._button(actions, 'Download now', app._refresh)
    app.download_button = primary
    primary.configure(style='Primary.TButton')
    primary.pack(side='left', padx=(0, 10))
    app.schedule_button = app._button(actions, 'Checking schedule…', app._toggle_schedule)
    app.schedule_button.pack(side='left')
    app.schedule_button.configure(state='disabled')

    collection_border, collection = card(body)
    collection_border.grid(row=1, column=0, sticky='ew', padx=(0, 14))
    collection.configure(padding=14)
    label(collection, variable=app.dashboard_variables['collection'], style='Strong.TLabel').grid(row=0, column=0, sticky='w')
    label(collection, variable=app.selection, style='Muted.TLabel').grid(row=1, column=0, sticky='w', pady=(3, 0))
    choices = ttk.Frame(collection)
    choices.grid(row=0, column=1, rowspan=2, sticky='e', padx=(12, 0))
    app._button(choices, 'Choose albums', lambda: open_albums(app)).pack(side='left', padx=(0, 8))
    app._button(choices, 'Open photos', app._open_folder).pack(side='left')

    wall_border, wall = card(body)
    wall_border.grid(row=0, column=1, rowspan=2, sticky='nsew')
    wall_header = ttk.Frame(wall)
    wall_header.grid(row=0, column=0, sticky='ew')
    label(wall_header, 'Desktop wallpaper', style='Heading.TLabel').pack(side='left')
    preferences = app._button(wall_header, 'Settings', lambda: open_wallpaper_settings(app))
    preferences.configure(style='Quiet.TButton')
    preferences.pack(side='right')
    app.wallpaper_badge = tk.Label(wall, background='#eef2f7', foreground=MUTED,
                                 font=('Segoe UI', 11, 'bold'), padx=12, pady=6)
    app.wallpaper_badge.grid(row=1, column=0, sticky='w', pady=(16, 12))
    label(wall, variable=app.wallpaper_feature_status, wraplength=260).grid(row=2, column=0, sticky='nw')
    label(wall, variable=app.dashboard_variables['wallpaper_plan'], style='Muted.TLabel',
          wraplength=260).grid(row=3, column=0, sticky='nw', pady=(14, 16))
    app.wallpaper_toggle_button = app._button(wall, 'Turn wallpaper on', app._toggle_wallpaper)
    app.wallpaper_toggle_button.grid(row=4, column=0, sticky='ew')
    app.wallpaper_refresh_button = app._button(wall, 'Next wallpaper', app._refresh_wallpaper)
    app.wallpaper_refresh_button.grid(row=5, column=0, sticky='ew', pady=(8, 0))
    wall.rowconfigure(7, weight=1)

    footer = ttk.Frame(outer, style='Page.TFrame')
    footer.grid(row=3, column=0, sticky='ew', pady=(10, 0))
    ttk.Button(footer, text='Open logs', command=app._open_logs).pack(side='left')
    label(footer, 'Private albums · Local photo cache', style='Page.TLabel').pack(side='left', padx=12)
    ttk.Button(footer, text='Support this project', command=app._support).pack(side='right')


def dialog(app, key, title, size):
    if key in app._dialogs:
        return app._dialogs[key], False
    window = tk.Toplevel(app.root)
    window.withdraw()
    window.title(title)
    window.geometry(size)
    width, height = map(int, size.split('x'))
    window.minsize(640 if key == 'albums' else width, 480 if key == 'albums' else height)
    window.configure(background='white')
    window.transient(app.root)
    app._dialogs[key] = window
    return window, True


def show(window):
    window.deiconify()
    window.update_idletasks()
    parent = window.master
    width, height = window.winfo_width(), window.winfo_height()
    x = max(0, min(parent.winfo_rootx() + (parent.winfo_width() - width) // 2, window.winfo_screenwidth() - width))
    y = max(0, min(parent.winfo_rooty() + (parent.winfo_height() - height) // 2, window.winfo_screenheight() - height - 50))
    window.geometry(f'+{x}+{y}')
    window.lift()
    window.grab_set()
    window.focus_set()


def hide(window):
    window.grab_release()
    window.withdraw()


def reset_download_draft(app):
    app.config = load_config(app.config_path)
    config = app.config
    for variable, value in ((app.batch_size, config.batch_size), (app.max_photos, config.max_photos),
                            (app.cache_mib, config.max_bytes // 1024**2),
                            (app.resolution, f'{config.max_width} × {config.max_height}')):
        variable.set(str(value))
    app.quality_filter.set(config.quality_filter)
    app.anniversaries.set(config.anniversary_fraction > 0)
    app.dirty = False


def reset_wallpaper_draft(app):
    current = load_config(app.config_path)
    app.wallpaper_layout.set(current.wallpaper_layout)
    app.wallpaper_photos.set(str(current.wallpaper_photos_per_image))
    app.wallpaper_minutes.set(str(current.wallpaper_interval_minutes))
    app.wallpaper_dirty = False


def reset_album_draft(app):
    app.config = load_config(app.config_path)
    app.selected_ids = {url.split('?')[0].rstrip('/').rsplit('/', 1)[-1] for url in app.config.albums}
    for item, row in app.album_rows.items():
        app.album_tree.set(item, 'chosen', '✓' if row['id'] in app.selected_ids else '')
    app.dirty = False
    app._update_selection()


def open_download_settings(app):
    window, fresh = dialog(app, 'downloads', 'Download settings', '540x470')
    if fresh:
        frame = ttk.Frame(window, padding=24)
        frame.pack(fill='both', expand=True)
        frame.columnconfigure(1, weight=1)
        label(frame, 'Download settings', style='Heading.TLabel').grid(row=0, column=0, columnspan=2, sticky='w', pady=(0, 6))
        label(frame, 'One small batch each hour. Older photos rotate out.', style='Muted.TLabel').grid(row=1, column=0, columnspan=2, sticky='w', pady=(0, 16))
        for row, (text, variable, low, high) in enumerate((('Photo attempts per hour', app.batch_size, 1, 50),
                ('Keep up to (photos)', app.max_photos, 1, 10000), ('Disk limit (MiB)', app.cache_mib, 32, 102400)), 2):
            label(frame, text).grid(row=row, column=0, sticky='w', pady=6)
            ttk.Spinbox(frame, textvariable=variable, from_=low, to=high, width=11,
                        command=app._mark_dirty).grid(row=row, column=1, sticky='e', pady=6)
        label(frame, 'Maximum image size').grid(row=5, column=0, sticky='w', pady=6)
        sizes = ttk.Combobox(frame, textvariable=app.resolution, state='readonly', width=18,
            values=('1920 × 1080', '2560 × 1440', '3840 × 2160', '5120 × 2880', '7680 × 4320'))
        sizes.grid(row=5, column=1, sticky='e')
        sizes.bind('<<ComboboxSelected>>', lambda _: app._mark_dirty())
        ttk.Checkbutton(frame, text='Prefer higher resolution; skip near-duplicates', variable=app.quality_filter,
                        command=app._mark_dirty).grid(row=6, column=0, columnspan=2, sticky='w', pady=(12, 0))
        ttk.Checkbutton(frame, text='Include memories from this time of year', variable=app.anniversaries,
                        command=app._mark_dirty).grid(row=7, column=0, columnspan=2, sticky='w')
        label(frame, 'Attempts include skipped and failed photos. Images keep their\naspect ratio. Memories use past years within ±7 days.',
              style='Muted.TLabel').grid(row=8, column=0, columnspan=2, sticky='w', pady=(8, 14))
        actions = ttk.Frame(frame)
        actions.grid(row=9, column=0, columnspan=2, sticky='ew')
        def cancel():
            reset_download_draft(app)
            hide(window)
        def save():
            if app._save():
                hide(window)
                sync(app)
        ttk.Button(actions, text='Cancel', command=cancel).pack(side='right', padx=(8, 0))
        save_button = app._button(actions, 'Save settings', save)
        save_button.configure(style='Primary.TButton')
        save_button.pack(side='right')
        window.protocol('WM_DELETE_WINDOW', cancel)
        window.bind('<Escape>', lambda _: cancel())
        for variable in (app.batch_size, app.max_photos, app.cache_mib):
            variable.trace_add('write', lambda *_: app._mark_dirty())
    show(window)


def open_albums(app):
    window, fresh = dialog(app, 'albums', 'Choose your albums', '700x540')
    if fresh:
        frame = ttk.Frame(window, padding=22)
        frame.pack(fill='both', expand=True)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(3, weight=1)
        label(frame, 'Choose your albums', style='Heading.TLabel').grid(row=0, column=0, sticky='w')
        label(frame, 'Click a row or press Space to include an album. Your saved choices are kept.',
              style='Muted.TLabel').grid(row=1, column=0, sticky='w', pady=(6, 14))
        bar = ttk.Frame(frame)
        bar.grid(row=2, column=0, sticky='ew', pady=(0, 10))
        app.album_search = tk.StringVar(app.root)
        search = ttk.Entry(bar, textvariable=app.album_search, width=24)
        label(bar, 'Find album').pack(side='left', padx=(0, 8))
        search.pack(side='left', fill='x', expand=True)
        app._button(bar, 'Reload albums', app._load_albums).pack(side='left', padx=(10, 0))
        table = ttk.Frame(frame)
        table.grid(row=3, column=0, sticky='nsew')
        table.rowconfigure(0, weight=1)
        table.columnconfigure(0, weight=1)
        app.album_tree = ttk.Treeview(table, columns=('chosen', 'title', 'count'), show='headings', selectmode='none', height=9)
        for key, title, width, anchor in (('chosen', 'Use', 45, 'center'), ('title', 'Album', 380, 'w'), ('count', 'Photos', 65, 'e')):
            app.album_tree.heading(key, text=title)
            app.album_tree.column(key, width=width, anchor=anchor, stretch=key == 'title')
        app.album_tree.grid(row=0, column=0, sticky='nsew')
        scroll = ttk.Scrollbar(table, command=app.album_tree.yview)
        scroll.grid(row=0, column=1, sticky='ns')
        app.album_tree.configure(yscrollcommand=scroll.set)
        app.album_tree.bind('<Button-1>', app._toggle_album)
        app.album_tree.bind('<space>', app._toggle_keyboard)
        def filter_albums(*_):
            query = app.album_search.get().casefold()
            for item, row in app.album_rows.items():
                if query in row['title'].casefold():
                    app.album_tree.move(item, '', 'end')
                else:
                    app.album_tree.detach(item)
        app.album_search.trace_add('write', filter_albums)
        tools = ttk.Frame(frame)
        tools.grid(row=4, column=0, sticky='ew', pady=(10, 8))
        label(tools, variable=app.selection, style='Muted.TLabel').pack(side='left')
        app._button(tools, 'Select all albums', lambda: app._select_all(True)).pack(side='right')
        app._button(tools, 'Clear selection', lambda: app._select_all(False)).pack(side='right', padx=8)
        label(frame, variable=app.status, style='Muted.TLabel', wraplength=630).grid(row=5, column=0, sticky='w', pady=(0, 12))
        actions = ttk.Frame(frame)
        actions.grid(row=6, column=0, sticky='ew')
        def cancel():
            reset_album_draft(app)
            hide(window)
        def save():
            if not app.selected_ids:
                messagebox.showerror('Choose albums', 'Select at least one album.', parent=window)
            elif app._save():
                hide(window)
                sync(app)
        ttk.Button(actions, text='Cancel', command=cancel).pack(side='right', padx=(8, 0))
        save_button = app._button(actions, 'Save selection', save)
        save_button.configure(style='Primary.TButton')
        save_button.pack(side='right')
        window.protocol('WM_DELETE_WINDOW', cancel)
        window.bind('<Escape>', lambda _: cancel())
    show(window)
    if not app.loaded_albums:
        app._load_albums()


def open_wallpaper_settings(app):
    window, fresh = dialog(app, 'wallpaper', 'Wallpaper settings', '530x370')
    if fresh:
        frame = ttk.Frame(window, padding=24)
        frame.pack(fill='both', expand=True)
        frame.columnconfigure(1, weight=1)
        label(frame, 'Wallpaper settings', style='Heading.TLabel').grid(row=0, column=0, columnspan=2, sticky='w', pady=(0, 10))
        label(frame, 'Settings never turn wallpaper on. Use the dashboard switch.', style='Muted.TLabel').grid(row=1, column=0, columnspan=2, sticky='w', pady=(0, 15))
        label(frame, 'Layout').grid(row=2, column=0, sticky='w', pady=7)
        layout = ttk.Combobox(frame, textvariable=app.wallpaper_layout, state='readonly', values=('collage', 'single'), width=16)
        layout.grid(row=2, column=1, sticky='e')
        layout.bind('<<ComboboxSelected>>', lambda _: app._mark_wallpaper_dirty())
        for row, (text, variable, high) in enumerate((('Photos per collage', app.wallpaper_photos, 100),
                ('Change every (minutes)', app.wallpaper_minutes, 1440)), 3):
            label(frame, text).grid(row=row, column=0, sticky='w', pady=7)
            ttk.Spinbox(frame, textvariable=variable, from_=1, to=high, width=10,
                        command=app._mark_wallpaper_dirty).grid(row=row, column=1, sticky='e')
            variable.trace_add('write', lambda *_: app._mark_wallpaper_dirty())
        label(frame, 'Both screens show the same image. Changes apply when\nwallpaper is on; photo downloads have a separate schedule.',
              style='Muted.TLabel').grid(row=5, column=0, columnspan=2, sticky='w', pady=(12, 18))
        actions = ttk.Frame(frame)
        actions.grid(row=6, column=0, columnspan=2, sticky='ew')
        app._button(actions, 'Open wallpapers', app._open_wallpaper_folder).pack(side='left')
        def cancel():
            reset_wallpaper_draft(app)
            hide(window)
        def save():
            if app._save_wallpaper_settings():
                hide(window)
                sync(app)
                if app.config.windows_wallpaper:
                    app._apply_wallpaper()
        ttk.Button(actions, text='Cancel', command=cancel).pack(side='right', padx=(8, 0))
        save_button = app._button(actions, 'Save settings', save)
        save_button.configure(style='Primary.TButton')
        save_button.pack(side='right')
        window.protocol('WM_DELETE_WINDOW', cancel)
        window.bind('<Escape>', lambda _: cancel())
    show(window)


def sync(app):
    if not hasattr(app, 'dashboard_variables'):
        return
    v = app.dashboard_variables
    connection = read_connection(app.config.profile_dir)
    status = connection.get('status')
    texts = {'signed_in': ('Google Photos connected', '#16835d'),
             'sign_in_required': ('Google Photos needs sign-in', '#b45309'),
             'check_failed': ('Google Photos connection not verified', '#b45309')}
    title, color = texts.get(status, ('Google Photos not checked yet', MUTED))
    v['account'].set(title)
    app.account_dot.configure(foreground=color)
    checked = local_date(connection.get('checked_at'))
    v['checked'].set('Last checked ' + checked if checked else 'Sign in once to connect your private albums.')
    app.reconnect_button.configure(text='Reconnect' if status == 'signed_in' else 'Sign in to Google')
    schedule = app._schedule_data.get('state')
    app.schedule_badge.configure(text='ON' if schedule == 'on' else 'PAUSED' if schedule == 'off' else 'UNAVAILABLE',
        background='#e3f3ec' if schedule == 'on' else '#eef2f7',
        foreground='#16835d' if schedule == 'on' else MUTED)
    v['next'].set(local_date(app._schedule_data.get('next_run')) or
        ('Waiting for schedule' if schedule == 'on' else 'Paused' if schedule == 'off' else 'Schedule unavailable'))
    v['plan'].set(f'At most {app.config.batch_size} photo attempts per hour')
    v['wallpaper_plan'].set(f'{app.config.wallpaper_photos_per_image}-photo collage · Every {app.config.wallpaper_interval_minutes} min when on'
        if app.config.wallpaper_layout == 'collage' else f'Single photo · Every {app.config.wallpaper_interval_minutes} minutes when on.')
    state = getattr(app, '_dashboard_state', {})
    v['collection'].set(app.cache_status.get().split('\n')[0].replace(' downloaded photos', ' photos')
                        if state.get('items') else 'No photos downloaded yet')
    from .connection_status import latest_download
    v['last'].set(latest_download(state))
    active = getattr(app, '_dashboard_downloading', False)
    signin_first = status == 'sign_in_required' or (not app.config.albums and status != 'signed_in')
    app.download_button.configure(text='Sign in to Google' if signin_first else 'Download now' if app.config.albums else 'Choose albums',
        command=app._sign_in if signin_first else app._refresh if app.config.albums else lambda: open_albums(app),
        state='disabled' if app.busy or active else 'normal')
    if schedule == 'off' and not state.get('items'):
        app.schedule_button.configure(state='disabled')
    phase = state.get('download_activity', {}).get('phase')
    if active:
        heading = 'Downloading photos' if phase == 'downloading' else 'Reading your albums' if phase == 'reading_albums' else 'Connecting to Google Photos'
        detail = app.download_status.get()
    elif app.busy:
        heading, detail = 'Working…', ' '.join(app.status.get().split())
        if 'Sign in in Chrome' in detail:
            heading = 'Complete Google sign-in'
        if len(detail) > 160:
            detail = detail[:130].rstrip() + '… See logs for details.'
    else:
        heading = 'Ready for the next download' if schedule == 'on' else 'Automatic downloads paused' if schedule == 'off' else 'Ready to download'
        if signin_first:
            heading, detail = 'Connect your Google Photos', 'Sign in with Google, then choose the private albums you want.'
        elif state.get('last_error'):
            detail = 'Last run had an issue · ' + (local_date(state.get('last_attempt')) or 'See logs') + '\nOpen logs for the full details.'
        elif not app.config.albums:
            heading, detail = 'Choose albums to get started', 'Select the private albums you want to download.'
        else:
            detail = app.download_status.get().removeprefix('Idle · ')
    v['activity'].set(heading)
    v['detail'].set(detail)
