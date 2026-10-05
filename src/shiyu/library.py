import sqlite3,json,uuid,time,hashlib,base64,io,zipfile,threading,re,os,shutil
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from . import dictionary as dic

def dumps(x):return json.dumps(x,ensure_ascii=False,separators=(',',':'))
def loads(x,default=None):
    try:return json.loads(x)
    except (ValueError,TypeError):return default
def uid():return uuid.uuid4().hex
def now():return time.strftime('%Y-%m-%d %H:%M:%S')
class Library:
    def __init__(self,root):
        self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True)
        for folder in ('images','audio','exports','safety-backups'): (self.root/folder).mkdir(exist_ok=True)
        self.dbpath=self.root/'library.sqlite3';self.lock=threading.RLock();self.executor=ThreadPoolExecutor(max_workers=1);self.job=None;self.cancel=threading.Event();self.ai=None
        with self.db() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS courses(id TEXT PRIMARY KEY,name TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS lessons(id TEXT PRIMARY KEY,course_id TEXT,name TEXT,signature TEXT UNIQUE,deleted_at TEXT,created_at TEXT);
            CREATE TABLE IF NOT EXISTS pages(id TEXT PRIMARY KEY,lesson_id TEXT,position INTEGER,name TEXT,image TEXT,width INTEGER,height INTEGER,annotations TEXT,notes TEXT DEFAULT '');
            CREATE TABLE IF NOT EXISTS words(id TEXT PRIMARY KEY,page_id TEXT,text TEXT,lang TEXT,box TEXT,context TEXT,gloss TEXT,review_note TEXT,manual TEXT DEFAULT '{}',automatic TEXT DEFAULT '{}',status TEXT DEFAULT 'pending',error TEXT DEFAULT '',favorite INTEGER DEFAULT 0);
            CREATE TABLE IF NOT EXISTS entries(key TEXT PRIMARY KEY,data TEXT);
            CREATE TABLE IF NOT EXISTS audio_cache(url TEXT PRIMARY KEY,data TEXT);
            CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT);
            CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY AUTOINCREMENT,time TEXT,kind TEXT,detail TEXT);
            ''')
            db.execute("UPDATE words SET status='pending' WHERE status='processing'")
    @contextmanager
    def db(self):
        db=sqlite3.connect(self.dbpath,timeout=30);db.row_factory=sqlite3.Row;db.execute('PRAGMA foreign_keys=ON')
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback();raise
        finally:db.close()
    def event(self,kind,detail):
        with self.db() as db:db.execute('INSERT INTO events(time,kind,detail) VALUES(?,?,?)',(now(),kind,detail[:2000]))
    def require_idle(self):
        if self.job and self.job.get('running'):raise ValueError('请先暂停处理，等待当前单词完成后再执行此操作。')
    def decode_package(self,raw,name):
        if len(raw)>100*1024*1024:raise ValueError('课件不得超过 100 MB。')
        if name.lower().endswith('.pdf'):
            from pypdf import PdfReader
            pdf=PdfReader(io.BytesIO(raw));encoded=(pdf.metadata or {}).get('/ShiyuCourseB64')
            if encoded:
                data=json.loads(base64.urlsafe_b64decode(str(encoded)+'='*((4-len(encoded)%4)%4)))
            elif 'shiyu-course.json' in pdf.attachments:data=json.loads(pdf.attachments['shiyu-course.json'][0])
            else:raise ValueError('这个 PDF 没有隐藏分类数据，请先制作分类 PDF。')
        else:data=json.loads(raw.decode('utf-8-sig'))
        if data.get('format')!='shiyu.annotated-course' or data.get('schemaVersion')!=1 or not 1<=len(data.get('pages',[]))<=100:raise ValueError('不是支持的分类课件。')
        return data
    @staticmethod
    def validbox(box):return isinstance(box,list) and len(box)==4 and all(type(n) in (float,int) and 0<=n<=1 for n in box) and box[2]>0 and box[3]>0 and box[0]+box[2]<=1.00001 and box[1]+box[3]<=1.00001
    def import_package(self,raw,name,course_name='我的法语课程',lesson_name='',append_to=''):
        with self.lock:
            self.require_idle();data=self.decode_package(raw,name);prepared=[];signature=[]
            for p in data['pages']:
                if not isinstance(p.get('regions'),list) or len(p['regions'])>10000:raise ValueError('页面缺少分类区域。')
                if not (0<int(p.get('width',0))<=30000 and 0<int(p.get('height',0))<=30000):raise ValueError('图片尺寸无效。')
                image=p.get('image','');m=re.fullmatch(r'data:image/(png|jpeg|webp);base64,([A-Za-z0-9+/=]+)',image)
                if not m:raise ValueError('页面图像格式无效。')
                content=base64.b64decode(m[2],validate=True);sha=hashlib.sha256(content).hexdigest();path='images/'+sha+'.'+m[1]
                if not content.startswith((b'\x89PNG',b'\xff\xd8',b'RIFF')):raise ValueError('图像内容无效。')
                regions=[];ids=set()
                for r in p['regions']:
                    if not isinstance(r,dict) or not self.validbox(r.get('box')) or not isinstance(r.get('text'),str) or len(r['text'])>15000 or r.get('id') in ids:raise ValueError('分类区域的位置或文字无效。')
                    ids.add(r.get('id'));regions.append({k:r.get(k,'') for k in ('id','text','kind','lang','box','review','reviewNote')})
                words=[];source_words={w['id']:w for w in p.get('words',[]) if isinstance(w,dict) and 'id' in w}
                for r in regions:
                    if r['kind']=='word' and r['lang']=='fr':
                        w=source_words.get(r['id'],{})
                        # Classification-only context and verbatim source gloss; never consume prefilled dictionary/lemma/audio.
                        words.append({'source_id':r['id'],'text':r['text'],'box':r['box'],'context':str(w.get('sentence') or r['text'])[:2000],'gloss':str(w.get('sourceGloss',''))[:2000],'review_note':r.get('reviewNote') or w.get('reviewNote','')})
                clean={'name':str(p.get('name','课件页'))[:300],'image':path,'content':content,'width':p['width'],'height':p['height'],'regions':regions,'words':words,'pattern':p.get('pattern'),'originalRule':str(p.get('originalRule',''))[:15000],'sourceFilename':str(p.get('sourceFilename',''))[:300]}
                signature.append([sha,regions]);prepared.append(clean)
            sig=hashlib.sha256(dumps(signature).encode()).hexdigest()
            with self.db() as db:
                old=db.execute('SELECT * FROM lessons WHERE signature=?',(sig,)).fetchone()
                if old:return {'lessonId':old['id'],'duplicate':True,'deleted':bool(old['deleted_at'])}
                cidrow=db.execute('SELECT id FROM courses WHERE name=?',(course_name,)).fetchone();cid=cidrow['id'] if cidrow else uid()
                if not cidrow:db.execute('INSERT INTO courses VALUES(?,?)',(cid,course_name[:150] or '我的法语课程'))
                lid=uid();position=0
                if append_to:
                    target=db.execute('SELECT * FROM lessons WHERE id=? AND deleted_at IS NULL',(append_to,)).fetchone()
                    if not target:raise ValueError('追加的节次不存在。')
                    lid=append_to;position=db.execute('SELECT COALESCE(MAX(position),-1)+1 FROM pages WHERE lesson_id=?',(lid,)).fetchone()[0]
                    # Track each imported batch separately without polluting the visible lesson tree.
                    db.execute('INSERT INTO settings VALUES(?,?) ON CONFLICT(key) DO NOTHING',('import:'+sig,lid))
                else:
                    prior=db.execute('SELECT value FROM settings WHERE key=?',('import:'+sig,)).fetchone()
                    if prior:return {'lessonId':prior[0],'duplicate':True}
                    db.execute('INSERT INTO lessons VALUES(?,?,?,?,?,?)',(lid,cid,lesson_name[:150] or name.rsplit('.',1)[0],sig,None,now()))
                if append_to:
                    existing_images={r[0] for r in db.execute('SELECT image FROM pages WHERE lesson_id=?',(lid,))}
                    prepared=[p for p in prepared if p['image'] not in existing_images]
                added=0
                for p in prepared:
                    pid=uid();dest=self.root/p['image']
                    if not dest.exists():dest.write_bytes(p.pop('content'))
                    else:p.pop('content')
                    db.execute('INSERT INTO pages VALUES(?,?,?,?,?,?,?,?,?)',(pid,lid,position,p['name'],p['image'],p['width'],p['height'],dumps({k:p[k] for k in ('regions','pattern','originalRule','sourceFilename')}),''));position+=1;added+=1
                    for w in p['words']:db.execute('INSERT INTO words(id,page_id,text,lang,box,context,gloss,review_note) VALUES(?,?,?,?,?,?,?,?)',(uid(),pid,w['text'],'fr',dumps(w['box']),w['context'],w['gloss'],w['review_note']))
            self.event('import',f'{added} 页分类课件；未使用预配词典内容。')
            return {'lessonId':lid,'added':added,'duplicate':False}
    def state(self):
        with self.db() as db:
            courses=[dict(r) for r in db.execute('SELECT * FROM courses ORDER BY rowid')]
            lessons=[dict(r) for r in db.execute('SELECT l.*,COUNT(DISTINCT p.id) page_count,COUNT(w.id) word_count,SUM(CASE WHEN w.status IN ("done","review") THEN 1 ELSE 0 END) done_count FROM lessons l LEFT JOIN pages p ON p.lesson_id=l.id LEFT JOIN words w ON w.page_id=p.id GROUP BY l.id ORDER BY l.rowid')]
            pages=[{k:r[k] for k in ('id','lesson_id','position','name','image')} for r in db.execute('SELECT * FROM pages ORDER BY position')]
            stats=dict(db.execute('SELECT COUNT(*) total,SUM(favorite) favorites FROM words').fetchone())
            stats['audioFiles']=len(list((self.root/'audio').glob('*')));stats['entries']=db.execute('SELECT COUNT(*) FROM entries').fetchone()[0]
        return {'courses':courses,'lessons':lessons,'pages':pages,'stats':stats,'job':self.job,'dataPath':str(self.root.resolve())}
    def page(self,pid):
        with self.db() as db:
            p=db.execute('SELECT * FROM pages WHERE id=?',(pid,)).fetchone()
            if not p:raise ValueError('页面不存在。')
            p=dict(p);p['annotations']=loads(p['annotations'],{});p['words']=[self.unpack(r) for r in db.execute('SELECT * FROM words WHERE page_id=? ORDER BY rowid',(pid,))];return p
    def unpack(self,r):
        w=dict(r)
        for k in ('box','manual','automatic'):w[k]=loads(w[k],{} if k!='box' else [])
        return w
    def word(self,wid):
        with self.db() as db:r=db.execute('SELECT * FROM words WHERE id=?',(wid,)).fetchone()
        if not r:raise ValueError('单词不存在。')
        return self.unpack(r)
    def edit_word(self,wid,changes):
        with self.lock:
            w=self.word(wid);manual=dict(w['manual'])
            for k in ('lemma','meaning','english','pos','ipa','explanation','example','note','senseIndex','audioIndex'):
                if k in changes:manual[k]=int(changes[k]) if k.endswith('Index') else str(changes[k])[:5000]
            text=str(changes.get('text',w['text'])).strip()[:300]
            if not text:raise ValueError('单词不能为空。')
            lang=changes.get('lang',w['lang'])
            if lang not in ('fr','en','zh','und','und-fonipa','grapheme'):raise ValueError('语言分类无效。')
            box=changes.get('box',w['box'])
            if not self.validbox(box):raise ValueError('点击区域必须在图片内。')
            reset=changes.get('reset',False)
            if reset:manual={}
            context=str(changes.get('context',w['context']))[:3000]
            invalidated=text!=w['text'] or lang!=w['lang'] or context!=w['context'] or ('lemma' in changes and changes['lemma']!=w['manual'].get('lemma',w['automatic'].get('lemma','')))
            # Preserve old result for audit; mark it stale rather than silently reusing wrong audio.
            auto=w['automatic'];status=w['status']
            if invalidated:status='pending';auto['stale']=True
            if 'reviewed' in changes:
                manual['reviewed']=bool(changes['reviewed'])
                if changes['reviewed'] and auto and not auto.get('stale'):status='done' if (auto.get('audio') or {}).get('path') else 'partial'
            with self.db() as db:db.execute('UPDATE words SET text=?,lang=?,box=?,context=?,manual=?,automatic=?,status=?,favorite=? WHERE id=?',(text,lang,dumps(box),context,dumps(manual),dumps(auto),status,int(changes.get('favorite',w['favorite'])),wid))
            return self.word(wid)
    def patch(self,kind,id,data):
        with self.lock:
            if kind=='word':return self.edit_word(id,data)
            self.require_idle()
            with self.db() as db:
                if kind=='course':db.execute('UPDATE courses SET name=? WHERE id=?',(str(data['name'])[:150],id))
                elif kind=='lesson':
                    if 'name'in data:db.execute('UPDATE lessons SET name=? WHERE id=?',(str(data['name'])[:150],id))
                    if 'deleted'in data:db.execute('UPDATE lessons SET deleted_at=? WHERE id=?',(now() if data['deleted'] else None,id))
                    if 'course_id'in data:
                        if not db.execute('SELECT 1 FROM courses WHERE id=?',(data['course_id'],)).fetchone():raise ValueError('课程不存在。')
                        db.execute('UPDATE lessons SET course_id=? WHERE id=?',(data['course_id'],id))
                elif kind=='page':
                    for key in ('notes','name'):
                        if key in data:db.execute(f'UPDATE pages SET {key}=? WHERE id=?',(str(data[key])[:15000],id))
                elif kind=='order':
                    actual={r[0] for r in db.execute('SELECT id FROM pages WHERE lesson_id=?',(id,))}
                    if set(data['ids'])!=actual or len(data['ids'])!=len(actual):raise ValueError('页面列表不一致。')
                    for i,pid in enumerate(data['ids']):db.execute('UPDATE pages SET position=? WHERE id=?',(i,pid))
                else:raise ValueError('操作无效。')
        return {'ok':True}
    def create(self,kind,data):
        id=uid()
        with self.db() as db:
            if kind=='course':db.execute('INSERT INTO courses VALUES(?,?)',(id,str(data.get('name','新课程'))[:150]))
            elif kind=='lesson':
                if not db.execute('SELECT 1 FROM courses WHERE id=?',(data['course_id'],)).fetchone():raise ValueError('课程不存在。')
                db.execute('INSERT INTO lessons VALUES(?,?,?,?,?,?)',(id,data['course_id'],str(data.get('name','新节次'))[:150],uid(),None,now()))
            else:raise ValueError('操作无效。')
        return {'id':id}
    def add_word(self,pid,data):
        self.page(pid);box=data.get('box',[.4,.4,.1,.05]);text=str(data.get('text','')).strip()[:200]
        if not text or not self.validbox(box):raise ValueError('请输入文字与有效位置。')
        id=uid()
        with self.db() as db:db.execute('INSERT INTO words(id,page_id,text,lang,box,context,gloss,review_note) VALUES(?,?,?,?,?,?,?,?)',(id,pid,text,'fr',dumps(box),text,'','用户新增区域'))
        return self.word(id)
    def entry(self,lemma,refresh=False):
        key=dic.norm(lemma)
        with self.db() as db:r=db.execute('SELECT data FROM entries WHERE key=?',(key,)).fetchone()
        if r and not refresh:return loads(r[0])
        entry=dic.fetch_entry(lemma)
        with self.db() as db:db.execute('INSERT INTO entries VALUES(?,?) ON CONFLICT(key) DO UPDATE SET data=excluded.data',(key,dumps(entry)))
        self.event('dictionary',lemma+' → '+entry['url']);return entry
    def audio(self,asset,refresh=False):
        with self.db() as db:r=db.execute('SELECT data FROM audio_cache WHERE url=?',(asset['url'],)).fetchone()
        if r:
            saved=loads(r[0]);p=self.root/saved.get('path','')
            if p.is_file() and not refresh:return saved
        saved=dic.save_audio(asset,self.root)
        with self.db() as db:db.execute('INSERT INTO audio_cache VALUES(?,?) ON CONFLICT(url) DO UPDATE SET data=excluded.data',(asset['url'],dumps(saved)))
        self.event('audio',asset['form']+' 已保存本地音频');return saved
    def process_one(self,wid,refresh=False,ai_enabled=False):
        w=self.word(wid)
        if w['lang']!='fr':return
        with self.db() as db:db.execute("UPDATE words SET status='processing',error='' WHERE id=?",(wid,))
        prior=w['automatic'];manual=w['manual'];guess=None
        try:
            options=dic.candidates(w['text'],w['context'])
            if manual.get('lemma'):options=[manual['lemma']]
            elif ai_enabled and self.ai:
                guess=self.ai.analyze(w)
                if guess.get('lemma'):options=list(dict.fromkeys([guess['lemma']]+options))
            errors=[];entry=None;lemma=None
            # Direct entry first unless a common grammatical form is known.
            if dic.norm(w['text']) not in dic.IRREGULAR and not guess and not manual.get('lemma'):options=[w['text']]+[x for x in options if dic.norm(x)!=dic.norm(w['text'])]
            for candidate in options[:5]:
                if self.cancel.is_set():break
                try:
                    entry=self.entry(candidate,refresh);lemma=candidate;break
                except dic.FetchError as exc:errors.append(str(exc))
            if self.cancel.is_set():
                with self.db() as db:db.execute("UPDATE words SET status='pending' WHERE id=?",(wid,))
                return
            if not entry:raise dic.FetchError(errors[-1] if errors else '尚未获取词典内容。')
            senses=entry['senses'];index=int(manual.get('senseIndex',0));index=max(0,min(index,len(senses)-1));sense=senses[index]
            lemma=sense['headword']
            assets=sense.get('audio',[])
            # Choose a verified matching surface variant when present (e.g. la / les).
            exact=[a for a in assets if dic.norm(a['form'])==dic.norm(w['text'])]
            asset=exact[0] if exact else (assets[0] if assets else None)
            ai=int(manual.get('audioIndex',-1))
            if 0<=ai<len(assets):asset=assets[ai]
            saved=None;audio_error=''
            if asset:
                try:saved=self.audio(asset,refresh)
                except dic.FetchError as exc:audio_error=str(exc)
            else:audio_error='词典当前条目没有可识别的法语音频。'
            transformed=dic.norm(w['text'])!=dic.norm(lemma) and dic.norm(w['text']) not in ('la','les')
            ambiguous=transformed or len({s['pos'] for s in senses})>1 or bool(w['review_note'])
            note=dic.grammar(w['text'],lemma,w['context'])
            if saved and dic.norm(saved['form'])!=dic.norm(w['text']):note+=' 当前播放原形 '+saved['form']+' 的词典发音，不保证等于课内变形的发音。';ambiguous=True
            result={'lemma':lemma,'entry':entry,'senseIndex':index,'ipa':sense['ipa'],'pos':dic.chinese_pos(sense['pos']),'quotes':sense['quotes'],'meaning':w['gloss'],'meaningSource':'课件中文原文' if w['gloss'] else '尚无中文释义；可填写或启用 AI 补充','explanation':note,'audio':saved,'audioError':audio_error,'candidates':options,'processedAt':now(),'stale':False,'ai':guess}
            if guess:
                result['meaning']=str(guess.get('meaning') or w['gloss']);result['meaningSource']='AI 语境补充（请核对）';result['explanation']=str(guess.get('explanation') or note);ambiguous=True
            with self.lock:
                # Never overwrite concurrent personal edits; invalidate if lexical inputs changed during fetch.
                current=self.word(wid)
                if current['text']!=w['text'] or current['context']!=w['context'] or current['manual'].get('lemma')!=manual.get('lemma'):
                    db_status='pending';result['stale']=True
                else:db_status='partial' if not saved else 'review' if ambiguous and not current['manual'].get('reviewed') else 'done'
                with self.db() as db:db.execute('UPDATE words SET automatic=?,status=?,error=? WHERE id=?',(dumps(result),db_status,audio_error,wid))
        except Exception as exc:
            with self.db() as db:db.execute("UPDATE words SET status='failed',error=? WHERE id=?",(str(exc)[:600],wid))
    def start(self,lesson_id='',word_id='',refresh=False,ai_enabled=False):
        with self.lock:
            self.require_idle()
            with self.db() as db:
                if word_id:rows=db.execute('SELECT id FROM words WHERE id=? AND lang="fr"',(word_id,)).fetchall()
                else:
                    sql='SELECT w.id FROM words w JOIN pages p ON p.id=w.page_id JOIN lessons l ON l.id=p.lesson_id WHERE l.deleted_at IS NULL AND w.lang="fr"'
                    args=[]
                    if lesson_id:sql+=' AND l.id=?';args.append(lesson_id)
                    if not refresh:sql+=' AND w.status IN ("pending","partial","failed")'
                    rows=db.execute(sql,args).fetchall()
            ids=[r[0] for r in rows];self.cancel.clear();self.job={'running':True,'total':len(ids),'finished':0,'current':'','refresh':refresh,'startedAt':now()}
            def run():
                try:
                    for wid in ids:
                        if self.cancel.is_set():break
                        self.job['current']=self.word(wid)['text'];self.process_one(wid,refresh,ai_enabled);self.job['finished']+=1
                finally:self.job['running']=False;self.job['paused']=self.cancel.is_set();self.job['current']=''
            self.executor.submit(run);return self.job.copy()
    def search(self,q='',favorites=False):
        with self.db() as db:
            sql='SELECT w.*,p.name page_name,p.lesson_id FROM words w JOIN pages p ON p.id=w.page_id JOIN lessons l ON l.id=p.lesson_id WHERE l.deleted_at IS NULL';args=[]
            if favorites:sql+=' AND w.favorite=1'
            if q:
                like='%'+q.replace('!','!!').replace('%','!%').replace('_','!_')+'%'
                sql+=" AND (w.text LIKE ? ESCAPE '!' OR w.context LIKE ? ESCAPE '!' OR w.gloss LIKE ? ESCAPE '!' OR w.manual LIKE ? ESCAPE '!' OR w.automatic LIKE ? ESCAPE '!' OR p.notes LIKE ? ESCAPE '!' OR p.name LIKE ? ESCAPE '!')";args=[like]*7
            return [self.unpack(r) for r in db.execute(sql+' LIMIT 300',args)]
    def upload_audio(self,wid,raw,name):
        if len(raw)>15_000_000 or len(raw)<80:raise ValueError('音频大小无效，最大 15 MB。')
        if not(raw[:3]==b'ID3' or raw[0]==255 or raw[:4] in (b'RIFF',b'OggS')):raise ValueError('请选择 MP3、WAV 或 OGG 音频。')
        ext='.wav' if raw[:4]==b'RIFF' else '.ogg' if raw[:4]==b'OggS' else '.mp3';path='audio/'+hashlib.sha256(raw).hexdigest()+ext;(self.root/path).write_bytes(raw)
        with self.lock:
            w=self.word(wid);manual=w['manual'];manual['audio']={'path':path,'form':w['text'],'origin':'用户导入','filename':Path(name).name}
            with self.db() as db:db.execute('UPDATE words SET manual=? WHERE id=?',(dumps(manual),wid))
        return self.word(wid)
    def backup(self):
        with self.lock:
            self.require_idle();buf=io.BytesIO();snap=self.root/'exports'/'snapshot.sqlite3'
            with self.db() as source:
                dest=sqlite3.connect(snap);source.backup(dest);dest.close()
            with zipfile.ZipFile(buf,'w',zipfile.ZIP_DEFLATED) as z:
                z.writestr('manifest.json',dumps({'format':'shiyu.backup','version':1,'createdAt':now()}));z.write(snap,'library.sqlite3')
                for folder in ('images','audio'):
                    for p in (self.root/folder).iterdir():
                        if p.is_file():z.write(p,p.relative_to(self.root).as_posix())
            snap.unlink(missing_ok=True);return buf.getvalue()
    def restore(self,raw):
        with self.lock:
            self.require_idle()
            with zipfile.ZipFile(io.BytesIO(raw)) as z:
                infos=z.infolist();names=[i.filename for i in infos]
                if len(names)!=len(set(names)) or sum(i.file_size for i in infos)>1_500_000_000:raise ValueError('备份文件无效或过大。')
                if any(n not in ('manifest.json','library.sqlite3') and not re.fullmatch(r'(images|audio)/[a-f0-9]{64}\.(png|jpeg|webp|mp3|wav|ogg)',n) for n in names):raise ValueError('备份包含不受支持的路径。')
                if loads(z.read('manifest.json'),{}).get('format')!='shiyu.backup':raise ValueError('不是拾语备份。')
                candidate=self.root/'exports'/'restore-candidate.sqlite3';candidate.write_bytes(z.read('library.sqlite3'))
                db=None
                try:
                    db=sqlite3.connect(f'file:{candidate.as_posix()}?mode=ro',uri=True)
                    if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('备份数据库损坏。')
                    schema={r[0]:r[1] for r in db.execute("SELECT name,type FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'")}
                    if set(schema)!= {'courses','lessons','pages','words','entries','audio_cache','settings','events'} or any(v!='table' for v in schema.values()):raise ValueError('备份数据库结构无效。')
                    for image, in db.execute('SELECT image FROM pages'):
                        if image not in names:raise ValueError('备份缺少图片。')
                    for auto,manual in db.execute('SELECT automatic,manual FROM words'):
                        for obj in (loads(auto,{}),loads(manual,{})):
                            path=(obj.get('audio') or {}).get('path')
                            if path and path not in names:raise ValueError('备份缺少音频。')
                    db.close()
                    safety=self.backup();(self.root/'safety-backups'/('恢复前-'+time.strftime('%Y%m%d-%H%M%S')+'.zip')).write_bytes(safety)
                    # Asset names are content hashes, so merging cannot overwrite unrelated files.
                    for name in names:
                        if name.startswith(('images/','audio/')):(self.root/name).write_bytes(z.read(name))
                    os.replace(candidate,self.dbpath)
                    with self.db() as db:db.execute("UPDATE words SET status='pending' WHERE status='processing'")
                    self.job=None;return {'ok':True,'safetyBackup':str(self.root/'safety-backups')}
                finally:
                    if db is not None:db.close()
                    candidate.unlink(missing_ok=True)
