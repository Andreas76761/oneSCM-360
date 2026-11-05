"""Read-only workspace counts and storage on the database volume."""
import json
import shutil
from pathlib import Path
from collections import Counter


def snapshot(store):
    from app import now
    from version import VERSION
    with store.connect() as db:
        db.execute('BEGIN')
        counts={key:db.execute('SELECT COUNT(*) FROM '+table).fetchone()[0] for key,table in [('documents','sources'),('chunks','chunks'),('outlines','outlines'),('library','library'),('exports','exports')]}
        images=[json.loads(r[0]) for r in db.execute('SELECT payload FROM media')]
        counts.update(images=len(images),archived_images=sum(bool(m.get('archived')) for m in images),approved_images=sum(m.get('status')=='Freigegeben' and m.get('pii_reviewed') is True and not m.get('archived') for m in images))
        types=Counter(Path(r[0]).suffix.lower().lstrip('.') or 'ohne Endung' for r in db.execute('SELECT name FROM sources'))
        page_size=db.execute('PRAGMA page_size').fetchone()[0]
        reusable=db.execute('PRAGMA freelist_count').fetchone()[0]*page_size
    database=Path(store.path).resolve()
    warnings=[];files={}
    for suffix in ['', '-wal','-shm','-journal']:
        path=Path(str(database)+suffix)
        try:files['database' if not suffix else suffix[1:]]=path.stat().st_size
        except FileNotFoundError:pass
        except OSError:warnings.append('Eine Datenbankdatei konnte nicht vermessen werden.')
    try:
        disk=shutil.disk_usage(database.parent)
        volume={'total':disk.total,'used':disk.used,'free':disk.free}
    except OSError:
        volume=None;warnings.append('Laufwerksbelegung ist momentan nicht verfügbar.')
    return {'updated':now(),'version':VERSION,'counts':counts,'file_types':dict(sorted(types.items())),
            'storage':{'application_bytes':sum(files.values()),'files':files,'reusable_database_bytes':reusable,'volume':volume},'warnings':warnings}
