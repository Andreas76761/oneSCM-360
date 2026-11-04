"""Explicit source selection, readable compilations and extractive short views."""
import hashlib
import json
import re


def collect(store,data):
    from app import Invalid
    ids=data.get('ids')
    if not isinstance(ids,list) or not 1<=len(ids)<=1500 or any(not isinstance(i,str) for i in ids) or len(set(ids))!=len(ids):
        raise Invalid('1–1500 unterschiedliche Dateien auswählen.')
    sources={s['id']:s for s in store.sources.listing()}
    parts=[];refs=[];size=0
    for sid in ids:
        if sid not in sources:raise Invalid('Eine markierte Datei wurde gelöscht. Auswahl aktualisieren.')
        source=sources[sid];chunks=store.sources.chunks(sid)
        refs.append({'id':sid,'name':source['name'],'chunks':[(c['id'],hashlib.sha256(c['text'].encode()).hexdigest()) for c in chunks]})
        for c in chunks:
            size+=len(c['text'])
            if size>2_000_000:raise Invalid('Auswahl überschreitet 2 Millionen Textzeichen. Weniger Dateien auswählen.')
            parts.append({'text':c['text'],'location':source['name']+' · '+c['location'],'details':{**c.get('details',{}),'source_ref':{'source_id':sid,'chunk_id':c['id'],'revision':c['revision']}}})
    fingerprint=hashlib.sha256(json.dumps(refs,sort_keys=True).encode()).hexdigest()
    text='\n\n'.join('## '+p['location']+'\n\n'+p['text'] for p in parts)
    excerpts=[]
    for p in parts:
        lines=[line.strip() for line in p['text'].splitlines() if line.strip() and not line.lstrip().startswith('#')]
        excerpt=' '.join(lines)[:500]
        if len(' '.join(lines))>500:excerpt+=' […]'
        excerpts.append('## '+p['location']+'\n\n'+excerpt)
    return {'fingerprint':fingerprint,'text':text,'summary':'# Textauszüge – keine KI-Zusammenfassung\n\nJe Chunk höchstens 500 Zeichen. Voraussetzungen und Ausnahmen können fehlen; Originaltexte prüfen.\n\n'+'\n\n'.join(excerpts),'files':len(ids),'chunks':len(parts),'parts':parts}


def save(store,data):
    from app import Invalid,Conflict,clean_text
    current=collect(store,data)
    if current['fingerprint']!=data.get('fingerprint'):raise Conflict('Quellen geändert. Texte erneut laden.')
    text=clean_text(data.get('text'),'Zusammenstellung',3_000_000).strip()
    if not text:raise Invalid('Zusammenstellung ist leer.')
    name=clean_text(data.get('name'),'Dateiname',240).strip()
    if not name:raise Invalid('Dateiname fehlt.')
    if not name.lower().endswith('.md'):name+='.md'
    name,metadata=store.sources.metadata(name,{'kind':'Zusammenstellung','origin':f"Aus {current['files']} Quellen zusammengestellt; redaktionell prüfen."})
    if text==current['text'].strip():
        parts=current['parts']
    else:
        from sources import text_chunks
        parts=list(text_chunks(text,'Redaktionelle Zusammenstellung'))
        for p in parts:p['details']={'source_ids':data['ids'],'collection_fingerprint':current['fingerprint']}
    return store.sources.store_parsed(name,text.encode(),metadata,parts,['Abgeleitete Quelle; Originaldateien bleiben erhalten. Labels und Kapitelzuordnungen werden nicht automatisch übernommen.'])
