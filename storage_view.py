"""Read-only inventory: logical record sizes, never load binary objects."""
import json
from pathlib import Path
import dashboard

def inventory(store,data):
 from app import Invalid
 page=data.get('page',0);selected=data.get('table','')
 if type(page) is not int or page<0:raise Invalid('Ungültige Seite.')
 items=[];offset=page*50
 with store.connect() as db:
  db.execute('BEGIN')
  tables=[r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
  if selected and selected not in tables:raise Invalid('Unbekannter Bereich.')
  quote=lambda v:'"'+v.replace('"','""')+'"'
  counts={t:db.execute('SELECT COUNT(*) FROM '+quote(t)).fetchone()[0] for t in tables}
  flags={r[0]:json.loads(r[1]) for r in db.execute("SELECT ref,payload FROM content_flags")}
  for table in ([selected] if selected else tables):
   if offset>=counts[table]:offset-=counts[table];continue
   cols=[r[1] for r in db.execute('PRAGMA table_info('+quote(table)+')')]
   keys=[c for c in cols if c in ['id','asset_id','ref','name','created','uploaded','revision','release','payload','plan','labels','location']]
   size='+'.join('COALESCE(length(CAST('+quote(c)+' AS BLOB)),0)' for c in cols)
   sql='SELECT rowid,'+''.join(quote(c)+',' for c in keys)+'('+size+') FROM '+quote(table)+' ORDER BY rowid DESC LIMIT ? OFFSET ?'
   for raw in db.execute(sql,(50-len(items),offset)):
    fields=dict(zip(keys,raw[1:-1]));p={}
    for k in ['payload','plan']:
     try:
      value=json.loads(fields.get(k) or '{}')
      if isinstance(value,dict):p.update(value)
     except (ValueError,TypeError):pass
    profile=p.get('profile',{});profile=profile if isinstance(profile,dict) else {}
    b=p.get('block',{});b=b if isinstance(b,dict) else {}
    prefix={'sources':'source:','media':'screen:','internal_entries':'note:'}.get(table,'')
    flag=flags.get(prefix+str(fields.get('id','')),{}) if prefix else {}
    language=flag.get('language') or p.get('language') or profile.get('language') or b.get('language') or ', '.join(p.get('translations',{}))
    labels=[]
    try:labels=json.loads(fields.get('labels') or '{}').get('labels',[])
    except (ValueError,AttributeError):pass
    items.append({'table':table,'id':str(fields.get('id') or fields.get('asset_id') or fields.get('ref') or raw[0]),'title':str(fields.get('name') or p.get('title') or p.get('name') or fields.get('location') or table),'date':str(fields.get('uploaded') or fields.get('created') or p.get('updated') or p.get('created') or p.get('date') or ''),'bytes':raw[-1],'language':str(language or ''),'version':str(flag.get('version') or p.get('version') or fields.get('release') or profile.get('release') or ''),'revision':fields.get('revision',p.get('revision','')),'labels':labels,'note':(str(p.get('note') or p.get('method') or p.get('status') or '')+(' · Sprach-/Versionsflag: '+flag.get('status','Prüfen')+'; Inhaltsdatum '+flag.get('date','offen')+' (gespeicherter Vermerk, Aktualität prüfen)' if flag else ''))[:5000]})
   offset=0
   if len(items)>=50:break
 return {'database_path':str(Path(store.path).resolve()),'tables':counts,'total':sum(counts[t] for t in ([selected] if selected else tables)),'page':page,'items':items,'storage':dashboard.snapshot(store)['storage']}
