import copy
import unittest
import os
import tempfile
from types import SimpleNamespace
from unittest.mock import patch
from meme_generator.features.element_templates import fingerprint
from meme_generator.features.reviewed_faces import validate_tenor_face


class ReviewedFaceAdmissionTests(unittest.TestCase):
    def test_repeated_native_bootstrap_keeps_loaded_tenor_recipes(self):
        from meme_generator.features import catalog
        with tempfile.TemporaryDirectory() as state,patch.dict(os.environ,{'GENSTICKER_STATE_DIR':state,'GENSTICKER_BOOTSTRAP_SEEDS':'0'}),patch.object(catalog,'get_memes',return_value=[SimpleNamespace(key='tenor_face_'+'a'*24)]),patch.object(catalog,'publish') as publish:
            catalog.bootstrap()
            publish.assert_not_called()

    def test_only_recipe_bound_approved_face_source_is_admitted(self):
        spec={'frames':[{'layers':[{'type':'face','expression':{'driver':{'method':'geometry-v1'}}}]}]}
        metadata={'origin':'tenor','source_url':'https://tenor.com/view/cat-123','source_use':'explicit-user-request-with-attribution',
                  'license':'unverified','min_images':1,'max_images':1,'min_texts':0,'max_texts':0,
                  'review':{'source':'local-tenor-face-review','visual_status':'approved','template_key':'face',
                            'method':'geometry','selected_spec_sha256':fingerprint(spec),'annotation_sha256':'a'*64}}
        validate_tenor_face('face',spec,metadata)
        for field,value in [('source_url','https://attacker.example/view/cat'),('license','licensed'),('max_texts',1)]:
            changed=copy.deepcopy(metadata);changed[field]=value
            with self.assertRaises(ValueError):validate_tenor_face('face',spec,changed)
        for field,value in [('method','gan'),('template_key','different'),('selected_spec_sha256','b'*64),('visual_status','pending'),('annotation_sha256','')]:
            changed=copy.deepcopy(metadata);changed['review'][field]=value
            with self.assertRaises(ValueError):validate_tenor_face('face',spec,changed)
