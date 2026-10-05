from pathlib import Path
import io,json,base64,html,re,threading
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,PageBreak
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib import colors
from pypdf import PdfReader,PdfWriter
from . import library
LOCK=threading.Lock()
def fonts():
    if 'CJK' not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont('CJK',r'C:\Windows\Fonts\msyh.ttc',subfontIndex=0))
        f=Path(__file__).parent/'assets'/'DejaVuSans.ttf';pdfmetrics.registerFont(TTFont('Latin',str(f)))
def markup(s):
    parts=re.split(r'([\u2e80-\u9fff\uff00-\uffef\u3000-\u303f]+)',str(s))
    return ''.join(html.escape(x) if re.search(r'[\u2e80-\u9fff\uff00-\uffef\u3000-\u303f]',x) else '<font name="Latin">'+html.escape(x)+'</font>' for x in parts).replace('\n','<br/>')
def select(lib,scope,id):
    with lib.db() as db:
        if scope=='page':ids=[id]
        elif scope=='favorites':ids=[r[0] for r in db.execute('SELECT DISTINCT p.id FROM pages p JOIN words w ON w.page_id=p.id JOIN lessons l ON l.id=p.lesson_id WHERE w.favorite=1 AND l.deleted_at IS NULL ORDER BY p.position')]
        else:ids=[r[0] for r in db.execute('SELECT id FROM pages WHERE lesson_id=? ORDER BY position',(id,))]
    pages=[lib.page(pid) for pid in ids]
    if scope=='favorites':
        for p in pages:p['words']=[w for w in p['words'] if w['favorite']]
    if not pages:raise ValueError('所选范围没有课件或收藏内容。')
    return pages
def effective(w):
    a=w['automatic'];m=w['manual'];d={**a,**m}
    if 'english' in m:d['quotes']=[m['english']]
    return d
def course_package(lib,pages):
    out=[]
    for p in pages:
        annotations=p['annotations'];regions=[r for r in annotations.get('regions',[]) if not(r['kind']=='word' and r['lang']=='fr')];words=[]
        for w in p['words']:
            regions.append({'id':w['id'],'text':w['text'],'lang':w['lang'],'kind':'word' if w['lang']!='grapheme' else 'grapheme','box':w['box'],'reviewNote':w['review_note']})
            if w['lang']=='fr':
                x,y,ww,hh=w['box'];words.append({'id':w['id'],'text':w['text'],'lang':'fr','x':x,'y':y,'w':ww,'h':hh,'sentence':w['context'],'sourceGloss':w['gloss'],'reviewNote':w['review_note']})
        raw=(lib.root/p['image']).read_bytes();mime='image/'+Path(p['image']).suffix[1:]
        out.append({'id':p['id'],'name':p['name'],'image':'data:'+mime+';base64,'+base64.b64encode(raw).decode(),'width':p['width'],'height':p['height'],'regions':regions,'words':words,'phrases':[],'pattern':annotations.get('pattern'),'originalRule':annotations.get('originalRule',''),'sourceFilename':annotations.get('sourceFilename',''),'notes':p['notes']})
    return {'format':'shiyu.annotated-course','schemaVersion':1,'stage':'classification-only','pages':out}
def classified_pdf(lib,pages):
    with LOCK:
        fonts();package=course_package(lib,pages);payload=library.dumps(package).encode();buf=io.BytesIO();c=canvas.Canvas(buf,pagesize=(1280,800))
        for p, classified in zip(pages,package['pages']):
            width=1280;height=width*p['height']/p['width'];c.setPageSize((width,height));c.drawImage(str(lib.root/p['image']),0,0,width,height)
            for r in classified['regions']:
                if r['kind'] in ('nontext','ui'):continue
                x,y,w,h=r['box'];font='CJK' if re.search(r'[\u4e00-\u9fff]',r['text']) else 'Latin';size=max(5,h*height*.7);t=c.beginText(x*width,height-y*height-h*height*.85);t.setFont(font,size);t.setTextRenderMode(3);sw=pdfmetrics.stringWidth(r['text'],font,size)
                if sw:t.setHorizScale(100*w*width/sw)
                t.textOut(r['text']);c.drawText(t)
            c.showPage()
        c.save();writer=PdfWriter();writer.append(PdfReader(buf));writer.add_attachment('shiyu-course.json',payload);writer.add_metadata({'/Title':'拾语 - 分类课件','/ShiyuFormat':'shiyu.annotated-course/1','/ShiyuCourseB64':base64.urlsafe_b64encode(payload).decode().rstrip('=')});result=io.BytesIO();writer.write(result);return result.getvalue()
def compact_pdf(lib,pages,hide=False,include_notes=True):
    with LOCK:
        fonts();body=ParagraphStyle('body',fontName='CJK',fontSize=9,leading=13,wordWrap='CJK',textColor=colors.HexColor('#25372f'));small=ParagraphStyle('small',parent=body,fontSize=7.5,leading=11,textColor=colors.HexColor('#62746b'));heading=ParagraphStyle('head',parent=body,fontSize=13,leading=20,spaceBefore=12,spaceAfter=7,textColor=colors.HexColor('#285b49'));title=ParagraphStyle('title',parent=heading,fontSize=23,leading=31,spaceBefore=0)
        def P(s,style=body):return Paragraph(markup(s),style)
        def T(rows,widths):
            t=Table([[P(x,small if i==0 else body) for x in row] for i,row in enumerate(rows)],colWidths=widths,repeatRows=1,hAlign='LEFT',splitInRow=1)
            t.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('BACKGROUND',(0,0),(-1,0),colors.HexColor('#edf3ef')),('LINEBELOW',(0,0),(-1,-1),.3,colors.HexColor('#cdd9d1')),('TOPPADDING',(0,0),(-1,-1),4),('BOTTOMPADDING',(0,0),(-1,-1),4)]));return t
        story=[P('法语课程 · 复习讲义',title),P('依据本地保存内容生成 · '+library.now()+' · '+str(len(pages))+' 页课件',small)]
        rules=[]
        for p in pages:
            an=p['annotations'];pattern=an.get('pattern')
            if pattern:rules.append([pattern.get('text',''),pattern.get('ipa',''),', '.join(dict.fromkeys(w['text'] for w in p['words'] if w['lang']=='fr'))])
            elif an.get('originalRule') and p['words']:story += [P(p['name'],heading),P(an['originalRule'])]
        if rules:story += [P('课件发音组合',heading),T([['字母组合','课件音标','课内词汇']]+rules,[110,110,287])]
        if include_notes:
            for p in pages:
                if p['notes']:story += [P('我的笔记 · '+p['name'],heading),P(p['notes'])]
        story.append(Spacer(1,12))
        story.append(P('词汇与语境'+(' · 自测版' if hide else ''),heading))
        story.append(P('英文为词典短摘录或个人修订；中文注明来源。词典音标保留网页写法。',small))
        unique={}
        for p in pages:
            for w in p['words']:
                if w['lang']=='fr':unique.setdefault((w['text'],w['context']),w)
        rows=[['课内形式 / 原形','音标 / 词性','含义与来源']];sources={}
        for w in unique.values():
            d=effective(w);lemma=d.get('lemma','待处理');english='; '.join(d.get('quotes',[]));meaning=d.get('meaning') or w['gloss'] or '中文待补充';src='个人修订' if w['manual'].get('meaning') else d.get('meaningSource','课件原文')
            value='________________\n________________' if hide else english+'\n'+meaning+(' · '+src if d.get('meaning') or w['gloss'] else '')
            if d.get('stale'):value+='\n词形已修改，词典结果待更新。'
            label=w['text']+(' → '+lemma if lemma!=w['text'] else '')
            if w['context']!=w['text']:label+='\n'+w['context']
            rows.append([label,d.get('ipa','')+'\n'+d.get('pos',''),value])
            url=d.get('entry',{}).get('url')
            if url:sources[url]=lemma
        story.append(T(rows,[152,115,240]))
        review=[w['text']+'：'+w['review_note'] for w in unique.values() if w['review_note']]
        if review:story += [P('需注意的标注',heading),P('\n'.join(review),small)]
        if hide:
            story += [PageBreak(),P('自测答案',title)]
            for w in unique.values():
                d=effective(w);story.append(P(w['text']+'：'+'; '.join(d.get('quotes',[]))+' / '+(d.get('meaning') or w['gloss'] or '待补充')))
        if sources:
            story.append(P('词典来源 · 点击查看',heading));links=['<link href="'+html.escape(url,quote=True)+'" color="#285b49">'+html.escape(label)+'</link>' for url,label in sources.items()];story.append(Paragraph(' · '.join(links),ParagraphStyle('refs',parent=small,fontName='Latin')))
        def footer(c,doc):c.setFont('CJK',8);c.setFillColor(colors.HexColor('#6a796f'));c.drawString(44,24,'拾语 / 课件原文、词典与个人修订分别保存');c.drawRightString(A4[0]-44,24,str(doc.page))
        buf=io.BytesIO();doc=SimpleDocTemplate(buf,pagesize=A4,leftMargin=44,rightMargin=44,topMargin=35,bottomMargin=42,title='拾语 - A4复习讲义');doc.build(story,onFirstPage=footer,onLaterPages=footer);return buf.getvalue()
