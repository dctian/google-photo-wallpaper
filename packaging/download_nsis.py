"""Retrieve the official compiler ZIP; reject HTML and unexpected bytes."""
import hashlib
from pathlib import Path
import requests

target=Path(__file__).resolve().parent.parent/'.state'/'tools'/'nsis-3.13.zip'
expected='ba63dffc4410ee89193e1cb5a41989991bd77c61068da17e3156d136b7b0b3d8'
target.parent.mkdir(parents=True,exist_ok=True)
if not target.is_file() or hashlib.sha256(target.read_bytes()).hexdigest()!=expected:
    response=requests.get('https://downloads.sourceforge.net/project/nsis/NSIS%203/3.13/nsis-3.13.zip',timeout=120)
    response.raise_for_status()
    content=response.content
    digest=hashlib.sha256(content).hexdigest()
    if content[:2]!=b'PK' or digest!=expected:
        raise RuntimeError('Official compiler response is not the pinned ZIP (SHA256 '+digest+').')
    target.write_bytes(content)
print('NSIS compiler ZIP checksum verified.')
