"""Internal, revision-bound OCR findings; no reader content provider."""
import json
from ai_exchange import scrub

class OCRRecords:
 def __init__(self,store):
  self.store=store
  with store.connect() as db:db.execute('CREATE TABLE IF NOT EXISTS ocr_records(asset_id TEXT PRIMARY KEY REFERENCES media(id) ON DELETE CASCADE, payload TEXT)')
 def get(self,aid):
  with self.store.connect() as db:
   row=db.execute('SELECT o.payload,m.revision FROM ocr_records o JOIN media m ON m.id=o.asset_id WHERE asset_id=?',(aid,)).fetchone()
  if not row:return None
  value=json.loads(row[0]);value['stale']=value['asset_revision']!=row[1];return value
 def save(self,aid,revision,words,pii_lines,redactions):
  from app import now,Conflict
  groups={}
  for w in words:groups.setdefault(tuple(w['line']),[]).append(w)
  lines=[]
  for key,group in groups.items():
   if key in pii_lines:continue
   if any(w['x']<r['x']+r['w'] and w['x']+w['w']>r['x'] and w['y']<r['y']+r['h'] and w['y']+w['h']>r['y'] for w in group for r in redactions):continue
   raw=' '.join(w['text'] for w in group);clean=scrub(raw)
   if clean!=raw:continue
   x=min(w['x'] for w in group);y=min(w['y'] for w in group)
   lines.append({'text':clean,'x':x,'y':y,'w':max(w['x']+w['w'] for w in group)-x,'h':max(w['y']+w['h'] for w in group)-y,'line':list(key)})
  result={'asset_id':aid,'asset_revision':revision,'updated':now(),'engine':'Tesseract TSV','text':'\n'.join(l['text'] for l in lines),'lines':lines,'internal':True,'status':'Ungeprüft','excluded_lines':len(groups)-len(lines)}
  with self.store.connect() as db:
   db.execute('BEGIN IMMEDIATE');current=db.execute('SELECT revision FROM media WHERE id=?',(aid,)).fetchone()
   if not current or current[0]!=revision:raise Conflict('Bild während OCR geändert. Erneut starten.')
   db.execute('INSERT INTO ocr_records VALUES(?,?) ON CONFLICT(asset_id) DO UPDATE SET payload=excluded.payload',(aid,json.dumps(result,ensure_ascii=False)))
  return result
