"""Ratings must survive gallery changes without losing earlier versions."""
import importlib.util
import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen


class TemplateReviewServerTests(unittest.TestCase):
    def test_versioned_ratings_persist_and_cross_origin_writes_are_rejected(self):
        path=Path(__file__).resolve().parents[4]/'tools/qa/serve_template_review.py'
        loader=importlib.util.spec_from_file_location('review_server',path)
        module=importlib.util.module_from_spec(loader);loader.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'data.json').write_text(json.dumps({'templates':[{'key':'fixture','version':2}],'samples':['S03']}))
            ratings=root/'ratings.json';ratings.write_text(json.dumps({'records':{'fixture@1:S03':{'rating':'需调整'}}}))
            server=module.ThreadingHTTPServer(('127.0.0.1',0),module.make_handler(root,ratings))
            thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.01});thread.start()
            origin=f'http://127.0.0.1:{server.server_port}'
            body=json.dumps({'key':'fixture','version':2,'sample':'S03','rating':'可用','note':'完整覆盖'}).encode()
            def request(origin_header):
                return urlopen(Request(origin+'/api/reviews',data=body,headers={'Content-Type':'application/json','Origin':origin_header}),timeout=2)
            try:
                with self.assertRaises(HTTPError) as denied:request('https://unrelated.example')
                self.assertEqual(denied.exception.code,403)
                self.assertEqual(list(json.loads(ratings.read_text())['records']),['fixture@1:S03'])
                with request(origin) as response:self.assertTrue(json.load(response)['saved'])
            finally:server.shutdown();thread.join();server.server_close()
            saved=json.loads(ratings.read_text())['records']
            self.assertEqual(saved['fixture@1:S03']['rating'],'需调整')
            self.assertEqual(saved['fixture@2:S03']['rating'],'可用')
            self.assertEqual(saved['fixture@2:S03']['note'],'完整覆盖')
            self.assertEqual(len(ratings.with_suffix('.jsonl').read_text().splitlines()),1)
            self.assertFalse(list(root.glob('tmp*')))


if __name__=='__main__':unittest.main()
