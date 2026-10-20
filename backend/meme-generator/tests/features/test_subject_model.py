import hashlib,os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from meme_generator.features import subject_model

class SubjectModelTests(unittest.TestCase):
    def test_only_verified_public_model_is_downloadable(self):
        with tempfile.TemporaryDirectory() as directory:
            app=FastAPI();app.include_router(subject_model.router)
            content=b'public model test fixture';digest=hashlib.sha256(content).hexdigest()
            model=Path(directory)/'u2netp.onnx'
            with patch.dict(os.environ,{'U2NET_HOME':directory}),patch.object(subject_model,'MODEL_SHA',digest),patch.object(subject_model,'MODEL_BYTES',len(content)),TestClient(app) as client:
                self.assertEqual(client.get('/images/subject-model/private.onnx').status_code,404)
                self.assertEqual(client.get('/images/subject-model/'+digest+'.onnx').status_code,503)
                model.write_bytes(content)
                response=client.get('/images/subject-model/'+digest+'.onnx')
                self.assertEqual(response.status_code,200);self.assertEqual(response.content,content)
                self.assertIn('immutable',response.headers['cache-control'])
                model.write_bytes(b'x'*len(content))
                self.assertEqual(client.get('/images/subject-model/'+digest+'.onnx').status_code,503)
            subject_model.verified.cache_clear()
