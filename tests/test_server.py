import json,tempfile,threading,unittest,urllib.request,urllib.error
from pathlib import Path
from shiyu.app import Server
from shiyu.library import Library
class ServerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.lib=Library(self.temp.name);self.server=Server(('127.0.0.1',0),self.lib,'unit-token');threading.Thread(target=self.server.serve_forever,daemon=True).start();self.url='http://127.0.0.1:'+str(self.server.server_port)
    def tearDown(self):self.server.shutdown();self.server.server_close();self.lib.executor.shutdown();self.temp.cleanup()
    def test_authentication_and_origin(self):
        with self.assertRaises(urllib.error.HTTPError) as exc:urllib.request.urlopen(self.url+'/api/state')
        self.assertEqual(exc.exception.code,403)
        req=urllib.request.Request(self.url+'/api/state',headers={'X-Shiyu-Token':'unit-token'})
        with urllib.request.urlopen(req) as r:self.assertEqual(json.load(r)['stats']['total'],0)
        req=urllib.request.Request(self.url+'/api/state',headers={'X-Shiyu-Token':'unit-token','Origin':'https://other.test'})
        with self.assertRaises(urllib.error.HTTPError) as exc:urllib.request.urlopen(req)
        self.assertEqual(exc.exception.code,403)
    def test_no_arbitrary_files(self):
        req=urllib.request.Request(self.url+'/file/../library.sqlite3?t=unit-token')
        with self.assertRaises(urllib.error.HTTPError):urllib.request.urlopen(req)
if __name__=='__main__':unittest.main()
