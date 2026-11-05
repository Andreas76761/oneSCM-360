"""Three-language editorial appendix catalogue and explicit outline snapshots."""
import json
from hashlib import sha256
LANGUAGES=['de','en','fr']
TITLES={'glossary':{'de':'Glossar','en':'Glossary','fr':'Glossaire'},'abbreviations':{'de':'Abkürzungsverzeichnis','en':'Abbreviations','fr':'Abréviations'},'synonyms':{'de':'Synonyme','en':'Synonyms','fr':'Synonymes'},'faq':{'de':'FAQs','en':'FAQs','fr':'FAQ'}}
class Appendices:
 def __init__(self,store):
  self.store=store
  with store.connect() as db:db.execute('CREATE TABLE IF NOT EXISTS appendix_entries(id TEXT PRIMARY KEY,revision INTEGER,payload TEXT)')
 def listing(self):
  with self.store.connect() as db:return [json.loads(r[0]) for r in db.execute('SELECT payload FROM appendix_entries ORDER BY rowid')]
 def save(self,data):
  from app import uid,clean_text,choice,boolean,Conflict,Invalid,now
  revision=data.get('revision',0)
  if type(revision) is not int or revision<0:raise Invalid('Ungültige Revision.')
  row={'id':clean_text(data.get('id') or uid(),'ID',100),'revision':revision+1,'kind':choice(data.get('kind'),list(TITLES),'Anhang'),'internal':boolean(data.get('internal',True),'Nur intern'),'note':clean_text(data.get('note',''),'Interner Vermerk',5000),'translations':{},'updated':now()}
  for lang in LANGUAGES:
   t=data.get('translations',{}).get(lang,{})
   row['translations'][lang]={'title':clean_text(t.get('title',''),'Begriff / Frage',300).strip(),'text':clean_text(t.get('text',''),'Erklärung / Antwort',10000).strip(),'approved':boolean(t.get('approved',False),'Geprüft')}
   if row['translations'][lang]['approved'] and not all(row['translations'][lang][k] for k in ['title','text']):raise Invalid('Geprüfte Sprachfassung benötigt Begriff und Erklärung.')
  if not any(t['title'] for t in row['translations'].values()):raise Invalid('Mindestens einen Begriff / eine Frage eingeben.')
  with self.store.connect() as db:
   db.execute('BEGIN IMMEDIATE');old=db.execute('SELECT revision FROM appendix_entries WHERE id=?',(row['id'],)).fetchone()
   if (old[0] if old else 0)!=revision:raise Conflict('Anhangseintrag geändert. Neu laden.')
   db.execute('INSERT INTO appendix_entries VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET revision=excluded.revision,payload=excluded.payload',(row['id'],row['revision'],json.dumps(row,ensure_ascii=False)))
  return row
 def preview(self,data):
  from app import choice
  lang=choice(data.get('language','de'),LANGUAGES,'Sprache');result=[];missing=[]
  for e in self.listing():
   if e['internal']:continue
   t=e['translations'][lang]
   if not t['approved']:missing.append({'id':e['id'],'kind':e['kind'],'reason':'Sprachfassung fehlt oder ungeprüft'});continue
   result.append({'id':e['id'],'revision':e['revision'],'kind':e['kind'],'heading':TITLES[e['kind']][lang],'title':t['title'],'text':t['text']})
  return {'language':lang,'entries':result,'missing':missing}
 def attach(self,data):
  with self.store.connect() as db:
   db.execute("BEGIN IMMEDIATE")
   return self._attach(data,db)
 def _attach(self,data,db):
  from app import Invalid,Conflict,chapter,block
  if data.get('reviewed') is not True:raise Invalid('Vorschau zuerst prüfen.')
  o=self.store.get(data.get('outline_id'))
  if o['revision']!=data.get('outline_revision'):raise Conflict('Gliederung geändert. Neu laden.')
  rows=self.listing();signature=sha256(json.dumps(rows,sort_keys=True).encode()).hexdigest()
  if data.get('signature')!=signature:raise Conflict('Anhangskatalog geändert. Vorschau neu laden.')
  for kind,titles in TITLES.items():
   cid='annex-'+sha256((o['id']+kind).encode()).hexdigest()[:24]
   c=chapter(titles['de']);c['id']=cid;c['config']={'titles':titles};c['blocks']=[]
   for e in rows:
    if e['kind']!=kind or e['internal']:continue
    for lang,t in e['translations'].items():
     if not t['approved']:continue
     b=block();b.update(text=t['title']+'\n'+t['text'],language=lang,status='Freigegeben',content_kind='FAQ' if kind=='faq' else 'Glossarbegriff',source='Anhang '+e['id']+' R'+str(e['revision']))
     c['blocks'].append(b)
   # Only managed appendix chapters are replaced; existing user chapters remain intact.
   o['chapters']=[old for old in o['chapters'] if old['id']!=cid]
   if c['blocks']:o['chapters'].append(c)
  return self.store.save(o,connection=db)
 def state(self):
  rows=self.listing();return {'entries':rows,'signature':sha256(json.dumps(rows,sort_keys=True).encode()).hexdigest(),'outlines':[{'id':o['id'],'title':o['title'],'revision':o['revision']} for o in self.store.all()]}
