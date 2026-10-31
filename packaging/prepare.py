"""Prepare reproducible runtime notices and an original, locally drawn icon."""
from pathlib import Path
import importlib.metadata as metadata
import json
import shutil
import sys
import runpy
from PIL import Image, ImageDraw
from runtime_policy import require_release_runtime
from PyInstaller.utils.win32.versioninfo import VSVersionInfo, FixedFileInfo, StringFileInfo, StringTable, StringStruct, VarFileInfo, VarStruct

require_release_runtime()

root = Path(__file__).resolve().parent.parent
version=runpy.run_path(str(root/'photo_cache'/'__init__.py'))['__version__']
numbers=tuple(map(int,version.split('.')))+(0,)
target = root/'build'/'runtime-licenses'
target.mkdir(parents=True, exist_ok=True)
for name in ('GooglePhotoWallpaper','GooglePhotoWallpaper-cli'):
    info=VSVersionInfo(ffi=FixedFileInfo(filevers=numbers,prodvers=numbers,
        mask=0x3f,flags=0,OS=0x40004,fileType=1,subtype=0,date=(0,0)),kids=[
        StringFileInfo([StringTable('040904B0',[
            StringStruct('CompanyName','David Tian'),
            StringStruct('FileDescription','Google Photos Wallpaper'),
            StringStruct('FileVersion',version),
            StringStruct('InternalName',name),
            StringStruct('OriginalFilename',name+'.exe'),
            StringStruct('ProductName','Google Photos Wallpaper'),
            StringStruct('ProductVersion',version),
            StringStruct('LegalCopyright','Copyright 2026 David Tian'),
        ])]),VarFileInfo([VarStruct('Translation',[1033,1200])])])
    (root/'build'/(name+'.version.txt')).write_text(str(info),encoding='utf-8')
shutil.copyfile(root/'third_party'/'licenses'/'nsis'/'COPYING',target/'NSIS-COPYING.txt')
base = Path(sys.base_prefix)
license_file = next((p for p in (base/'LICENSE.txt',base/'LICENSE') if p.is_file()), None)
if license_file is None:
    raise RuntimeError('Python runtime license was not found')
shutil.copyfile(license_file,target/'Python-LICENSE.txt')
for path in (base/'tcl').rglob('license*'):
    if path.is_file():
        relative = path.relative_to(base/'tcl')
        dest = target/'Tcl-Tk'/relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path,dest)
packages = ['certifi','charset-normalizer','gpwc','greenlet','idna','lxml','pillow',
            'playwright','pyee','pystray','requests','six','typing_extensions','urllib3']
(target/'runtime-inventory.json').write_text(json.dumps({
    'python':sys.version.split()[0],
    'packages':{name:metadata.version(name) for name in packages},
    'source':'https://github.com/dctian/google-photo-wallpaper',
},indent=2)+'\n',encoding='utf-8')
image = Image.new('RGBA',(256,256),(0,0,0,0))
draw = ImageDraw.Draw(image)
draw.rounded_rectangle((12,24,244,232),radius=36,fill='#2878cc')
draw.rounded_rectangle((36,48,220,208),radius=12,fill='#edf6ff')
draw.ellipse((157,69,192,104),fill='#f4b942')
draw.polygon(((42,190),(102,118),(142,157),(171,131),(214,190)),fill='#328f65')
image.save(root/'build'/'app.ico',sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)])
print('Prepared runtime inventory, licenses and application icon.')
