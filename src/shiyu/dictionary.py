"""Larousse public page adapter. No embedded lesson dictionary or audio URLs."""
import re, json, time, urllib.request, urllib.parse, unicodedata
from html.parser import HTMLParser
from pathlib import Path
import hashlib

class FetchError(Exception): pass

def norm(s):
    return unicodedata.normalize('NFC',s).strip().replace('’',"'").lower()

def official(url,audio=False):
    p=urllib.parse.urlsplit(url)
    return p.scheme=='https' and p.hostname=='www.larousse.fr' and not p.username and not p.password and p.port in (None,443) and p.path.startswith('/dictionnaires-prononciation/francais/' if audio else '/dictionnaires/francais-anglais/')

class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        p=urllib.parse.urlsplit(newurl)
        official_file=p.scheme=='https' and p.hostname=='voix.larousse.fr' and p.path.startswith('/francais/') and p.path.endswith('.mp3') and not p.username and p.port in (None,443)
        if not (official(newurl) or official(newurl,True) or official_file):raise FetchError('词典跳转到未支持的地址，请手动核对。')
        return super().redirect_request(req,fp,code,msg,headers,newurl)

def get(url,limit=4_000_000):
    if not (official(url) or official(url,True)):raise FetchError('只支持 Larousse 法英词条和法语发音地址。')
    try:
        req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 (compatible; ShiyuPersonalStudy/1.0)','Accept-Language':'fr,en;q=0.8'})
        with urllib.request.build_opener(SafeRedirect()).open(req,timeout=22) as res:
            b=res.read(limit+1)
            if len(b)>limit:raise FetchError('返回文件过大。')
            return b,res.headers.get('Content-Type','')
    except FetchError:raise
    except Exception as e:raise FetchError('Larousse 暂时无法访问或该词未找到；请联网后重试。') from e

class Node:
    def __init__(self,tag='',attrs=(),parent=None):self.tag=tag;self.attrs=dict(attrs);self.parent=parent;self.children=[]
    def walk(self):
        yield self
        for c in self.children:
            if isinstance(c,Node):yield from c.walk()
    def has(self,cls):return cls in self.attrs.get('class','').split()
    def text(self):return re.sub(r'\s+',' ',' '.join(c.text() if isinstance(c,Node) else c for c in self.children)).strip()

class Tree(HTMLParser):
    def __init__(self):super().__init__(convert_charrefs=True);self.root=Node();self.stack=[self.root]
    def handle_starttag(self,tag,attrs):
        n=Node(tag,attrs,self.stack[-1]);self.stack[-1].children.append(n)
        if tag not in ('br','img','input','meta','link','hr','source','area','wbr'):self.stack.append(n)
    def handle_startendtag(self,tag,attrs):self.handle_starttag(tag,attrs);self.handle_endtag(tag)
    def handle_endtag(self,tag):
        for i in range(len(self.stack)-1,0,-1):
            if self.stack[i].tag==tag:self.stack=self.stack[:i];break
    def handle_data(self,data):self.stack[-1].children.append(data)

def parse(source,requested_url):
    t=Tree();t.feed(source);nodes=list(t.root.walk())
    canonical=next((n.attrs.get('href') for n in nodes if n.tag=='link' and n.attrs.get('rel')=='canonical'),requested_url)
    if not official(canonical):raise FetchError('页面不是有效的 Larousse 法英词条。')
    heads=[n for n in nodes if n.has('ZoneEntree')];senses=[];total_quote_words=0
    for head in heads[:10]:
        hn=list(head.walk());name=next((n.text() for n in hn if n.has('Adresse')),'')
        if not name:continue
        pos=' '.join(n.text() for n in hn if n.has('CategorieGrammaticale'))[:150]
        phon=''.join(n.text() for n in hn if n.has('Phonetique'))[:200]
        audio=[]
        for i,n in enumerate(hn):
            if n.tag!='audio':continue
            url=urllib.parse.urljoin(canonical,n.attrs.get('src',''))
            if not official(url,True):continue
            following=[]
            for nxt in hn[i+1:]:
                if nxt.tag=='audio':break
                following.append(nxt)
            form=next((a.text() for a in following if a.has('Adresse') or a.has('Mot')),name)
            audio.append({'form':form,'url':url,'label':form if not audio else form+'（词条发音变体）','source':canonical})
        # A sense block belongs to its immediately preceding head, never to another entry.
        sibs=head.parent.children;start=sibs.index(head);body=None
        for sib in sibs[start+1:]:
            if not isinstance(sib,Node):continue
            if sib.has('ZoneEntree'):break
            if sib.has('ZoneTexte'):body=sib;break
        quotes=[]
        if body:
            primary=[n for n in body.walk() if n.has('Traduction') and n.attrs.get('lang')=='en']
            if not primary:primary=[n for n in body.walk() if n.has('Traduction2') and n.attrs.get('lang')=='en'][:1]
            for n in primary:
                q=re.sub(r'\([^)]*\)','',n.text()).strip(' ,;')
                q=re.sub(r'^ou\s+','',q)
                if not q or q in quotes or len(q)>75:continue
                count=len(q.split())
                if total_quote_words+count>20:continue
                quotes.append(q);total_quote_words+=count
                if len(quotes)==3:break
        senses.append({'headword':name,'pos':pos,'ipa':phon,'quotes':quotes,'audio':audio,'url':canonical})
    if not senses:raise FetchError('词典页面结构未识别，或该词未找到；没有生成猜测的词典内容。')
    return {'url':canonical,'senses':senses,'fetchedAt':time.strftime('%Y-%m-%d %H:%M:%S'),'adapterVersion':1}

def fetch_entry(lemma):
    if not isinstance(lemma,str) or not lemma.strip() or len(lemma)>100 or any(c in lemma for c in '/\\<>\n'):raise FetchError('请输入单词或短语，不要输入网页地址。')
    url='https://www.larousse.fr/dictionnaires/francais-anglais/'+urllib.parse.quote(lemma.strip(),safe='')
    raw,mime=get(url)
    return parse(raw.decode('utf-8-sig'),url)

def save_audio(asset,root):
    if not official(asset.get('url',''),True):raise FetchError('发音来源无效。')
    raw,mime=get(asset['url'],8_000_000)
    # Some official TTS MP3s have zero padding before their MPEG frames.
    header=raw.lstrip(b'\x00')
    mpeg=len(header)>=4 and header[0]==255 and header[1]&224==224 and header[1]&6!=0 and header[2]&240 not in (0,240)
    if len(raw)<80 or not (header[:3]==b'ID3' or mpeg or header[:4] in (b'RIFF',b'OggS')):raise FetchError('词典没有返回有效音频文件。')
    path='audio/'+hashlib.sha256(raw).hexdigest()+('.wav' if raw[:4]==b'RIFF' else '.ogg' if raw[:4]==b'OggS' else '.mp3')
    full=Path(root)/path;full.parent.mkdir(exist_ok=True,parents=True)
    if not full.exists():full.write_bytes(raw)
    return {**asset,'path':path,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'origin':'Larousse'}

# These are grammatical candidate rules, not a curated dictionary for the sample.
IRREGULAR={
 'suis':['être','suivre'],'es':['être'],'est':['être'],'sommes':['être'],'êtes':['être'],'sont':['être'],
 'étais':['être'],'était':['être'],'étaient':['être'],'été':['être'],'serai':['être'],'seront':['être'],
 'ai':['avoir'],'as':['avoir'],'a':['avoir'],'avons':['avoir'],'avez':['avoir'],'ont':['avoir'],'eu':['avoir'],
 'avais':['avoir'],'avait':['avoir'],'avaient':['avoir'],'aura':['avoir'],
 'vais':['aller'],'vas':['aller'],'va':['aller'],'allons':['aller'],'allez':['aller'],'vont':['aller'],'allé':['aller'],
 'fais':['faire'],'fait':['faire'],'faisons':['faire'],'faites':['faire'],'font':['faire'],
 'peux':['pouvoir'],'peut':['pouvoir'],'pouvons':['pouvoir'],'pouvez':['pouvoir'],'peuvent':['pouvoir'],
 'veux':['vouloir'],'veut':['vouloir'],'voulons':['vouloir'],'voulez':['vouloir'],'veulent':['vouloir'],
 'dois':['devoir'],'doit':['devoir'],'devons':['devoir'],'devez':['devoir'],'doivent':['devoir'],
 'viens':['venir'],'vient':['venir'],'venons':['venir'],'venez':['venir'],'viennent':['venir'],
 'prends':['prendre'],'prend':['prendre'],'prenons':['prendre'],'prenez':['prendre'],'prennent':['prendre'],'pris':['prendre'],
 'dis':['dire'],'dit':['dire'],'dites':['dire'],'lis':['lire'],'lit':['lire'],'lu':['lire'],
 'sais':['savoir'],'sait':['savoir'],'savez':['savoir'],'savons':['savoir'],
 'bonne':['bon'],'bonnes':['bon'],'beaux':['beau'],'belle':['beau'],'belles':['beau'],
 'nouveaux':['nouveau'],'nouvelle':['nouveau'],'nouvel':['nouveau'],'vieille':['vieux'],
 'la':['le'],'les':['le'],"l'":["le"],'aux':['à','le'],'au':['à','le'],'du':['de','le'],'des':['un','de','le']}

def candidates(surface,context=''):
    key=norm(surface);out=[]
    if key in IRREGULAR:out+=IRREGULAR[key]
    if key.endswith('s') and len(key)>3:out.append(key[:-1])
    out.append(surface)
    if key.endswith('aux') and len(key)>4:out.extend([key[:-3]+'al',key[:-1]])
    if key.endswith('x') and len(key)>3:out.append(key[:-1])
    for suffix in ('ons','ez','ent','ais','ait','aient','ées','ée','és','é'):
        if key.endswith(suffix) and len(key)>len(suffix)+2:out.append(key[:-len(suffix)]+'er')
    if key.endswith('es') and len(key)>4:out.extend([key[:-1],key[:-2]])
    if key.endswith('e') and len(key)>4:out.extend([key[:-1],key[:-1]+'er'])
    return list(dict.fromkeys(out))[:8]

def grammar(surface,lemma,context=''):
    k=norm(surface);l=norm(lemma)
    if k in ('le','la','les'):return 'le / la / les 为冠词形式；la 是阴性单数，les 是复数，不属于动词变位。'
    if k in ('au','aux','du','des'):return '可能涉及介词与冠词缩合；需要结合上下文确认。'
    if k!=l and k==l+'s':return '候选原形为 '+lemma+'；可能是复数形式，也可能与动词同形，请核对语境。'
    if k in IRREGULAR and k!=l:return '按常见词形规则提出原形 '+lemma+'；具体语法与语境需核对。'
    if k!=l:return '这是根据词尾提出的候选原形；请核对词性和上下文。'
    return '词形与词典入口相同；请结合词条词性和课内语境选择义项。'

def chinese_pos(pos):
    for fr,zh in [('nom propre féminin','阴性专有名词'),('nom féminin','阴性名词'),('nom masculin','阳性名词'),('article défini','定冠词'),('article indéfini','不定冠词'),('pronom','代词'),('adjectif','形容词'),('adverbe','副词'),('conjonction','连词'),('verbe','动词'),('déterminant','限定词')]:
        if fr in pos:return zh
    return pos
