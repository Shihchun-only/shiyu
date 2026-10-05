"""Run on Windows after installing requirements-build.txt."""
import hashlib,json,os,shutil,subprocess,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];VERSION='0.1.0';OUT=ROOT/'release';BUILD=ROOT/'build'
def run(args):subprocess.run(args,cwd=ROOT,check=True)
def zipdir(source,output):
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(source.rglob('*')):
            if path.is_file():archive.write(path,path.relative_to(source).as_posix())
def main():
    if os.name!='nt':raise SystemExit('Build on Windows to produce Windows executables.')
    OUT.mkdir(exist_ok=True);BUILD.mkdir(exist_ok=True)
    args=[sys.executable,'-m','PyInstaller','--noconfirm','--clean','--windowed','--name','Shiyu','--paths',str(ROOT/'src'),'--distpath',str(BUILD/'app-dist'),'--workpath',str(BUILD/'freeze'),'--specpath',str(BUILD),'--add-data',str(ROOT/'src/shiyu/assets')+';shiyu/assets',str(ROOT/'tools/desktop_entry.py')]
    run(args);app=BUILD/'app-dist/Shiyu'
    for name in ('LICENSE','README.md','CHANGELOG.md'):shutil.copyfile(ROOT/name,app/name)
    shutil.copytree(ROOT/'third-party-notices',app/'third-party-notices',dirs_exist_ok=True)
    manifest={p.relative_to(app).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in app.rglob('*') if p.is_file() and p.name!='files.sha256.json'}
    (app/'files.sha256.json').write_text(json.dumps(manifest,sort_keys=True),'utf8')
    portable=OUT/f'Shiyu-{VERSION}-windows-x64-portable.zip';zipdir(app,portable)
    installer_assets=BUILD/'installer-assets';installer_assets.mkdir(exist_ok=True);shutil.copyfile(portable,installer_assets/'payload.zip')
    run([sys.executable,'-m','PyInstaller','--noconfirm','--clean','--onefile','--windowed','--name',f'Shiyu-{VERSION}-windows-x64-setup','--distpath',str(OUT),'--workpath',str(BUILD/'setup-freeze'),'--specpath',str(BUILD),'--add-data',str(installer_assets/'payload.zip')+';.',str(ROOT/'tools/installer.py')])
    files=[portable,OUT/f'Shiyu-{VERSION}-windows-x64-setup.exe']
    (OUT/'SHA256SUMS.txt').write_text('\n'.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.name for p in files)+'\n','utf8')
    print('RELEASE READY:',*[str(p) for p in files],sep='\n')
if __name__=='__main__':main()
