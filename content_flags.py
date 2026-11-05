"""Editorial-only language/date/version annotations; never consumed by renderers."""
import json
import re
from datetime import date
from knowledge_review import digest

WORDS={
 'de':set('der die das und ist sind für mit nicht werden ein eine einer des den im auf'.split()),
 'en':set('the and is are for with not will a an of to in this that your'.split()),
 'fr':set('le la les des et est sont pour avec pas une un dans du cette sur'.split()),
 'it':set('il lo gli le e sono per con non una uno della nel questo anche'.split()),
 'sk':set('je sú pre nie sa na vo alebo pri tento táto ako používateľ zmluva'.split())}

def detect(text,title='',declared=''):
 words=re.findall(r'[^\W\d_]+',text.casefold());scores={k:sum(w in vocab for w in words) for k,vocab in WORDS.items()}
 ordered=sorted(scores,key=scores.get,reverse=True);best=ordered[0];score=scores[best]
 if len(re.findall('[가-힣]',text))>=5:language='ko';method='Koreanische Schrift erkannt'
 elif score>=4 and score>=scores[ordered[1]]*1.5:language=best;method='Lokale Wortheuristik – prüfen'
 else:language='';method='Text zu kurz, gemischt oder Sprache nicht eindeutig'
 dates=[]
 for match in re.finditer(r'(?<!\d)(20\d{2})[-/.](\d{2})[-/.](\d{2})(?!\d)',title+'\n'+text):
  try:dates.append(date(*map(int,match.groups())).isoformat())
  except ValueError:pass
 for match in re.finditer(r'(?<!\d)(\d{2})\.(\d{2})\.(20\d{2})(?!\d)',title+'\n'+text):
  try:dates.append(date(int(match[3]),int(match[2]),int(match[1])).isoformat())
  except ValueError:pass
 versions=list(dict.fromkeys(re.findall(r'(?i)(?<![A-Za-z0-9])(?:version|release|v)[\s:_-]*(\d+(?:\.\d+){0,3}(?:-[A-Za-z0-9]+)?)(?![A-Za-z0-9])',title+'\n'+text)))[:20]
 dates=list(dict.fromkeys(dates))[:20]
 return {'language':language,'date':dates[0] if len(dates)==1 else '', 'version':versions[0] if len(versions)==1 else '', 'date_candidates':dates,'version_candidates':versions,'method':method,'declared_language':declared,'language_conflict':bool(language and declared not in ['', '*',language]),'status':'Prüfen'}

class Flags:
 def __init__(self,store):
  self.store=store
  with store.connect() as db:db.execute('CREATE TABLE IF NOT EXISTS content_flags(ref TEXT PRIMARY KEY, revision INTEGER, payload TEXT)')
 def records(self):
  rows=[]
  with self.store.connect() as db:
   contexts={r[0]:json.loads(r[1]) for r in db.execute('SELECT id,payload FROM source_context')}
   for sid,name,uploaded,release in db.execute('SELECT id,name,uploaded,release FROM sources'):
    chunks=list(db.execute('SELECT id,revision,text FROM chunks WHERE source_id=? ORDER BY ordinal',(sid,)))
    context=contexts.get(sid,{})
    rows.append({'ref':'source:'+sid,'kind':'Quelle','title':name,'text':'\n'.join(c[2] for c in chunks),'declared':context.get('language',''),'uploaded':uploaded,'release':release,'fingerprint':digest([name,chunks,context,release])})
   for mid,rev,payload in db.execute('SELECT id,revision,payload FROM media'):
    m=json.loads(payload);rows.append({'ref':'screen:'+mid,'kind':'Screen','title':m['title'],'text':'\n'.join([m.get('caption',''),m.get('note','')]),'declared':m['profile'].get('language',''),'fingerprint':digest([rev,payload])})
   for nid,rev,payload in db.execute('SELECT id,revision,payload FROM internal_entries'):
    n=json.loads(payload);rows.append({'ref':'note:'+nid,'kind':'Notiz','title':n['title'],'text':'\n'.join(str(n.get(k,'')) for k in ['body','question','answer','note']),'declared':n.get('language',''),'fingerprint':digest([rev,payload])})
  return rows
 def listing(self):
  with self.store.connect() as db:saved={r[0]:json.loads(r[1]) for r in db.execute('SELECT ref,payload FROM content_flags')}
  return [{**{k:r[k] for k in ['ref','kind','title','fingerprint']},'flags':saved.get(r['ref']), 'stale':r['ref'] in saved and saved[r['ref']]['fingerprint']!=r['fingerprint']} for r in self.records()]
 def write(self,record,value,expected):
  from app import Conflict,now
  with self.store.connect() as db:
   db.execute('BEGIN IMMEDIATE')
   current=next((r for r in self.records() if r['ref']==record['ref']),None)
   if not current or current['fingerprint']!=record['fingerprint']:raise Conflict('Inhalt geändert. Neu laden.')
   old=db.execute('SELECT revision FROM content_flags WHERE ref=?',(record['ref'],)).fetchone()
   if (old[0] if old else 0)!=expected:raise Conflict('Vermerk geändert. Neu laden.')
   value.update(revision=expected+1,fingerprint=record['fingerprint'],updated=now(),internal=True)
   db.execute('INSERT INTO content_flags VALUES(?,?,?) ON CONFLICT(ref) DO UPDATE SET revision=excluded.revision,payload=excluded.payload',(record['ref'],value['revision'],json.dumps(value,ensure_ascii=False)))
  return value
 def process(self,data):
  from app import Invalid,Conflict,clean_text,LANGUAGES
  record=next((r for r in self.records() if r['ref']==data.get('ref')),None)
  if not record:raise Invalid('Inhalt nicht gefunden.')
  if record['fingerprint']!=data.get('fingerprint'):raise Conflict('Inhalt geändert. Neu laden.')
  if type(data.get('revision')) is not int:raise Invalid('Vermerkrevision fehlt.')
  if data.get('action')=='analyse':
   text=record['text'][:500000];basis='Text und Metadaten'
   if record['kind']=='Screen' and data.get('ocr') is True:
    text=self.store.media.ocr(record['ref'].split(':',1)[1])['text'][:500000]+'\n'+text;basis='Lokale OCR und Metadaten; Bild visuell prüfen'
   elif record['kind']=='Screen':basis='Nur Titel/Untertitel; Bildinhalt nicht gelesen'
   value=detect(text,record['title'],record.get('declared',''));value.update(basis=basis,uploaded=record.get('uploaded',''),declared_release=record.get('release',''))
  elif data.get('action')=='save':
   language=clean_text(data.get('language',''),'Sprache',10)
   if language and language not in LANGUAGES:raise Invalid('Unbekannte Sprache.')
   day=clean_text(data.get('date',''),'Datum',10)
   if day:
    try:date.fromisoformat(day)
    except ValueError:raise Invalid('Datum im Format JJJJ-MM-TT angeben.')
   value={'language':language,'date':day,'version':clean_text(data.get('version',''),'Version',100),'method':'Manuell geprüft','status':'Bestätigt' if data.get('reviewed') is True else 'Prüfen','basis':'Redaktionelle Eingabe'}
  else:raise Invalid('Ungültige Aktion.')
  return self.write(record,value,data['revision'])
