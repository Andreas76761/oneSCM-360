"""Local evidence retrieval across registers; reader drafts never consume internal records."""
import copy
import json
import re
from datetime import date
from collections import Counter
import publication
from knowledge_review import digest
from internal_chat import words


def record(kind, rid, title, text, revision=1, internal=False, approved=False, **extra):
    row={'ref':kind+':'+rid,'kind':kind,'id':rid,'title':title,'text':text,'revision':revision,'internal':internal,'approved':approved,**extra}
    row['fingerprint']=digest(row)
    return row


class RAG:
    def __init__(self,store):self.store=store

    def profile(self,data):
        from app import profile,validate_profile
        return validate_profile({**profile(),'as_of':date.today().isoformat(),**data.get('profile',{})})

    def corpus(self,p):
        from app import compose,new_outline,chapter
        rows=[]
        with self.store.connect() as db:
            contexts={sid:json.loads(raw) for sid,raw in db.execute('SELECT id,payload FROM source_context')}
            for cid,sid,ordinal,text,location,labels,revision,name in db.execute('SELECT c.id,c.source_id,c.ordinal,c.text,c.location,c.labels,c.revision,s.name FROM chunks c JOIN sources s ON s.id=c.source_id'):
                labels=json.loads(labels);context=contexts.get(sid,{})
                roles=labels.get('roles',[])
                if roles and p['role'] not in roles:continue
                if any(context.get(k,'*') not in ['', '*',p[k]] for k in ['role','language','market','environment']):continue
                if context.get('division','*') not in ['', '*',p['division']] and p['division']!='Beide':continue
                if context.get('from') and p['as_of']<context['from'] or context.get('until') and p['as_of']>context['until']:continue
                rows.append(record('source',cid,name+' · '+location,text,revision,source_id=sid,profile_known=bool(context.get('language') not in [None,'','*']),labels=labels,context=context))
        for outline in self.store.all():
            index_outline=copy.deepcopy(outline);index_outline['metadata']['document_type']='Sonstiges'
            plan=compose(index_outline,p)
            originals={b['id']:b for c in outline['chapters'] for b in c['blocks']}
            for c in plan['chapters']:
                if not c['visible']:continue
                for b in c['blocks']:
                    # Composer excludes internal blocks from all reader profiles.
                    rows.append(record('chapter',outline['id']+'/'+c['id']+'/'+b['id'],outline['title']+' / '+c['title'],b['text'],outline['revision'],internal=originals[b['id']].get('internal',False),approved=b['status']=='Freigegeben' and not originals[b['id']].get('internal',False),outline_id=outline['id'],chapter_id=c['id'],profile_known=True))
                original_chapter=next(ch for ch in outline['chapters'] if ch['id']==c['id'])
                notes='\n'.join([original_chapter.get('goal',''),*[b.get('note','') for b in original_chapter['blocks']],json.dumps(original_chapter.get('remarks',[]),ensure_ascii=False)])
                if notes.strip():rows.append(record('notes',outline['id']+'/'+c['id'],outline['title']+' / '+c['title']+' · Redaktion',notes,outline['revision'],internal=True))
                rows.append(record('outline',outline['id']+'/'+c['id'],outline['title']+' / '+c['title'],c['title'],outline['revision'],internal=True,outline_id=outline['id'],chapter_id=c['id']))
        for entry in self.store.library.listing():
            if entry.get('archived'):continue
            b=entry['block'];dummy=new_outline(entry['title']);dummy['chapters']=[chapter(entry['title'])];dummy['chapters'][0]['blocks']=[b];dummy['metadata']['document_type']='Sonstiges'
            plan=compose(dummy,p)
            blocks=plan['chapters'][0]['blocks']
            if blocks:rows.append(record('library',entry['id'],entry['title'],blocks[0]['text'],entry['revision'],internal=b.get('internal',False),approved=b['status']=='Freigegeben' and not b.get('internal',False),profile_known=True))
        for e in self.store.internal.listing():
            if e['status']=='Archiviert' or e['language']!=p['language'] or e['roles'] and p['role'] not in e['roles']:continue
            if e['markets'] and '*' not in e['markets'] and p['market'] not in e['markets']:continue
            if e.get('divisions') and p['division']!='Beide' and p['division'] not in e['divisions']:continue
            if not publication.effective(e.get('validity',[]),p)['matches']:continue
            rows.append(record('internal',e['id'],e['title'],'\n'.join([e['body'],e['question'],e['answer'],e['note']]),e['revision'],internal=True))
            if self.store.chat.eligible(e,p):
                rows.append(record('faq',e['id'],e['question'] or e['title'],e['answer'],e['revision'],internal=True,approved=True,source=e['source']))
        domain_names={d['id']:d['name'] for d in self.store.get_catalog()}
        for media in self.store.media.listing():
            if media.get('archived'):continue
            mp=media['profile']
            if any(mp.get(k,'*') not in ['*',p[k]] for k in ['role','language','market','scope','release']):continue
            if mp.get('division','*') not in ['*',p['division']] and p['division']!='Beide':continue
            classification=media.get('classification',{})
            if classification.get('roles') and p['role'] not in classification['roles']:continue
            text=' '.join([media['caption'],classification.get('topic',''),*classification.get('keywords',[]),*classification.get('labels',[]),*[domain_names.get(d,d) for d in classification.get('domain_ids',[])],*[u['chapter'] for u in media.get('usage',[])]])
            approved=media['status']=='Freigegeben' and media['pii_reviewed']
            rows.append(record('screen',media['id'],media['title'],text,media['revision'],approved=approved,caption=media['caption'],media_profile=media['profile'],profile_known=True,priority=media.get('priority','Normal')))
        screen_ids={r['id'] for r in rows if r['kind']=='screen'}
        for aid in screen_ids:
            ocr=self.store.ocr_records.get(aid)
            if ocr and not ocr['stale']:
                rows.append(record('ocr',aid,'OCR · '+next(r['title'] for r in rows if r['kind']=='screen' and r['id']==aid),ocr['text'],ocr['asset_revision'],internal=True,approved=False,lines=ocr['lines'],updated=ocr['updated']))
        for job in self.store.orchestrator.listing():
            if job['status'] in ['completed','cancelled']:continue
            rows.append(record('task',job['id'],job['title'],'Agentenauftrag '+job['status']+' · '+', '.join(step['agent'] for step in job['steps']),internal=True,status=job['status']))
        for job in self.store.ai_exchange.listing():
            if job['accepted']:continue
            if job['language']!=p['language'] or job['role']!=p['role']:continue
            rows.append(record('exchange',job['id'],job['task']+' · '+job['provider'],job['prompt'],internal=True,status='Quellen geändert' if job['stale'] else 'Antwort ausstehend'))
        for job in self.store.sources.imports.listing():
            rows.append(record('import',job['id'],job['name'],f"Import offen: {job['processed']}/{job['total']}",job['revision'],internal=True))
        for session in self.store.chat.listing():
            if any(session['profile'].get(k)!=p[k] for k in ['role','language','market','division','environment']):continue
            chat=self.store.chat.get(session['id'])
            rows.append(record('chat',chat['id'],chat['title'],'\n'.join(t['question'] for t in chat['turns']),chat['revision'],internal=True))
        for package in self.store.releases.listing()['packages']:
            rows.append(record('release',package['id'],'Release '+package['version'],package['status']+' · '+package['date'],package['revision'],internal=True))
        for review in self.store.review.listing():
            rows.append(record('review',review['id'],'Quellenprüfung '+review.get('kind',''),json.dumps(review,ensure_ascii=False),review.get('revision',1),internal=True))
        for job in self.store.agent_hub.listing():
            if job['status']!='cancelled':rows.append(record('task',job['id'],job['title'],'Orchestrator '+job['status']+' '+', '.join(s['agent'] for s in job['steps']),job['revision'],internal=True,status=job['status']))
        for pattern in self.store.source_design.listing():
            rows.append(record('design',pattern['id'],pattern['name'],json.dumps(pattern['theme'],ensure_ascii=False),pattern['revision'],internal=True))
        for layout in self.store.layouts.listing():
            rows.append(record('design',layout['id'],layout['name'],'Designvorlage '+layout['format']+' · '+layout['version'],layout['revision'],internal=True))
        for item in self.store.get_catalog():rows.append(record('domain',item['id'],item['name'],item['name'],internal=True))
        return rows

    def selected_corpus(self,data):
        from app import Invalid
        p=self.profile(data)
        internal=data.get('include_internal') is True
        if internal and data.get('working_role') not in ['HQ','intern']:
            raise Invalid('Interne Recherche benötigt die Redaktionsrolle HQ oder intern (lokaler Einzelarbeitsplatz).')
        rows=[r for r in self.corpus(p) if internal or not r['internal']]
        return p,rows

    def search(self,data):
        from app import clean_text,Invalid
        p,rows=self.selected_corpus(data)
        query=clean_text(data.get('query',''),'Suchtext',2000).strip()
        kind=data.get('kind','')
        if not isinstance(kind,str):raise Invalid('Ungültiger Registerfilter.')
        terms=words(query);ranked=[]
        for row in rows:
            if kind and (row['kind'] not in ['task','exchange','import'] if kind=='work' else row['kind']!=kind):continue
            title=words(row['title']);body=words(row['text']+' '+json.dumps(row.get('labels',{}),ensure_ascii=False))
            score=sum(4 if term in title else 1 for term in terms if any(word.startswith(term) for word in title|body))
            if terms and not score:continue
            ranked.append({**row,'score':score})
        ranked.sort(key=lambda r:(-r['score'],not r['approved'],r['title']))
        return {'profile':p,'total':len(ranked),'counts':dict(Counter(r['kind'] for r in rows)),'results':[{**r,'text':r['text'][:1200],'truncated':len(r['text'])>1200} for r in ranked[:100]],'method':'Lokale Belegsuche ohne externes Modell; keine semantische Vollständigkeitsgarantie.'}

    def evidence(self,data):
        from app import Invalid,Conflict
        _,rows=self.selected_corpus(data);byref={r['ref']:r for r in rows};refs=data.get('refs',[])
        if not isinstance(refs,list) or not 1<=len(refs)<=20:raise Invalid('1–20 Belege auswählen.')
        found=[]
        for ref in refs:
            if not isinstance(ref,dict):raise Invalid('Ungültiger Beleg.')
            row=byref.get(ref.get('ref'))
            if not row or row['fingerprint']!=ref.get('fingerprint'):raise Conflict('Beleg oder Profil geändert. Suche erneuern.')
            if row['ref'] in {r['ref'] for r in found}:raise Invalid('Beleg doppelt ausgewählt.')
            found.append(row)
        return found

    def answer(self,data):
        # No synthesis: return complete approved evidence to preserve conditions/negations.
        result=self.search(data)
        eligible=[r for r in result['results'] if r['approved'] and r['kind'] in ['faq','library','chapter']][:5]
        if not words(data.get('query','')) or not eligible:return {'answer':'Keine ausreichend passenden freigegebenen Belege gefunden.','citations':[]}
        full=self.evidence({**data,'refs':[{'ref':r['ref'],'fingerprint':r['fingerprint']} for r in eligible]})
        return {'answer':'Belegte Textstellen – Voraussetzungen und mögliche Unterschiede gemeinsam prüfen.','citations':full}

    def chapter(self,data):
        from app import Invalid,Conflict,clean_text,chapter,block,uid
        if data.get('reviewed') is not True:raise Invalid('Belege, Zielprofil und Personenangaben zuerst prüfen.')
        p=self.profile(data);rows=self.evidence(data)
        if any(r['internal'] or r['kind'] not in ['source','library','chapter','screen'] for r in rows):raise Invalid('Interne Informationen und Aufträge dürfen nicht in Leser-Kapitel übernommen werden.')
        outline=self.store.get(data.get('outline_id'))
        if outline['revision']!=data.get('outline_revision'):raise Conflict('Gliederung geändert. Neu laden.')
        title=clean_text(data.get('title'),'Kapiteltitel',300).strip()
        if not title:raise Invalid('Kapiteltitel fehlt.')
        c=chapter(title);c['config']={'titles':{p['language']:title},'conditions':{'role':[p['role']],'language':[p['language']]},'status':'Entwurf'}
        c['media']=[]
        for row in rows:
            if row['kind']=='screen':
                if not row['approved']:raise Invalid('Screens vor der Übernahme visuell prüfen und freigeben.')
                c['media'].append({'id':uid(),'title':row['title'],'kind':'Bild','frames':[{'variants':[{'asset_id':row['id'],'revision':row['revision']}],'caption':row['caption']}],'conditions':{'role':[p['role']],'language':[p['language']]}})
            else:
                if len(row['text'])>100000:raise Invalid('Beleg ist zu groß für einen Kapitelbaustein; vorher aufteilen.')
                from jira_import import KEY
                b=block();b.update(text=publication.public_text(row['text'],KEY.findall(row['text'])),text_format='markdown',source=row['ref']+' @'+str(row['revision']),role=p['role'],language=p['language'],market=p['market'] or '*',division=p['division'] if p['division']!='Beide' else '*',status='Entwurf')
                c['blocks'].append(b)
        parent=data.get('parent_id')
        if parent:
            index=next((i for i,ch in enumerate(outline['chapters']) if ch['id']==parent),None)
            if index is None:raise Invalid('Übergeordnetes Kapitel fehlt.')
            level=outline['chapters'][index]['level'];c['level']=level+1
            if c['level']>6:raise Invalid('Maximal sechs Kapitelebenen.')
            index+=1
            while index<len(outline['chapters']) and outline['chapters'][index]['level']>level:index+=1
            outline['chapters'].insert(index,c)
        else:outline['chapters'].append(c)
        return self.store.save(outline)


    def attach_screens(self,data):
        from app import Invalid,Conflict,uid
        if data.get('reviewed') is not True:raise Invalid('Screens und Zielprofil zuerst prüfen.')
        p=self.profile(data);rows=self.evidence(data)
        if any(r['kind']!='screen' or not r['approved'] or r['internal'] for r in rows):raise Invalid('Nur freigegebene, PII-geprüfte Screens auswählen.')
        outline=self.store.get(data.get('outline_id'))
        if outline['revision']!=data.get('outline_revision'):raise Conflict('Gliederung geändert. Neu laden.')
        c=next((c for c in outline['chapters'] if c['id']==data.get('parent_id')),None)
        if not c:raise Invalid('Ein bestehendes Zielkapitel auswählen.')
        for row in rows:
            existing={ref['asset_id'] for item in c.get('media',[]) for f in item['frames'] for ref in f['variants']}
            if row['id'] in existing:continue
            c.setdefault('media',[]).append({'id':uid(),'title':row['title'],'kind':'Bild','frames':[{'variants':[{'asset_id':row['id'],'revision':row['revision']}],'caption':row['caption']}],'conditions':{'role':[p['role']],'language':[p['language']]}})
        return self.store.save(outline)
