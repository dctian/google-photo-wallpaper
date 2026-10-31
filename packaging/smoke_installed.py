"""Exercise the installer in a clean Windows CI user account. Never use Google."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import winreg

sys.path.insert(0,str(Path(__file__).resolve().parent.parent))

from PIL import Image
from photo_cache.cache import Cache
from photo_cache.config import load_config
from photo_cache.source import _PROFILE_MARKER


def run(args, env=None):
    result=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                          env=env,timeout=180,creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode:
        raise RuntimeError(result.stdout.decode('utf-8',errors='replace'))
    return result.stdout.decode('utf-8',errors='replace')


def ps(script, *arguments):
    return run(['powershell.exe','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass',
                '-File',str(script),*arguments])


def main():
    if os.environ.get('CI')!='true':
        raise RuntimeError('Run this installer integration check only in a clean CI account.')
    uninstall_key=r'Software\Microsoft\Windows\CurrentVersion\Uninstall\GooglePhotoWallpaper'
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,uninstall_key):
            raise RuntimeError('An existing installation must not be replaced by this test.')
    except FileNotFoundError:
        pass
    setup=Path(sys.argv[1]).resolve()
    with tempfile.TemporaryDirectory(prefix='gpw-installer-') as td:
        root=Path(td)
        installed=root/'installed app'
        # NSIS requires an unquoted /D= value as the final command-line argument.
        result=subprocess.run('"'+str(setup)+'" /S /D='+str(installed),timeout=180)
        assert result.returncode==0
        cli=installed/'GooglePhotoWallpaper-cli.exe'
        gui=installed/'GooglePhotoWallpaper.exe'
        assert cli.is_file() and gui.is_file()
        fake_user=root/'new user \u65c5\u9014'
        env={**os.environ,'LOCALAPPDATA':str(fake_user),'PYTHONIOENCODING':'cp1252'}
        run([str(cli),'--self-test'],env)
        run([str(cli),'init'],env)
        config=fake_user/'GooglePhotosWallpaper'/'config.json'
        data=json.loads(config.read_text(encoding='utf-8'))
        assert Path(data['cache_dir'])==config.parent/'cache'
        assert Path(data['profile_dir'])==config.parent/'browser'
        assert data['albums']==[]
        data['albums']=['https://photos.google.com/album/synthetic-ci']
        config.write_text(json.dumps(data),encoding='utf-8')
        cache=Cache(load_config(config));cache.open()
        key='a'*64
        photo=cache.photos/(key+'.jpg')
        Image.new('RGB',(160,100),'blue').save(photo)
        cache.state['items'][key]={'version':'1','selected':0.0,'bytes':photo.stat().st_size}
        cache.save()
        cache.config.profile_dir.mkdir(parents=True)
        marker=cache.config.profile_dir/_PROFILE_MARKER
        marker.write_text('Synthetic CI profile; no account or cookies.',encoding='utf-8')
        run([str(cli),'--config',str(config),'status','--require-schedulable'],env)
        scripts=installed/'_internal'/'scripts'
        ps(scripts/'Install-Task.ps1','-ConfigPath',str(config))
        ps(scripts/'Install-WallpaperTask.ps1','-ConfigPath',str(config))
        ps(scripts/'Install-Startup.ps1','-ConfigPath',str(config))
        output=run(['powershell.exe','-NoProfile','-Command',
            "Get-ScheduledTask -TaskName GooglePhotosWallpaperRefresh,GooglePhotosWallpaperRotation | ForEach-Object { $_.Actions.Execute; $_.Actions.Arguments }"])
        assert output.count(str(gui))==2 and output.count('--run-task')==2
        run([str(gui),'--run-task','--config',str(config),'--wallpaper-next'],env)
        log=config.parent/'.state'/'wallpaper.log'
        assert 'code 0' in log.read_text(encoding='utf-8')
        # No wallpaper is applied: the synthetic config has windows_wallpaper=False.
        result=subprocess.run([str(installed/'Uninstall.exe'),'/S'],timeout=180)
        assert result.returncode==0
        deadline=time.monotonic()+45
        while gui.exists() and time.monotonic()<deadline:
            time.sleep(.2)
        assert not gui.exists(), 'Installed executable remained after uninstall'
        assert config.is_file() and photo.is_file() and marker.is_file()
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,r'Software\Microsoft\Windows\CurrentVersion\Uninstall') as key_handle:
            try:
                winreg.OpenKey(key_handle,'GooglePhotoWallpaper')
            except FileNotFoundError:
                pass
            else:
                raise AssertionError('Uninstall entry remained')
        print('Installer integration passed: isolated per-user paths, Unicode, bundled driver, jobs, startup and data-preserving uninstall.')


if __name__=='__main__':
    main()
