"""Consistent local SQLite backups and explicitly reviewed whole-workspace restore."""
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import secrets
import sqlite3
import tempfile
import time
import zipfile

MAX_ARCHIVE = 128 * 1024 * 1024
MAX_DATABASE = 512 * 1024 * 1024


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def schema(db):
    return sorted(db.execute("SELECT type,name,tbl_name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'").fetchall())


def snapshot(store):
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder)/'snapshot.sqlite3'
        with closing(store.connect()) as source, closing(sqlite3.connect(path)) as target:
            source.backup(target)
        return path.read_bytes()


def archive(raw):
    from version import VERSION
    from app import Invalid
    if len(raw)>MAX_DATABASE:
        raise Invalid("Datenbank überschreitet 512 MB; eine externe Datensicherung ist erforderlich.")
    manifest = {"format":"oneSCM-backup-1","application":VERSION,"created":datetime.now(timezone.utc).isoformat(),"sha256":sha(raw),"bytes":len(raw)}
    output=io.BytesIO()
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as z:
        z.writestr('manifest.json',json.dumps(manifest))
        z.writestr('workspace.sqlite3',raw)
    result=output.getvalue()
    if len(result)>MAX_ARCHIVE:
        raise Invalid("Sicherungs-ZIP überschreitet 128 MB; eine externe Datensicherung ist erforderlich.")
    return result


class Backups:
    def __init__(self, store):
        self.store=store
        self.pending=None

    def export(self):
        return archive(snapshot(self.store))

    def inspect(self, raw):
        from app import Invalid
        from version import VERSION
        if not raw or len(raw)>MAX_ARCHIVE:
            raise Invalid('Sicherungsdatei muss zwischen 1 Byte und 128 MB groß sein.')
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as z:
                if sorted(z.namelist()) != ['manifest.json','workspace.sqlite3']:
                    raise Invalid('Keine gültige oneSCM-Sicherung: unerwarteter Archivinhalt.')
                if z.getinfo('manifest.json').file_size>10000 or z.getinfo('workspace.sqlite3').file_size>MAX_DATABASE:
                    raise Invalid('Entpackte Sicherung überschreitet das Größenlimit (512 MB).')
                manifest=json.loads(z.read('manifest.json'))
                dbraw=z.read('workspace.sqlite3')
            if not isinstance(manifest,dict) or manifest.get('format')!='oneSCM-backup-1' or manifest.get('application')!=VERSION:
                raise Invalid('Sicherung benötigt dieselbe Programmversion. Mit der passenden Version öffnen und migrieren.')
            if sha(dbraw)!=manifest.get('sha256') or len(dbraw)!=manifest.get('bytes'):
                raise Invalid('Prüfsumme der Sicherung stimmt nicht.')
            if not dbraw.startswith(b'SQLite format 3\x00'):
                raise Invalid('Sicherung enthält keine SQLite-Datenbank.')
            with tempfile.TemporaryDirectory() as folder:
                path=Path(folder)/'verify.sqlite3';path.write_bytes(dbraw)
                with closing(sqlite3.connect(path)) as db, closing(self.store.connect()) as current:
                    db.execute('PRAGMA trusted_schema=OFF')
                    if schema(db)!=schema(current):
                        raise Invalid('Das Datenbankschema passt nicht zu dieser Programmversion.')
                    if db.execute('PRAGMA integrity_check').fetchall()!=[('ok',)] or db.execute('PRAGMA foreign_key_check').fetchone():
                        raise Invalid('Die Sicherung hat beschädigte oder ungültige Datenbankverknüpfungen.')
                    counts={name:db.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0] for name in ['outlines','sources','chunks','library','media','internal_entries','exports'] if db.execute('SELECT 1 FROM sqlite_master WHERE type=? AND name=?',('table',name)).fetchone()}
                    # Reject malformed stored JSON before replacing the workspace.
                    for _,name,_,_ in schema(db):
                        if not db.execute('SELECT 1 FROM sqlite_master WHERE type=? AND name=?',('table',name)).fetchone():continue
                        columns=[r[1] for r in db.execute(f'PRAGMA table_info("{name}")')]
                        for column in ['payload','plan']:
                            if column in columns:
                                for row in db.execute(f'SELECT "{column}" FROM "{name}"'):
                                    json.loads(row[0])
        except (zipfile.BadZipFile,RuntimeError,sqlite3.Error,json.JSONDecodeError,UnicodeDecodeError,KeyError) as exc:
            raise Invalid('Sicherung konnte nicht vollständig geprüft werden; Daten bleiben unverändert.') from exc
        token=secrets.token_urlsafe(24)
        self.pending={"token":token,"expires":time.monotonic()+900,"database":dbraw,"current_hash":sha(snapshot(self.store))}
        return {"token":token,"manifest":manifest,"counts":counts,"expires_minutes":15}

    def restore(self,data):
        from app import Invalid, Conflict
        pending=self.pending
        if not pending or pending['token']!=data.get('token') or time.monotonic()>pending['expires']:
            raise Invalid('Wiederherstellungsvorschau fehlt oder ist abgelaufen. Sicherung erneut prüfen.')
        if data.get('confirmation')!='WIEDERHERSTELLEN':
            raise Invalid('Zur Bestätigung WIEDERHERSTELLEN eingeben.')
        old=snapshot(self.store)
        if sha(old)!=pending['current_hash']:
            raise Conflict('Arbeitsdaten wurden seit der Vorschau geändert. Sicherung erneut prüfen.')
        folder=Path(self.store.path).parent/'backups';folder.mkdir(exist_ok=True)
        safety=folder/('vor-wiederherstellung-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+secrets.token_hex(3)+'.zip')
        # Complete the recovery copy before any live write.
        with safety.open('xb') as stream:stream.write(archive(old))
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'restore.sqlite3';path.write_bytes(pending['database'])
            with closing(sqlite3.connect(path)) as source, closing(self.store.connect()) as target:
                source.backup(target)
        self.pending=None
        return {"restored":True,"safety_backup":str(safety),"reload":True}
