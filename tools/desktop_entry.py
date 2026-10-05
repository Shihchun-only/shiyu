"""Frozen executable entry; no Python installation needed by the user."""
import sys,traceback,ctypes
from pathlib import Path
from shiyu.runtime import data_dir
from shiyu.app import main

if __name__=='__main__':
    try:main()
    except SystemExit:raise
    except Exception:
        root=data_dir();root.mkdir(parents=True,exist_ok=True);log=root/'startup-error.log';log.write_text(traceback.format_exc(),'utf8')
        ctypes.windll.user32.MessageBoxW(0,'拾语未能启动。诊断记录已保存至：\n'+str(log)+'\n请将该记录提供给项目维护者。','拾语',16)
        sys.exit(1)
