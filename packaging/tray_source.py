"""Fetch and verify the complete source matching the shipped LGPL library."""
import hashlib
import importlib.metadata
import importlib.util
import io
from pathlib import Path
import tarfile
import requests

root=Path(__file__).resolve().parent.parent
target=root/'dist'/'pystray-0.19.5.tar.gz'
target.parent.mkdir(parents=True,exist_ok=True)
commit='1907f8681d6d421517c63d94f425f9cdd74d0034'
expected='2df980e432f349815c8b1e88f910c085c161a17ce7294f73a0e8d7651c5d9bac'
assert importlib.metadata.version('pystray')=='0.19.5'
if not target.is_file():
    response=requests.get('https://github.com/moses-palmer/pystray/archive/'+commit+'.tar.gz',timeout=60)
    response.raise_for_status()
    target.write_bytes(response.content)
raw=target.read_bytes()
if hashlib.sha256(raw).hexdigest()!=expected:
    raise RuntimeError('Tray source archive checksum mismatch')
library=Path(importlib.util.find_spec('pystray').origin).parent
with tarfile.open(fileobj=io.BytesIO(raw),mode='r:gz') as archive:
    prefix='pystray-'+commit+'/lib/pystray/'
    for source in library.rglob('*.py'):
        name=prefix+source.relative_to(library).as_posix()
        upstream=archive.extractfile(name).read().decode('utf-8').replace('\r\n','\n')
        if upstream!=source.read_text(encoding='utf-8').replace('\r\n','\n'):
            raise RuntimeError('Tray source archive does not match the installed library')
print('Verified complete tray source archive and every shipped Python module.')
