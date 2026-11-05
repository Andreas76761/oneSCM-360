import tempfile,unittest
from pathlib import Path
import app
class AppendixTests(unittest.TestCase):
 def test_three_languages_internal_isolation_and_repeat_binding(self):
  with tempfile.TemporaryDirectory() as folder:
   s=app.Store(Path(folder)/'db.sqlite3');o=s.save(app.new_outline('Manual'))
   translations={lang:{'title':title,'text':'Definition '+lang,'approved':True} for lang,title in [('de','Vertrag'),('en','Contract'),('fr','Contrat')]}
   e=s.appendices.save({'kind':'glossary','internal':False,'note':'PRIVATE-SECRET','translations':translations})
   s.appendices.save({'kind':'faq','internal':True,'translations':translations})
   for lang in ['de','en','fr']:
    result=s.appendices.preview({'language':lang});self.assertEqual(len(result['entries']),1);self.assertNotIn('PRIVATE-SECRET',str(result))
   state=s.appendices.state();data={'outline_id':o['id'],'outline_revision':o['revision'],'signature':state['signature'],'reviewed':True}
   saved=s.appendices.attach(data);self.assertEqual(len(saved['chapters']),4);self.assertNotIn('PRIVATE-SECRET',str(saved));self.assertEqual(len(saved['chapters'][-1]['blocks']),3)
   with self.assertRaises(app.Conflict):s.appendices.attach(data)
   saved=s.appendices.attach({**data,'outline_revision':saved['revision']});self.assertEqual(len(saved['chapters']),4)
   for lang in ['de','en','fr']:
    plan=app.compose(saved,{**saved['profile'],'language':lang});texts=[b['text'] for c in plan['chapters'] for b in c['blocks']];self.assertEqual(texts,[translations[lang]['title']+'\nDefinition '+lang])
   s.appendices.save({**e,'internal':True})
   with self.assertRaises(app.Conflict):s.appendices.attach({**data,'outline_revision':saved['revision']})
   saved=s.appendices.attach({**data,'outline_revision':saved['revision'],'signature':s.appendices.state()['signature']});self.assertEqual(len(saved['chapters']),3)
 def test_missing_translation_and_validation(self):
  with tempfile.TemporaryDirectory() as folder:
   s=app.Store(Path(folder)/'db.sqlite3')
   with self.assertRaises(app.Invalid):s.appendices.save({'kind':'faq','translations':{'de':{'title':'Frage','approved':True}}})
   s.appendices.save({'kind':'faq','internal':False,'translations':{'de':{'title':'Frage','text':'Antwort','approved':True}}})
   self.assertEqual(len(s.appendices.preview({'language':'en'})['missing']),1)
