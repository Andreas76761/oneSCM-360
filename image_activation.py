"""Activation applies to a pinned image/sequence use in a specific chapter."""
def listing(store):
 return [{'outline_id':o['id'],'outline_revision':o['revision'],'outline':o['title'],'chapter_id':c['id'],'chapter':c['title'],'assignment_id':m['id'],'title':m['title'] or m['kind'],'activation':m.get('activation',{'enabled':True,'releases':[],'domains':[]})} for o in store.all() for c in o['chapters'] for m in c.get('media',[])]

def save(store,data):
 from app import Conflict,Invalid
 o=store.get(data.get('outline_id'))
 if o['revision']!=data.get('outline_revision'):raise Conflict('Gliederung geändert. Neu laden.')
 c=next((c for c in o['chapters'] if c['id']==data.get('chapter_id')),None)
 m=next((m for m in (c or {}).get('media',[]) if m['id']==data.get('assignment_id')),None)
 if not m:raise Invalid('Bildzuordnung fehlt.')
 activation=data.get('activation')
 if not isinstance(activation,dict):raise Invalid('Bildregel fehlt.')
 domains=activation.get('domains',[])
 if not isinstance(domains,list) or any(d not in {v['id'] for v in store.get_catalog()} for d in domains):raise Invalid('Unbekannte Domäne.')
 m['activation']=activation
 return store.save(o)
