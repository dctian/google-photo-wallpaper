"""Fail binary releases if development files or developer paths leak in."""
import os
from pathlib import Path, PureWindowsPath
import types
from PyInstaller.archive.readers import ZlibArchiveReader

project=Path(__file__).resolve().parent.parent
bundle=project/'dist'/'GooglePhotoWallpaper'
expected_scripts={'App-Runtime.ps1','Install-Task.ps1','Install-WallpaperTask.ps1',
                  'Install-Startup.ps1','Remove-Task.ps1','Remove-Integration.ps1',
                  'Run-Refresh.ps1','run_hidden.pyw'}
assert {p.name for p in (bundle/'_internal'/'scripts').iterdir()}==expected_scripts
assert not (bundle/'config.json').exists()
assert not (bundle/'_internal'/'config.json').exists()
forbidden=[str(project).casefold(),str(project).replace('\\','/').casefold()]
for path in bundle.rglob('*'):
    if path.is_file() and path.suffix.lower() in {'.ps1','.py','.pyw','.json','.md','.txt'}:
        text=path.read_text(encoding='utf-8',errors='replace').casefold()
        assert not any(value in text for value in forbidden), 'Build directory found in '+path.name
archive=ZlibArchiveReader(str(project/'build'/'windows'/'PYZ-00.pyz'))
assert not any(name=='pystray' or name.startswith('pystray.') for name in archive.toc)

def check_code(code):
    assert not PureWindowsPath(code.co_filename).is_absolute(), 'Absolute compiled source path'
    assert not any(value in code.co_filename.casefold() for value in forbidden)
    for value in code.co_consts:
        if isinstance(value,types.CodeType):
            check_code(value)
        elif isinstance(value,str):
            assert not any(path in value.casefold() for path in forbidden)

for name in archive.toc:
    if name=='photo_cache' or name.startswith('photo_cache.'):
        check_code(archive.extract(name))
for required in ('licenses/LICENSE','licenses/dependencies/pystray/COPYING',
                 'licenses/dependencies/pystray/COPYING.LGPL',
                 'licenses/runtime/Python-LICENSE.txt','licenses/runtime/runtime-inventory.json',
                 'playwright/driver/LICENSE','playwright/driver/package/ThirdPartyNotices.txt'):
    assert (bundle/'_internal'/required).is_file(),required
print('Bundle audit passed: allowlisted scripts, no private config/build paths, replaceable tray source and runtime notices.')
