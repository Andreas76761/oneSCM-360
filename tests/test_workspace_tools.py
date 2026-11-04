import copy
import io
import json
from pathlib import Path
import tempfile
import sqlite3
import unittest
import zipfile
from unittest.mock import patch
import app
import backups
import variant_export


class WorkspaceToolsTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.store=app.Store(Path(self.temp.name)/'db.sqlite3')
        outline=app.new_outline('Varianten')
        outline['chapters']=[app.chapter('Vertrag',mandatory=True)]
        for language in ['de','en','fr']:
            for role in ['Retailer','HQ']:
                outline['chapters'][0]['blocks'].append(dict(app.block(),text=f'CONTENT_{language}_{role}',language=language,role=role,status='Freigegeben',note='PRIVATE_NOTE'))
        self.outline=self.store.save(outline)
        self.request={'id':self.outline['id'],'revision':self.outline['revision'],'languages':['de','en','fr'],'roles':['Retailer','HQ'],'documents':['Handbuch','Releaseletter','Quickreference'],'formats':['html']}

    def tearDown(self):self.temp.cleanup()

    def test_database_context_closes_handles_and_rolls_back_errors(self):
        with self.store.connect() as db:
            self.assertEqual(db.execute('SELECT 1').fetchone()[0],1)
        with self.assertRaises(sqlite3.ProgrammingError):db.execute('SELECT 1')
        with self.assertRaises(RuntimeError):
            with self.store.connect() as db:
                db.execute('DELETE FROM outlines')
                raise RuntimeError('rollback')
        self.assertEqual(self.store.get(self.outline['id'])['title'],'Varianten')

    def test_backup_restore_round_trip_and_recovery_copy(self):
        original=self.store.backups.export()
        outline=self.store.get(self.outline['id']);outline['title']='Neu';self.store.save(outline)
        source=self.store.sources.upload('Quelle.txt',b'Quelle',{})
        before=backups.snapshot(self.store)
        preview=self.store.backups.inspect(original)
        result=self.store.backups.restore({'token':preview['token'],'confirmation':'WIEDERHERSTELLEN'})
        self.assertEqual(self.store.get(outline['id'])['title'],'Varianten')
        self.assertEqual(self.store.sources.listing(),[])
        with zipfile.ZipFile(result['safety_backup']) as z:self.assertEqual(z.read('workspace.sqlite3'),before)
        with self.assertRaises(app.Invalid):self.store.backups.restore({'token':preview['token'],'confirmation':'WIEDERHERSTELLEN'})

    def test_confirmation_stale_preview_and_failed_safety_copy_do_not_write(self):
        raw=self.store.backups.export();preview=self.store.backups.inspect(raw)
        with self.assertRaises(app.Invalid):self.store.backups.restore({'token':preview['token']})
        outline=self.store.get(self.outline['id']);outline['title']='Änderung';self.store.save(outline)
        with self.assertRaises(app.Conflict):self.store.backups.restore({'token':preview['token'],'confirmation':'WIEDERHERSTELLEN'})
        preview=self.store.backups.inspect(raw)
        before=backups.snapshot(self.store)
        with patch.object(Path,'open',side_effect=OSError('disk full')):
            with self.assertRaises(OSError):self.store.backups.restore({'token':preview['token'],'confirmation':'WIEDERHERSTELLEN'})
        self.assertEqual(backups.snapshot(self.store),before)

    def test_invalid_archives_checksum_schema_and_version_are_rejected(self):
        original=self.store.backups.export();before=backups.snapshot(self.store)
        with self.assertRaises(app.Invalid):self.store.backups.inspect(b'not a zip')
        with zipfile.ZipFile(io.BytesIO(original)) as z:manifest=json.loads(z.read('manifest.json'));dbraw=z.read('workspace.sqlite3')
        for change in [{'sha256':'bad'},{'application':'999.0'}]:
            output=io.BytesIO()
            with zipfile.ZipFile(output,'w') as z:z.writestr('manifest.json',json.dumps({**manifest,**change}));z.writestr('workspace.sqlite3',dbraw)
            with self.assertRaises(app.Invalid):self.store.backups.inspect(output.getvalue())
        self.assertEqual(backups.snapshot(self.store),before)
        with self.store.connect() as db:db.execute('CREATE TABLE malicious(extra TEXT)')
        with self.assertRaises(app.Invalid):self.store.backups.inspect(original)

    def test_batch_matrix_selects_languages_roles_and_records_artifacts(self):
        original=copy.deepcopy(self.store.get(self.outline['id']))
        preview=variant_export.preview(self.store,self.request)
        self.assertEqual(preview['count'],18)
        raw=variant_export.export(self.store,{**self.request,'fingerprint':preview['fingerprint'],'reviewed':True})
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            report=json.loads(z.read('Pruefbericht.json'))
            self.assertEqual(len(report['files']),18)
            for entry in report['files']:
                html=z.read(entry['file']).decode();p=entry['profile']
                self.assertIn(f'CONTENT_{p["language"]}_{p["role"]}',html)
                self.assertNotIn('PRIVATE_NOTE',html)
                for language in ['de','en','fr']:
                    for role in ['Retailer','HQ']:
                        if (language,role)!=(p['language'],p['role']):self.assertNotIn(f'CONTENT_{language}_{role}',html)
        self.assertEqual(self.store.get(self.outline['id']),original)
        self.assertEqual(len(self.store.usage(self.outline['id'])['exports']),18)

    def test_batch_rejects_unreviewed_changed_and_oversized_requests(self):
        preview=variant_export.preview(self.store,self.request)
        with self.assertRaises(app.Invalid):variant_export.export(self.store,{**self.request,'fingerprint':preview['fingerprint']})
        with self.assertRaises(app.Conflict):variant_export.export(self.store,{**self.request,'fingerprint':'old','reviewed':True})
        with self.assertRaises(app.Invalid):variant_export.preview(self.store,{**self.request,'formats':['docx','pptx','pdf','html']})
        self.assertEqual(self.store.usage(self.outline['id'])['exports'],[])

    def test_failed_renderer_does_not_record_partial_batch(self):
        preview=variant_export.preview(self.store,self.request)
        with patch('variant_export.renderers.html_export',side_effect=RuntimeError('render failed')):
            with self.assertRaises(RuntimeError):variant_export.export(self.store,{**self.request,'fingerprint':preview['fingerprint'],'reviewed':True})
        self.assertEqual(self.store.usage(self.outline['id'])['exports'],[])

if __name__=='__main__':unittest.main()
