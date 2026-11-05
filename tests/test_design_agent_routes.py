"""Exercise HTTP handlers without opening sockets or requiring network access."""
import io
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch
import app

class DesignAgentRouteTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.store=app.Store(Path(self.temp.name)/'db.sqlite3')
  with patch.object(app,'ThreadingHTTPServer',side_effect=lambda address,handler:SimpleNamespace(server_port=address[1],handler=handler)):
   self.server=app.make_server(self.store,8765)
  self.handler=self.server.handler.__new__(self.server.handler);self.handler.server=self.server
  self.handler.send=lambda code,body,content_type=None,headers=None:self.responses.append((code,body,content_type,headers))
  self.responses=[];self.token=None
  self.token=self.get('/api/state')[1]['token']
 def tearDown(self):self.temp.cleanup()
 def get(self,path):
  self.handler.path=path;self.handler.headers={'Host':'127.0.0.1:8765'};self.handler.do_GET();return self.responses[-1]
 def post(self,path,data):
  raw=json.dumps(data).encode();self.handler.path=path;self.handler.headers={'Host':'127.0.0.1:8765','X-Local-Token':self.token,'Content-Length':str(len(raw))};self.handler.rfile=io.BytesIO(raw);self.handler.do_POST();return self.responses[-1]
 def test_design_pattern_preview_and_export_routes(self):
  source=self.store.sources.upload('Input.md',b'# Heading\n\nAchtung: Pruefen.',{})
  data={'source_id':source['id'],'theme':{'chapter_size':24,'attention_border':False}}
  self.assertEqual(self.post('/api/design/save',{'name':'Saved','theme':data['theme']})[0],200)
  self.assertEqual(len(self.post('/api/design/patterns',{})[1]),1)
  response=self.post('/api/design/preview',data);self.assertEqual(response[0],200)
  before=self.get(response[1]['before']);after=self.get(response[1]['after'])
  self.assertEqual(after[0],200);self.assertIn("style-src 'unsafe-inline'",after[3]['Content-Security-Policy']);self.assertNotEqual(before[1],after[1])
  result=self.post('/api/design/export',{**data,'format':'docx'});self.assertEqual(result[0],200);self.assertTrue(result[1].startswith(b'PK'))
  self.assertEqual(self.get('/design-preview/missing')[0],404)
 def test_agent_catalog_and_step_routes(self):
  catalog=self.post('/api/agents/catalog',{})[1];self.assertEqual(len(catalog),9)
  source=self.store.sources.upload('Input.txt',b'Test source',{})
  row=self.post('/api/agents/start',{'sources':[source['id']],'agents':['extraction']})[1]
  response=self.post('/api/agents/step',{'id':row['id'],'revision':row['revision']})
  self.assertEqual(response[0],200);self.assertEqual(response[1]['status'],'review')
  self.assertEqual(len(self.post('/api/agents/list',{})[1]),1)
  self.assertEqual(self.post('/api/agents/get',{'id':row['id']})[0],200)

if __name__=='__main__':unittest.main()
