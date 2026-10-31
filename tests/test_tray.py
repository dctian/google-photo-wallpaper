from __future__ import annotations

from pathlib import Path
import queue
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from photo_cache.gui import WallpaperApp
from photo_cache.tray import TrayIcon


class FakeIcon:
    def __init__(self, *, delayed=False, fail=False):
        self.visible = False
        self.allow_ready = threading.Event()
        if not delayed:
            self.allow_ready.set()
        self.started = threading.Event()
        self.stopped = threading.Event()
        self.finished = threading.Event()
        self.stop_calls = 0
        self.fail = fail

    def run(self, setup):
        try:
            self.started.set()
            if self.fail:
                raise RuntimeError("backend failed")
            self.allow_ready.wait(2)
            setup(self)
            self.stopped.wait(2)
        finally:
            self.finished.set()

    def stop(self):
        self.stop_calls += 1
        self.stopped.set()


class TrayLifecycleTests(unittest.TestCase):
    def test_one_icon_for_repeated_minimize_and_idempotent_cleanup(self):
        events = queue.Queue()
        created = []

        def factory(post):
            icon = FakeIcon(delayed=True)
            icon.post = post
            created.append(icon)
            return icon

        tray = TrayIcon(events.put, factory)
        self.addCleanup(tray.close)
        tray.show()
        tray.show()
        self.assertEqual(len(created), 1)
        icon = created[0]
        self.assertTrue(icon.started.wait(1))
        self.assertFalse(icon.visible)
        icon.allow_ready.set()
        self.assertEqual(events.get(timeout=1), "tray_ready")
        self.assertTrue(icon.visible)
        tray.show()
        self.assertEqual(events.get(timeout=1), "tray_ready")
        self.assertEqual(len(created), 1)
        tray.close()
        tray.close()
        self.assertTrue(icon.finished.wait(1))
        self.assertEqual(icon.stop_calls, 1)

    def test_exit_during_startup_suppresses_ready_and_late_callbacks(self):
        events = queue.Queue()
        icon = FakeIcon(delayed=True)
        posts = []

        def factory(post):
            posts.append(post)
            return icon

        tray = TrayIcon(events.put, factory)
        tray.show()
        self.assertTrue(icon.started.wait(1))
        tray.close()
        icon.allow_ready.set()
        self.assertTrue(icon.finished.wait(1))
        posts[0]("tray_show")
        tray.show()
        self.assertTrue(events.empty())
        self.assertFalse(icon.visible)

    def test_backend_failure_reports_error_instead_of_ready(self):
        events = queue.Queue()
        icon = FakeIcon(fail=True)
        tray = TrayIcon(events.put, lambda post: icon)
        self.addCleanup(tray.close)
        tray.show()
        self.assertEqual(events.get(timeout=1), "tray_error")
        self.assertFalse(icon.visible)

    def test_missing_backend_reports_error_without_hiding_application(self):
        events = queue.Queue()

        def missing(post):
            raise ImportError("not installed")

        tray = TrayIcon(events.put, missing)
        self.addCleanup(tray.close)
        tray.show()
        self.assertEqual(events.get_nowait(), "tray_error")


class FakeRoot:
    def __init__(self):
        self.window_state = "iconic"
        self.withdraw_calls = 0
        self.focus_calls = 0

    def state(self, value=None):
        if value is not None:
            self.window_state = value
        return self.window_state

    def withdraw(self):
        self.withdraw_calls += 1
        self.window_state = "withdrawn"

    def deiconify(self):
        self.window_state = "normal"

    def lift(self):
        pass

    def focus_force(self):
        self.focus_calls += 1


class WindowTrayTests(unittest.TestCase):
    def app(self):
        app = object.__new__(WallpaperApp)
        app.root = FakeRoot()
        app._closing = False
        app._hidden_to_tray = False
        app._tray_minimize_pending = False
        app.busy = True
        app.config = SimpleNamespace(cache_dir=Path("not-created"))
        app.status = SimpleNamespace(set=lambda value: None)
        app.tray = SimpleNamespace(show=lambda: None)
        app._update_cache_status = Mock()
        return app

    def test_window_hides_only_after_tray_is_ready_and_restores(self):
        app = self.app()
        app._minimize_to_tray()
        self.assertEqual(app.root.withdraw_calls, 0)
        app._handle_tray_event("tray_ready")
        self.assertEqual(app.root.withdraw_calls, 1)
        self.assertTrue(app._hidden_to_tray)
        self.assertTrue(app.busy)  # Tray events must not finish background work.
        app._handle_tray_event("tray_show")
        self.assertEqual(app.root.state(), "normal")
        self.assertFalse(app._hidden_to_tray)
        self.assertTrue(app.busy)
        app._update_cache_status.assert_called_once_with()

    def test_restore_before_tray_startup_completes_does_not_rehide(self):
        app = self.app()
        app._minimize_to_tray()
        app.root.state("normal")
        app._handle_tray_event("tray_ready")
        self.assertEqual(app.root.withdraw_calls, 0)
        self.assertFalse(app._tray_minimize_pending)

    def test_backend_failure_restores_minimized_window(self):
        app = self.app()
        app._minimize_to_tray()
        app._handle_tray_event("tray_error")
        self.assertEqual(app.root.state(), "normal")
        self.assertFalse(app._tray_minimize_pending)


if __name__ == "__main__":
    unittest.main()
