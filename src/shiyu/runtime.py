import ctypes,hashlib,os,sys,json
from pathlib import Path

def data_dir():
    if os.name=='nt':return Path(os.environ.get('LOCALAPPDATA',Path.home()/'AppData/Local'))/'Shiyu'
    return Path(os.environ.get('XDG_DATA_HOME',Path.home()/'.local/share'))/'shiyu'

class InstanceLock:
    """Hold a per-data-directory Windows mutex, including while starting up."""
    def __init__(self,path):self.path=Path(path).resolve();self.handle=None
    def acquire(self):
        if os.name!='nt':return True
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.CreateMutexW.argtypes=[ctypes.c_void_p,ctypes.c_bool,ctypes.c_wchar_p];kernel.CreateMutexW.restype=ctypes.c_void_p
        kernel.CloseHandle.argtypes=[ctypes.c_void_p];kernel.CloseHandle.restype=ctypes.c_bool
        self.kernel=kernel;name='Local\\Shiyu-'+hashlib.sha256(str(self.path).lower().encode()).hexdigest()
        self.handle=kernel.CreateMutexW(None,False,name)
        if not self.handle:raise OSError(ctypes.get_last_error(),'Unable to create application lock')
        if ctypes.get_last_error()==183:self.close();return False
        return True
    def close(self):
        if self.handle:self.kernel.CloseHandle(self.handle);self.handle=None

def atomic_json(path,value):
    path=Path(path);temp=path.with_suffix('.tmp');temp.write_text(json.dumps(value,ensure_ascii=False),'utf8');os.replace(temp,path)
