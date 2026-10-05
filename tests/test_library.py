import io,json,tempfile,unittest,wave,zipfile
from pathlib import Path
from unittest.mock import patch
from shiyu.library import Library
from shiyu import dictionary,pdf_export

SAMPLE=Path(__file__).resolve().parents[1]/'src/shiyu/assets/demo.course.json'
class LibraryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.lib=Library(Path(self.temp.name)/'data');self.lid=self.lib.import_package(SAMPLE.read_bytes(),'demo.json')['lessonId']
    def tearDown(self):self.lib.executor.shutdown();self.temp.cleanup()
    def test_only_french_and_duplicate(self):
        words=self.lib.search();self.assertEqual(len(words),9);self.assertTrue(all(w['lang']=='fr' and not w['automatic'] for w in words));self.assertTrue(self.lib.import_package(SAMPLE.read_bytes(),'demo.json')['duplicate'])
    def test_prefilled_dictionary_is_ignored(self):
        p=json.loads(SAMPLE.read_bytes());p['pages'][0]['words'][0].update({'dictionary':{'url':'https://invalid.example'},'audio':'evil','lemma':'wrong'});p['pages'][0]['regions'][0]['text']='modified'
        self.lib.import_package(json.dumps(p).encode(),'modified.json');self.assertTrue(all(not w['automatic'] for w in self.lib.search()))
    def test_caching_edit_and_backup(self):
        word=next(w for w in self.lib.search() if w['text']=='bleu');wid=word['id'];buf=io.BytesIO()
        with wave.open(buf,'wb') as f:f.setnchannels(1);f.setsampwidth(2);f.setframerate(8000);f.writeframes(b'\x00\x00'*800)
        audio=buf.getvalue();url='https://www.larousse.fr/dictionnaires-prononciation/francais/bleu/00001'
        entry={'url':'https://www.larousse.fr/dictionnaires/francais-anglais/bleu/1','senses':[{'headword':'bleu','pos':'adjectif','ipa':'[blø]','quotes':['blue'],'audio':[{'url':url,'form':'bleu'}]}]}
        with patch.object(dictionary,'fetch_entry',return_value=entry) as fetch,patch.object(dictionary,'get',return_value=(audio,'audio/wav')) as get:
            self.lib.process_one(wid);self.lib.edit_word(wid,{'meaning':'蓝色','note':'保留修改','favorite':True});self.lib.process_one(wid)
            self.assertEqual(fetch.call_count,1);self.assertEqual(get.call_count,1)
        backup=self.lib.backup();other=Library(Path(self.temp.name)/'other')
        try:
            other.restore(backup)
            with patch.object(dictionary,'fetch_entry',side_effect=AssertionError('network')),patch.object(dictionary,'get',side_effect=AssertionError('network')):other.process_one(wid)
            w=other.word(wid);self.assertEqual(w['manual']['meaning'],'蓝色');self.assertEqual(w['status'],'done');self.assertEqual((other.root/w['automatic']['audio']['path']).read_bytes(),audio)
            other.edit_word(wid,{'lemma':'blanc'});self.assertTrue(other.word(wid)['automatic']['stale'])
        finally:other.executor.shutdown()
    def test_search_trash_and_restore(self):
        w=self.lib.search()[0];self.lib.edit_word(w['id'],{'favorite':True,'note':'100%_!'});self.assertEqual(len(self.lib.search('100%_!')),1);self.assertEqual(len(self.lib.search(favorites=True)),1)
        self.lib.patch('lesson',self.lid,{'deleted':True});self.assertEqual(self.lib.search(),[]);self.lib.patch('lesson',self.lid,{'deleted':False});self.assertEqual(len(self.lib.search()),9)
    def test_reject_archive_traversal(self):
        b=io.BytesIO()
        with zipfile.ZipFile(b,'w') as z:z.writestr('../escape.txt','bad')
        with self.assertRaises(ValueError):self.lib.restore(b.getvalue())
        self.assertEqual(len(self.lib.search()),9)
    def test_export_reimport(self):
        pages=pdf_export.select(self.lib,'lesson',self.lid);raw=pdf_export.classified_pdf(self.lib,pages);other=Library(Path(self.temp.name)/'pdf')
        try:other.import_package(raw,'demo.pdf');self.assertEqual(len(other.search()),9);self.assertEqual(other.state()['stats']['entries'],0)
        finally:other.executor.shutdown()
    def test_edited_annotation_export(self):
        w=self.lib.search()[0];self.lib.edit_word(w['id'],{'text':'bleue','lang':'en'});p=pdf_export.course_package(self.lib,pdf_export.select(self.lib,'lesson',self.lid))
        self.assertEqual(sum(len(x['words']) for x in p['pages']),8);self.assertTrue(any(r['text']=='bleue' and r['lang']=='en' for r in p['pages'][0]['regions']))

class DictionaryTests(unittest.TestCase):
    def test_source_validation(self):
        self.assertFalse(dictionary.official('https://larousse.fr.evil.test/dictionnaires/francais-anglais/bleu'));self.assertFalse(dictionary.official('http://www.larousse.fr/dictionnaires/francais-anglais/bleu'))
    def test_short_translation_and_audio(self):
        html='<link rel="canonical" href="https://www.larousse.fr/dictionnaires/francais-anglais/bleu/1"><div><div class="ZoneEntree"><audio src="/dictionnaires-prononciation/francais/bleu/1"></audio><span class="Adresse">bleu</span><span class="CategorieGrammaticale">adjectif</span><span class="Phonetique">[blø]</span></div><div class="ZoneTexte"><span class="Traduction" lang="en">blue</span></div></div>'
        d=dictionary.parse(html,'https://www.larousse.fr/dictionnaires/francais-anglais/bleu');s=d['senses'][0];self.assertEqual(s['quotes'],['blue']);self.assertEqual(s['audio'][0]['form'],'bleu')

if __name__=='__main__':unittest.main()
