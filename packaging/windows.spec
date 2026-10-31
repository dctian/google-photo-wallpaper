# PyInstaller uses one shared runtime for a GUI and a console worker.
from pathlib import Path
import importlib.util
import runpy
from PyInstaller.utils.hooks import collect_all, copy_metadata

project = Path(SPECPATH).parent
runpy.run_path(str(project/'packaging'/'runtime_policy.py'),run_name='__main__')
data, binaries, imports = collect_all('playwright')
data += [(str(project/'LICENSE'), 'licenses'),
         (str(project/'THIRD_PARTY_NOTICES.md'), 'licenses'),
         (str(project/'third_party'/'licenses'), 'licenses/dependencies'),
         (str(project/'build'/'runtime-licenses'), 'licenses/runtime')]
for script in ('App-Runtime.ps1','Install-Task.ps1','Install-WallpaperTask.ps1',
               'Install-Startup.ps1','Remove-Task.ps1','Remove-Integration.ps1',
               'Run-Refresh.ps1','run_hidden.pyw'):
    data.append((str(project/'scripts'/script),'scripts'))
# LGPL: ship and load pystray as replaceable, unmodified Python source, outside
# the PYZ archive. Its full matching source archive accompanies binary releases.
tray = Path(importlib.util.find_spec('pystray').origin).parent
for source in tray.rglob('*.py'):
    data.append((str(source), str(Path('pystray')/source.relative_to(tray).parent)))
for package in ('pystray','pillow','playwright','gpwc','six','certifi','requests',
                'pyee','greenlet','lxml','idna','charset-normalizer','urllib3','typing_extensions'):
    data += copy_metadata(package)
a = Analysis([str(project/'packaging'/'entry.py')], pathex=[str(project)],
             binaries=binaries, datas=data,
             hiddenimports=imports+['photo_cache.__main__','photo_cache.gui','six','six.moves.queue','ctypes.wintypes'],
             excludes=['pystray','pytest','unittest','pip','setuptools'],
             noarchive=False, optimize=0)
pyz = PYZ(a.pure)
gui = EXE(pyz, a.scripts, [], exclude_binaries=True, name='GooglePhotoWallpaper',
          version=str(project/'build'/'GooglePhotoWallpaper.version.txt'),
          console=False, debug=False, upx=False, icon=str(project/'build'/'app.ico'))
cli = EXE(pyz, a.scripts, [], exclude_binaries=True, name='GooglePhotoWallpaper-cli',
          version=str(project/'build'/'GooglePhotoWallpaper-cli.version.txt'),
          console=True, debug=False, upx=False, icon=str(project/'build'/'app.ico'))
app = COLLECT(gui, cli, a.binaries, a.datas, strip=False, upx=False,
              name='GooglePhotoWallpaper')
