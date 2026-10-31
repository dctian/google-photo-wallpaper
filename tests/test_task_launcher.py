import importlib.machinery
import importlib.util
import io
from pathlib import Path
import tempfile
import unittest
from unittest import mock


LAUNCHER = Path(__file__).resolve().parents[1] / 'scripts' / 'run_hidden.pyw'
loader = importlib.machinery.SourceFileLoader('task_launcher', str(LAUNCHER))
spec = importlib.util.spec_from_loader(loader.name, loader)
launcher = importlib.util.module_from_spec(spec)
loader.exec_module(launcher)


class TaskLauncherTests(unittest.TestCase):
    def test_rotation_dispatches_only_the_local_wallpaper_command(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            child=mock.MagicMock()
            child.__enter__.return_value=child
            child.stdout=io.BytesIO(b'Local wallpaper applied\n')
            child.wait.return_value=0
            with mock.patch.object(launcher,'PROJECT_ROOT',root), mock.patch.object(launcher.subprocess,'Popen',return_value=child) as popen:
                self.assertEqual(launcher.main(['--config',str(root/'config.json'),'--wallpaper-next']),0)
            self.assertEqual(popen.call_args.args[0][-1],'wallpaper-next')
            self.assertTrue((root/'.state'/'wallpaper.log').is_file())

    def test_hidden_process_preserves_failure_code_and_bounds_logs(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            child = mock.MagicMock()
            child.__enter__.return_value = child
            child.stdout = io.BytesIO(b'x' * (launcher.LOG_LIMIT * 3) + b'\nLast failure\n')
            child.wait.return_value = 37
            with mock.patch.object(launcher, 'PROJECT_ROOT', root), mock.patch.object(
                launcher.subprocess, 'Popen', return_value=child
            ) as popen:
                result = launcher.main(['--config', str(root / 'config.json')])
            self.assertEqual(result, 37)
            self.assertEqual(popen.call_args.kwargs['creationflags'], launcher.subprocess.CREATE_NO_WINDOW)
            self.assertEqual(popen.call_args.kwargs['cwd'], root)
            self.assertEqual(popen.call_args.args[0][-1], 'refresh')
            logs = list((root / '.state').glob('task.log*'))
            self.assertEqual(len(logs), 2)
            self.assertTrue(all(path.stat().st_size <= launcher.LOG_LIMIT for path in logs))
            self.assertIn(b'Last failure', (root / '.state' / 'task.log').read_bytes())
            self.assertIn(b'code 37', (root / '.state' / 'task.log').read_bytes())

    def test_launch_error_is_logged_without_exception_secrets(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with mock.patch.object(launcher, 'PROJECT_ROOT', root), mock.patch.object(
                launcher.subprocess, 'Popen', side_effect=OSError('secret-session-value')
            ):
                self.assertEqual(launcher.main(['--config', str(root / 'config.json')]), 1)
            text = (root / '.state' / 'task.log').read_text()
            self.assertIn('Unable to start', text)
            self.assertNotIn('secret-session-value', text)


if __name__ == '__main__':
    unittest.main()
