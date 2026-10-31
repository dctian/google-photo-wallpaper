"""Shared entry for GUI and console executables; no developer paths or data."""
import multiprocessing
import runpy
import sys
from pathlib import Path

from photo_cache.runtime import resource_dir


def main():
    multiprocessing.freeze_support()
    arguments = sys.argv[1:]
    if arguments and arguments[0] == '--run-task':
        script = resource_dir()/'scripts'/'run_hidden.pyw'
        sys.argv = [str(script), *arguments[1:]]
        runpy.run_path(str(script), run_name='__main__')
        return 0
    if arguments == ['--self-test']:
        import tempfile
        import tkinter
        import pystray
        import six
        import certifi
        import requests
        from gpwc import payloads
        from PIL import Image
        from playwright.sync_api import sync_playwright
        from playwright._impl._driver import compute_driver_executable
        from photo_cache.wallpapers import compose
        root = tkinter.Tk()
        root.withdraw()
        root.update()
        root.destroy()
        with tempfile.TemporaryDirectory() as folder:
            photo = Path(folder)/'synthetic.jpg'
            Image.new('RGB',(160,100),'blue').save(photo)
            assert compose([photo],(640,480),'collage').size == (640,480)
        node, driver = compute_driver_executable()
        assert Path(node).is_file() and Path(driver).is_file()
        assert Path(certifi.where()).is_file()
        assert payloads.GetAlbumsPage(parse_response=False).rpcid
        assert Path(pystray.__file__).suffix == '.py'
        # Exercise the bundled Node driver without starting a browser or signing in.
        with sync_playwright() as browser:
            assert browser.chromium.name == 'chromium'
        print('Self-test passed: Tk, images, replaceable tray library, HTTPS certificates, Google payloads and browser driver.')
        return 0
    from photo_cache.__main__ import main as cli
    return cli(arguments or ['gui'])


if __name__ == '__main__':
    raise SystemExit(main())
