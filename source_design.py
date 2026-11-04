"""Named design patterns and standalone design previews for imported source text."""
import copy
import json
import secrets
import re
import time
import layouts
import renderers


class SourceDesign:
    def __init__(self,store):
        self.store=store;self.previews={}
        with store.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS design_patterns(id TEXT PRIMARY KEY,revision INTEGER,payload TEXT)')
            db.execute('CREATE TABLE IF NOT EXISTS design_pattern_history(id TEXT,revision INTEGER,payload TEXT,PRIMARY KEY(id,revision))')

    def listing(self):
        with self.store.connect() as db:return [json.loads(r[0]) for r in db.execute('SELECT payload FROM design_patterns ORDER BY rowid DESC')]

    def save(self,data):
        from app import clean_text,Invalid,Conflict,uid,now
        name=clean_text(data.get('name'),'Patternname',200).strip()
        if not name:raise Invalid('Patternname fehlt.')
        revision=data.get('revision',0)
        if type(revision) is not int or revision<0:raise Invalid('Ungültige Patternrevision.')
        pid=data.get('id') or uid();pid=clean_text(pid,'Pattern-ID',100)
        item={'id':pid,'revision':revision+1,'name':name,'theme':layouts.theme(data.get('theme')),'updated':now()}
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE');old=db.execute('SELECT revision FROM design_patterns WHERE id=?',(pid,)).fetchone()
            if (old and old[0]!=revision) or (not old and revision):raise Conflict('Designpattern inzwischen geändert. Neu laden.')
            raw=json.dumps(item,ensure_ascii=False)
            db.execute('INSERT INTO design_patterns VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET revision=excluded.revision,payload=excluded.payload',(pid,item['revision'],raw))
            db.execute('INSERT INTO design_pattern_history VALUES(?,?,?)',(pid,item['revision'],raw))
        return item

    def plan(self,data):
        from app import Invalid,compose,new_outline,chapter,block,validate_outline,choice,LANGUAGES
        if data.get('source_id'):
            with self.store.connect() as db:
                source=db.execute('SELECT name FROM sources WHERE id=?',(data['source_id'],)).fetchone()
            if not source:raise Invalid('Quelldatei nicht gefunden.')
            chunks=self.store.sources.chunks(data['source_id'])
            if sum(len(c['text']) for c in chunks)>500000:raise Invalid('Für die Gestaltung höchstens 500.000 Textzeichen wählen.')
            language=choice(data.get('language','de'),LANGUAGES,'Dokumentsprache')
            outline=new_outline(source[0]);outline['profile']['language']=language;outline['chapters']=[]
            current=None;body=[];fenced=False
            def flush():
                if current is None:return
                text="\n".join(body).strip()
                if text:
                    if len(text)>100000:raise Invalid('Ein Abschnitt überschreitet 100.000 Zeichen; vorher aufteilen.')
                    current['blocks'].append(dict(block(),text=text,text_format='markdown',source='Quelle '+data['source_id'],status='Entwurf',language=language))
                body.clear()
            for line in "\n\n".join(c['text'] for c in chunks).splitlines():
                if line.lstrip().startswith(('```','~~~')):fenced=not fenced
                match=None if fenced else re.match(r'^(#{1,6})\s+(.+)$',line)
                if match:
                    flush();previous=current['level'] if current else 0
                    current=chapter(match[2],min(len(match[1]),previous+1,6));outline['chapters'].append(current)
                else:
                    if current is None:current=chapter('Inhalt');outline['chapters'].append(current)
                    body.append(line)
            flush()
            if not outline['chapters']:outline['chapters']=[chapter('Inhalt')]
            outline=validate_outline(outline)
        elif data.get('outline_id'):
            outline=self.store.get(data['outline_id'])
            if data.get('revision')!=outline['revision']:raise Invalid('Gliederung geändert. Designstudio neu öffnen.')
        else:
            outline=new_outline('Designbeispiel');outline['chapters']=[chapter('Kapitel'),chapter('Unterkapitel',2)]
            outline['chapters'][0]['blocks']=[dict(block(),text='Hinweis: Angaben prüfen.\n\nAchtung: Freigabe erforderlich.\n\nTipp: Häufige Abläufe dokumentieren.\n\nAusnahme: Ländervorgaben beachten.')]
            outline=validate_outline(outline)
        before=compose(outline,outline['profile']);after=copy.deepcopy(before)
        after['layout']={'theme':layouts.theme(data.get('theme'))}
        return before,after

    def preview(self,data):
        before,after=self.plan(data);loader=lambda aid,rev:self.store.media.image(aid,rev,'intern')
        now=time.monotonic();self.previews={k:v for k,v in self.previews.items() if v['expires']>now}
        if len(self.previews)>10:self.previews={}
        result={}
        for key,plan in [('before',before),('after',after)]:
            token=secrets.token_urlsafe(24);self.previews[token]={'expires':now+900,'html':renderers.html_export(plan,loader)}
            result[key]='/design-preview/'+token
        return result

    def preview_file(self,token):
        from app import Invalid
        item=self.previews.get(token)
        if not item or item['expires']<time.monotonic():raise Invalid('Vorschau abgelaufen; erneut erzeugen.')
        return item['html']

    def export(self,data):
        from app import choice,office_export
        _,plan=self.plan(data);fmt=choice(data.get('format'),['docx','pptx','html','pdf'],'Ausgabeformat')
        loader=lambda aid,rev:self.store.media.image(aid,rev,'intern')
        raw=renderers.html_export(plan,loader) if fmt=='html' else renderers.pdf_export(plan,loader) if fmt=='pdf' else office_export(plan,fmt,loader)
        return raw,fmt
