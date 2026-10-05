"""Windows-local application server. Binds only to loopback; no external assets in UI."""
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from pathlib import Path
import json,urllib.parse,urllib.request,secrets,hmac,mimetypes,threading,sys,os,argparse,webbrowser,traceback
from .library import Library,dumps
from .ai_helper import AIHelper
from .runtime import data_dir,InstanceLock,atomic_json
from . import __version__
APP=Path(__file__).resolve().parent

class Server(ThreadingHTTPServer):
    daemon_threads=True
    def __init__(self,address,lib,token):self.lib=lib;self.token=token;super().__init__(address,Handler)

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def output(self,body,status=200,mime='application/json; charset=utf-8',download=''):
        if isinstance(body,(dict,list)):body=dumps(body).encode()
        if isinstance(body,str):body=body.encode()
        self.send_response(status);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(body)));self.send_header('X-Content-Type-Options','nosniff');self.send_header('Referrer-Policy','no-referrer');self.send_header('Cache-Control','no-store')
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; media-src 'self' blob:; connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'")
        if download:self.send_header('Content-Disposition',"attachment; filename*=UTF-8''"+urllib.parse.quote(download))
        self.end_headers()
        try:self.wfile.write(body)
        except (BrokenPipeError,ConnectionResetError):pass
    def check(self,private=True):
        host=self.headers.get('Host','');port=self.server.server_port
        if host not in ('127.0.0.1:'+str(port),'localhost:'+str(port)):raise PermissionError('仅允许本机访问。')
        origin=self.headers.get('Origin')
        if origin and origin not in ('http://127.0.0.1:'+str(port),'http://localhost:'+str(port)):raise PermissionError('来源无效。')
        if private:
            token=self.headers.get('X-Shiyu-Token','') or self.params.get('t',[''])[0]
            if not hmac.compare_digest(token,self.server.token):raise PermissionError('会话已过期，请重新双击启动软件。')
    def parse(self):
        u=urllib.parse.urlsplit(self.path);self.route=urllib.parse.unquote(u.path);self.params=urllib.parse.parse_qs(u.query)
    def param(self,key,default=''):return self.params.get(key,[default])[0]
    def readbody(self,maxsize=110_000_000):
        n=int(self.headers.get('Content-Length','0'))
        if n<0 or n>maxsize:raise ValueError('文件过大。')
        return self.rfile.read(n)
    def do_GET(self):
        try:
            self.parse();private=self.route.startswith(('/api/','/file/'));self.check(private)
            lib=self.server.lib
            if self.route=='/health':return self.output({'app':'shiyu','version':__version__,'data':str(lib.root.resolve())})
            if self.route=='/api/state':return self.output(lib.state())
            if self.route=='/api/page':return self.output(lib.page(self.param('id')))
            if self.route=='/api/word':return self.output(lib.word(self.param('id')))
            if self.route=='/api/search':return self.output(lib.search(self.param('q'),self.param('favorites')=='1'))
            if self.route=='/api/settings':return self.output({**lib.ai.config(),'version':__version__})
            if self.route=='/api/backup':
                raw=lib.backup();(lib.root/'exports'/'拾语完整备份.zip').write_bytes(raw)
                return self.output(raw,mime='application/zip',download='拾语完整备份.zip')
            if self.route=='/api/sample':return self.output((APP/'assets'/'demo.course.json').read_bytes(),mime='application/json',download='拾语示例.course.json')
            if self.route.startswith('/file/'):
                rel=self.route[6:];p=(lib.root/rel).resolve()
                if not p.is_relative_to(lib.root.resolve()) or rel.split('/')[0] not in ('images','audio','exports') or not p.is_file():raise ValueError('文件不存在。')
                raw=p.read_bytes();mime=mimetypes.guess_type(str(p))[0] or 'application/octet-stream'
                # Full local audio files are small; range support also enables browser seeking.
                rng=self.headers.get('Range','')
                if rng.startswith('bytes=') and ',' not in rng:
                    span=rng[6:].split('-');start=int(span[0] or 0);end=int(span[1]) if len(span)>1 and span[1] else len(raw)-1;end=min(end,len(raw)-1)
                    if not 0<=start<=end<len(raw):return self.output(b'',416,mime)
                    part=raw[start:end+1];self.send_response(206);self.send_header('Content-Type',mime);self.send_header('Content-Range',f'bytes {start}-{end}/{len(raw)}');self.send_header('Accept-Ranges','bytes');self.send_header('Content-Length',str(len(part)));self.end_headers();self.wfile.write(part);return
                return self.output(raw,mime=mime)
            if self.route in ('/','/index.html'):return self.output((APP/'assets'/'index.html').read_bytes(),mime='text/html; charset=utf-8')
            if self.route in ('/app.js','/style.css'):
                p=APP/'assets'/self.route[1:];return self.output(p.read_bytes(),mime='application/javascript; charset=utf-8' if p.suffix=='.js' else 'text/css; charset=utf-8')
            return self.output({'error':'页面不存在'},404)
        except PermissionError as e:self.output({'error':str(e)},403)
        except Exception as e:self.output({'error':str(e)},400)
    def do_POST(self):
        try:
            self.parse();self.check();lib=self.server.lib;route=self.route
            if route=='/api/import':return self.output(lib.import_package(self.readbody(),self.param('name'),self.param('course','我的法语课程'),self.param('lesson'),self.param('append')))
            if route=='/api/restore':return self.output(lib.restore(self.readbody(500_000_000)))
            if route=='/api/audio':return self.output(lib.upload_audio(self.param('id'),self.readbody(15_000_000),self.param('name','我的音频')))
            data=json.loads(self.readbody(1_000_000) or b'{}')
            if route=='/api/process':return self.output(lib.start(data.get('lessonId',''),data.get('wordId',''),bool(data.get('refresh')),bool(data.get('ai'))))
            if route=='/api/pause':lib.cancel.set();return self.output({'ok':True})
            if route=='/api/edit':return self.output(lib.patch(data['kind'],data['id'],data['changes']))
            if route=='/api/create':return self.output(lib.create(data['kind'],data))
            if route=='/api/addword':return self.output(lib.add_word(data['pageId'],data))
            if route=='/api/settings':return self.output(lib.ai.save(data))
            if route=='/api/test-ai':return self.output(lib.ai.analyze({'text':'amis','context':'les amis','gloss':'朋友们'}))
            if route=='/api/export':
                from . import pdf_export
                pages=pdf_export.select(lib,data.get('scope','lesson'),data.get('id',''))
                if data.get('format')=='classified':raw=pdf_export.classified_pdf(lib,pages);name='原图分类课件.pdf'
                elif data.get('format')=='json':
                    package=pdf_export.course_package(lib,pages);(lib.root/'exports'/'分类课程包.course.json').write_text(dumps(package),'utf8')
                    return self.output(package,mime='application/json; charset=utf-8',download='分类课程包.course.json')
                else:raw=pdf_export.compact_pdf(lib,pages,bool(data.get('hide')),bool(data.get('notes',True)));name='A4复习讲义.pdf'
                (lib.root/'exports'/name).write_bytes(raw)
                return self.output(raw,mime='application/pdf',download=name)
            if route=='/api/shutdown':
                lib.require_idle();self.output({'ok':True});threading.Thread(target=self.server.shutdown,daemon=True).start();return
            if route=='/api/open-folder':
                folder=lib.root/('exports' if data.get('folder')=='exports' else '')
                if os.name!='nt':raise ValueError('请按资料路径打开文件夹。')
                os.startfile(str(folder.resolve()));return self.output({'ok':True})
            self.output({'error':'操作不存在'},404)
        except PermissionError as e:self.output({'error':str(e)},403)
        except Exception as e:self.output({'error':str(e)},400)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--version',action='version',version=__version__);parser.add_argument('--data',default=str(data_dir()));parser.add_argument('--port',type=int,default=8766);parser.add_argument('--no-open',action='store_true');args=parser.parse_args()
    root=Path(args.data);root.mkdir(parents=True,exist_ok=True);runfile=root/'running.json'
    if runfile.exists():
        try:
            old=json.loads(runfile.read_text());url=f"http://127.0.0.1:{int(old['port'])}/"
            with urllib.request.urlopen(url+'health',timeout=1) as r:health=json.load(r)
            if health.get('app')=='shiyu' and health.get('data')==str(root.resolve()):
                if not args.no_open:webbrowser.open(url+'#'+old['token'])
                return
        except Exception:pass
    lock=InstanceLock(root)
    if not lock.acquire():
        # Another process may be between acquiring the mutex and writing running.json.
        import time
        for _ in range(60):
            try:
                old=json.loads(runfile.read_text('utf8'));url=f"http://127.0.0.1:{int(old['port'])}/"
                with urllib.request.urlopen(url+'health',timeout=1) as r:health=json.load(r)
                if health.get('app')=='shiyu' and health.get('data')==str(root.resolve()):
                    if not args.no_open:webbrowser.open(url+'#'+old['token'])
                    return
            except Exception:pass
            time.sleep(.2)
        raise RuntimeError('另一个拾语进程正在启动，请稍后重试。')
    lib=Library(root);lib.ai=AIHelper(root);token=secrets.token_urlsafe(32)
    with lib.db() as db:
        row=db.execute("SELECT value FROM settings WHERE key='app-version'").fetchone()
    if row and row['value']!=__version__:
        previous=''.join(c for c in str(row['value'])[:40] if c.isalnum() or c in '.-_') or '旧版'
        (root/'safety-backups'/('升级前-'+previous+'.zip')).write_bytes(lib.backup())
    with lib.db() as db:db.execute("INSERT INTO settings VALUES('app-version',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(__version__,))
    try:server=Server(('127.0.0.1',args.port),lib,token)
    except OSError:server=Server(('127.0.0.1',0),lib,token)
    atomic_json(runfile,{'port':server.server_port,'token':token,'pid':os.getpid()})
    if not args.no_open:threading.Timer(.5,lambda:webbrowser.open(f'http://127.0.0.1:{server.server_port}/#{token}')).start()
    try:server.serve_forever()
    finally:lib.cancel.set();lib.executor.shutdown(wait=True);server.server_close();runfile.unlink(missing_ok=True);lock.close()
if __name__=='__main__':main()
