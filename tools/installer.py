"""Per-user, offline installer. The payload includes the complete frozen app."""
import argparse,ctypes,hashlib,json,os,shutil,subprocess,sys,tempfile,zipfile
from pathlib import Path

VERSION='0.1.0'
RESOURCES=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parent))

def payload():return RESOURCES/'payload.zip'
def target_dir():return Path(os.environ['LOCALAPPDATA'])/'Programs'/'Shiyu'
def psquote(s):return "'"+str(s).replace("'","''")+"'"

def shortcut(path,exe):
    script="$w = New-Object -ComObject WScript.Shell; $s = $w.CreateShortcut("+psquote(path)+"); $s.TargetPath = "+psquote(exe)+"; $s.WorkingDirectory = "+psquote(exe.parent)+"; $s.Description = 'Shiyu French Notebook'; $s.Save()"
    subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',script],check=True,creationflags=subprocess.CREATE_NO_WINDOW,capture_output=True)

def uninstall_script(target,links):
    return '''Add-Type -AssemblyName System.Windows.Forms
$installRoot = '''+psquote(target.resolve())+'''
$marker = Join-Path $installRoot '.shiyu-install.json'
if (-not (Test-Path -LiteralPath $marker)) { exit 1 }
$record = Get-Content -LiteralPath $marker -Raw | ConvertFrom-Json
$resolved = [IO.Path]::GetFullPath($installRoot).TrimEnd('\\')
if ($record.path -ne $resolved -or $record.app -ne 'shiyu' -or $resolved.Length -lt 15 -or -not (Test-Path -LiteralPath (Join-Path $resolved 'Shiyu.exe'))) { exit 2 }
$answer = [System.Windows.Forms.MessageBox]::Show('卸载拾语软件？课程、词义、音频和笔记会保留在本地资料库。请先在设置中退出本地服务。','拾语卸载','YesNo','Question')
if ($answer -ne 'Yes') { exit 0 }
try {
'''+''.join('    Remove-Item -LiteralPath '+psquote(p)+' -ErrorAction SilentlyContinue\n' for p in links)+'''
    Remove-Item -LiteralPath $resolved -Recurse -Force -ErrorAction Stop
    Remove-Item -LiteralPath 'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\ShiyuFrench' -ErrorAction SilentlyContinue
    [System.Windows.Forms.MessageBox]::Show('软件已卸载。学习资料仍保留在 %LOCALAPPDATA%\\Shiyu。','拾语') | Out-Null
} catch { [System.Windows.Forms.MessageBox]::Show('卸载未完成，请先在拾语设置中退出本地服务后重试。','拾语') | Out-Null }
'''

def install(target,integrate=True,desktop=True):
    target=Path(target).resolve()
    if len(str(target))<15 or target==Path(target.anchor):raise ValueError('安装位置无效。')
    marker=target/'.shiyu-install.json'
    if target.exists() and any(target.iterdir()) and not marker.is_file():raise ValueError('目标文件夹已有其他内容，请选择空文件夹。')
    if marker.is_file():
        old=json.loads(marker.read_text('utf8'))
        if old.get('app')!='shiyu' or old.get('path')!=str(target):raise ValueError('安装记录不匹配。')
    # Stage and verify the whole package before touching an existing installation.
    with tempfile.TemporaryDirectory(prefix='shiyu-install-') as stage:
        staged=Path(stage)
        with zipfile.ZipFile(payload()) as archive:
            for info in archive.infolist():
                dest=(staged/info.filename).resolve()
                if not dest.is_relative_to(staged.resolve()) or '\\' in info.filename:raise ValueError('安装文件路径无效。')
            archive.extractall(staged)
        manifest=json.loads((staged/'files.sha256.json').read_text('utf8'))
        for name,expected in manifest.items():
            path=(staged/name).resolve()
            if not path.is_relative_to(staged.resolve()) or hashlib.sha256(path.read_bytes()).hexdigest()!=expected:raise ValueError('安装文件校验失败。')
        if not (staged/'Shiyu.exe').is_file():raise ValueError('安装文件不完整。')
        target.mkdir(parents=True,exist_ok=True)
        for path in staged.rglob('*'):
            if path.is_file():
                dest=target/path.relative_to(staged);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,dest)
    marker.write_text(json.dumps({'app':'shiyu','version':VERSION,'path':str(target)}),'utf8')
    if integrate:
        import winreg
        start=Path(os.environ['APPDATA'])/'Microsoft/Windows/Start Menu/Programs';start.mkdir(parents=True,exist_ok=True)
        links=[start/'拾语.lnk'];shortcut(links[0],target/'Shiyu.exe')
        if desktop:
            buf=ctypes.create_unicode_buffer(32768)
            if ctypes.windll.shell32.SHGetFolderPathW(None,0x10,None,0,buf)==0:
                link=Path(buf.value)/'拾语.lnk';shortcut(link,target/'Shiyu.exe');links.append(link)
        script=target/'uninstall.ps1';script.write_text(uninstall_script(target,links),'utf-8-sig')
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER,r'Software\Microsoft\Windows\CurrentVersion\Uninstall\ShiyuFrench') as key:
            values={'DisplayName':'拾语 · 法语学习助手','DisplayVersion':VERSION,'Publisher':'Shihchun-only','InstallLocation':str(target),'DisplayIcon':str(target/'Shiyu.exe'),'UninstallString':'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "'+str(script)+'"'}
            for k,v in values.items():winreg.SetValueEx(key,k,0,winreg.REG_SZ,v)
            for k in ('NoModify','NoRepair'):winreg.SetValueEx(key,k,0,winreg.REG_DWORD,1)
    return target/'Shiyu.exe'

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--test-target');args=parser.parse_args()
    if args.test_target:
        install(args.test_target,integrate=False);return
    import tkinter as tk
    from tkinter import ttk,messagebox,filedialog
    ui=tk.Tk();ui.title('安装拾语 '+VERSION);ui.geometry('620x460');ui.resizable(False,False)
    frame=ttk.Frame(ui,padding=28);frame.pack(fill='both',expand=True)
    ttk.Label(frame,text='拾语 · 法语学习助手',font=('Microsoft YaHei',21)).pack(anchor='w')
    ttk.Label(frame,text='Windows 10 / 11 · 安装后直接使用 · 无需 Python',font=('Microsoft YaHei',10)).pack(anchor='w',pady=(6,22))
    ttk.Label(frame,text='安装位置（仅当前用户，无需管理员权限）').pack(anchor='w')
    location=tk.StringVar(value=str(target_dir()));ttk.Entry(frame,textvariable=location,width=73).pack(fill='x',pady=8)
    ttk.Button(frame,text='选择文件夹',command=lambda:location.set(filedialog.askdirectory() or location.get())).pack(anchor='w')
    desktop=tk.BooleanVar(value=True);ttk.Checkbutton(frame,text='创建桌面快捷方式',variable=desktop).pack(anchor='w',pady=14)
    ttk.Label(frame,text='课程与学习记录单独保存在 %LOCALAPPDATA%\\Shiyu。\n升级或卸载应用会保留该资料库。\n软件代码采用 MIT 许可证；第三方组件的许可随软件提供。\n此版本未经过代码签名，安装前请核对发布来源与 SHA256。',wraplength=550).pack(anchor='w',pady=8)
    state=ttk.Label(frame,text='');state.pack(anchor='w',pady=8)
    def run():
        button.configure(state='disabled');state.configure(text='正在安装…');ui.update()
        try:
            exe=install(location.get(),desktop=desktop.get());state.configure(text='安装完成。')
            if messagebox.askyesno('安装完成','拾语已安装。现在打开软件？'):subprocess.Popen([str(exe)],creationflags=subprocess.CREATE_NO_WINDOW)
            ui.destroy()
        except Exception as e:messagebox.showerror('安装未完成',str(e));button.configure(state='normal')
    button=ttk.Button(frame,text='安装拾语',command=run);button.pack(anchor='e',pady=10);ui.mainloop()

if __name__=='__main__':
    try:main()
    except Exception as e:
        if '--test-target' in sys.argv:raise
        ctypes.windll.user32.MessageBoxW(0,str(e),'拾语安装未完成',16);sys.exit(1)
