"""Reviewed Cartesian-product draft exports with a manifest per artifact."""
import copy
import hashlib
import io
import itertools
import json
import zipfile
import editorial
import layouts
import renderers


def plans(store, data):
    from app import Invalid, Conflict, LANGUAGES, ROLES, compose, validate_profile
    outline=store.get(data.get('id'))
    if outline['revision']!=data.get('revision'):
        raise Conflict('Gliederung seit der Auswahl geändert. Neu laden und Vorschau erneuern.')
    selections=[]
    for key,allowed in [('languages',LANGUAGES),('roles',ROLES),('documents',['Handbuch','Releaseletter','Quickreference']),('formats',['docx','pptx','pdf','html'])]:
        values=data.get(key)
        if not isinstance(values,list) or not values or any(not isinstance(v,str) or v not in allowed for v in values) or len(set(values))!=len(values):
            raise Invalid('Ungültige Varianten-Auswahl: '+key)
        selections.append(values)
    if len(list(itertools.product(*selections)))>60:
        raise Invalid('Höchstens 60 Dateien je Stapel auswählen.')
    result=[]
    for language,role,document in itertools.product(*selections[:3]):
        variant=copy.deepcopy(outline)
        variant['profile']=validate_profile({**outline['profile'],'language':language,'role':role})
        variant['metadata']['document_type']=document
        plan=compose(variant,variant['profile']);plan['draft']=True
        issues=editorial.release_errors(plan)
        # The composer allows fallback titles; explicitly flag them for translated batches.
        if language!=outline['profile']['language']:
            for chapter in variant['chapters']:
                if not chapter.get('config',{}).get('titles',{}).get(language):
                    issues.append('Kapitelübersetzung fehlt: '+chapter['title']+' ('+language+')')
        for fmt in selections[3]:
            plan_copy=copy.deepcopy(plan)
            plan_copy['manifest']['theme']=layouts.theme(variant.get('layout',{}).get('theme'))
            if fmt in ['docx','pptx'] and variant.get('layout',{}).get(fmt):
                info,_=store.layouts.snapshot(variant['layout'][fmt],fmt)
                plan_copy['manifest']['template']=info
            result.append({'plan':plan_copy,'format':fmt,'issues':list(dict.fromkeys(issues+plan.get('warnings',[]))),
                           'filename':f'{len(result)+1:02d}-{document}-{language}-{role}.{fmt}'})
    return result


def fingerprint(rows):
    return hashlib.sha256(json.dumps(rows,sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def preview(store,data):
    rows=plans(store,data)
    return {'fingerprint':fingerprint(rows),'count':len(rows),'rows':[{'filename':r['filename'],'profile':r['plan']['profile'],'issues':r['issues'],'chapters':sum(c['visible'] for c in r['plan']['chapters'])} for r in rows]}


def export(store,data):
    from app import Invalid, Conflict, office_export
    rows=plans(store,data)
    if data.get('fingerprint')!=fingerprint(rows):
        raise Conflict('Vorschau fehlt oder ist veraltet. Varianten erneut prüfen.')
    if data.get('reviewed') is not True:
        raise Invalid('Varianten und Prüfpunkte vor der Stapelerzeugung bestätigen.')
    output=io.BytesIO();artifacts=[];total=0
    loader=lambda aid,rev:store.media.image(aid,rev,'intern')
    # Render everything before recording success. A failed renderer leaves no partial export history.
    for row in rows:
        plan,fmt=row['plan'],row['format'];template=None
        if fmt in ['docx','pptx'] and plan.get('layout',{}).get(fmt):
            _,template=store.layouts.snapshot(plan['layout'][fmt],fmt)
        raw=renderers.html_export(plan,loader) if fmt=='html' else renderers.pdf_export(plan,loader) if fmt=='pdf' else office_export(plan,fmt,loader,template)
        total+=len(raw)
        if total>128*1024*1024:raise Invalid('Stapel überschreitet 128 MB. Weniger Varianten wählen.')
        artifacts.append((row,raw))
    from app import uid,now
    manifest={'kind':'Prüfausgaben','outline_id':data['id'],'revision':data['revision'],'files':[]}
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        for row,raw in artifacts:
            eid=uid();db.execute('INSERT INTO exports VALUES(?,?,?,?,?)',(eid,now(),row['format'],json.dumps(row['plan'],ensure_ascii=False),raw))
            manifest['files'].append({'file':row['filename'],'export_id':eid,'profile':row['plan']['profile'],'issues':row['issues'],'sha256':hashlib.sha256(raw).hexdigest()})
        with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as z:
            for row,raw in artifacts:z.writestr(row['filename'],raw)
            z.writestr('Pruefbericht.json',json.dumps(manifest,ensure_ascii=False,indent=2))
    return output.getvalue()
