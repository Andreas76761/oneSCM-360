"""Conservative, local PII candidates. Matches block reader rendering."""
import json
import re
PATTERNS=[
 ('E-Mail',r'\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b'),
 ('IBAN',r'\b[A-Z]{2}\d{2}(?:[ ]?[A-Z0-9]){11,30}\b'),
 ('FIN/VIN',r'\b[A-HJ-NPR-Z0-9]{17}\b'),
 ('Telefon',r'(?<!\w)\+\d[\d ()/-]{7,}\d'),
 ('Personenfeld',r'(?im)\b(?:name|vorname|nachname|erfasser|bearbeiter|reporter|assignee|creator|kommentarautor|user\s?id|login|kennzeichen|license plate)\s*[:=]\s*(?!\[)[^\n]{2,100}')]

def findings(text):
 result=[]
 for category,pattern in PATTERNS:
  for match in re.finditer(pattern,text):
   result.append({'category':category,'start':match.start(),'end':match.end(),'line':text.count('\n',0,match.start())+1,'marker':'[PII-Kandidat: '+category+']'})
 return sorted(result,key=lambda f:f['start'])

def guard(plan):
 from app import Invalid
 values=[('Dokumenttitel',plan.get('title','')),('Ausgabeprofil',json.dumps(plan.get('profile',{}),ensure_ascii=False))]
 for c in plan.get('chapters',[]):
  if not c.get('visible',True):continue
  values.append(('Kapitel',c['title']))
  values.extend(('Textbaustein',b['text']) for b in c['blocks'])
  for figure in c.get('figures',[]):
   values.append(('Bildtitel',figure.get('title','')))
   values.extend(('Bildunterschrift',f.get('caption','')) for f in figure['frames'])
 for label,text in values:
  found=findings(text)
  if found:raise Invalid('PII-Audit sperrt Ausgabe: '+label+' enthält '+found[0]['category']+'. Inhalt anonymisieren und erneut prüfen.')

def uncovered_regions(ocr,asset):
 return [r for r in (ocr or {}).get('candidate_regions',[]) if not any(m['x']<=r['x'] and m['y']<=r['y'] and m['x']+m['w']>=r['x']+r['w'] and m['y']+m['h']>=r['y']+r['h'] for m in asset.get('redactions',[]))]

class Audit:
 def __init__(self,store):
  self.store=store
  with store.connect() as db:db.execute('CREATE TABLE IF NOT EXISTS pii_audits(ref TEXT PRIMARY KEY,payload TEXT)')
 def scan(self):
  from app import now
  from knowledge_review import digest
  records=self.store.content_flags.records()
  for e in self.store.appendices.listing():
   records.append({'ref':'appendix:'+e['id'],'title':'Anhang '+e['kind'],'text':'\n'.join([e['note'],*[t['title']+'\n'+t['text'] for t in e['translations'].values()]]),'fingerprint':digest(e)})
  for e in self.store.library.listing():records.append({'ref':'library:'+e['id'],'title':e['title'],'text':e['block']['text']+'\n'+e['block'].get('note',''),'fingerprint':digest(e)})
  for o in self.store.all():
   for c in o['chapters']:
    records.append({'ref':'chapter:'+c['id'],'title':c['title'],'text':'\n'.join([c['title'],c.get('goal',''),json.dumps(c.get('remarks',[]),ensure_ascii=False),*[b['text']+'\n'+b.get('note','') for b in c['blocks']]]),'fingerprint':digest(c)})
  result=[]
  for r in records:
   hits=findings(r['title']+'\n'+r['text'])
   item={'ref':r['ref'],'title':r['title'],'fingerprint':r['fingerprint'],'findings':hits,'updated':now(),'status':'Offene Funde' if hits else 'Keine Regel-Funde','note':'Lokale Musterprüfung; freie Namen und Bildinhalt können unerkannt bleiben.'}
   if r['ref'].startswith('screen:'):
    aid=r['ref'].split(':',1)[1];ocr=self.store.ocr_records.get(aid)
    asset=next(a for a in self.store.media.listing() if a['id']==aid)
    item['regions']=uncovered_regions(ocr,asset)
    item['note']='Bild visuell prüfen; OCR im Medieneditor ausführen. Bereinigte OCR liefert keine vollständige PII-Garantie.'
    if ocr and not ocr['stale']:item['findings']+=findings(ocr['text']);item['status']='Offene Funde' if item['findings'] else 'OCR ohne Regel-Funde – visuell prüfen'
    else:item['status']='OCR fehlt / veraltet – Bildprüfung offen'
    if item.get('regions'):item['status']='PII-Bildbereiche unmaskiert'
   result.append(item)
  with self.store.connect() as db:
   db.execute('DELETE FROM pii_audits')
   db.executemany('INSERT INTO pii_audits VALUES(?,?)',[(r['ref'],json.dumps(r,ensure_ascii=False)) for r in result])
  return result

def guard_template(raw):
 if not raw:return
 import io,zipfile
 from lxml import etree
 from app import Invalid
 with zipfile.ZipFile(io.BytesIO(raw)) as archive:
  for name in archive.namelist():
   if not name.endswith('.xml'):continue
   root=etree.fromstring(archive.read(name),etree.XMLParser(resolve_entities=False,no_network=True))
   text='\n'.join(root.itertext())
   if findings(text):raise Invalid('PII-Audit sperrt Ausgabe: Office-Vorlage enthält PII-Kandidaten. Vorlage bereinigen.')
