import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from polylab.server import Handler


class USValidationAPITests(unittest.TestCase):
    def request(self, root, path):
        response = {}
        handler = object.__new__(Handler)
        handler.path = path
        handler.host_ok = lambda: True
        handler.respond = lambda value,status=200: response.update(value=value,status=status)
        handler.send_file = lambda path: response.update(file=path,status=200)
        with patch('polylab.server.ROOT', root):
            handler.do_GET()
        return response

    def test_only_matching_audited_report_and_chart_are_exposed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(self.request(root,'/api/us/transfer')['value'], {'status':'pending'})
            study = root/'data/us-transfer/study/analysis'; study.mkdir(parents=True)
            (root/'data/us-transfer-latest.json').write_text(json.dumps(dict(directory=str(study))))
            self.assertEqual(self.request(root,'/api/us/transfer')['value'], {'status':'pending_audit'})
            raw = json.dumps(dict(results=[])).encode(); (study/'report.json').write_bytes(raw)
            (study/'audit.json').write_text(json.dumps(dict(status='passed',report_sha256=hashlib.sha256(raw).hexdigest())))
            self.assertEqual(self.request(root,'/api/us/transfer')['value'], {'results':[]})
            self.assertEqual(self.request(root,'/api/us/transfer/chart?slippage=.005')['file'], study/'transfer-slippage.png')
            (study/'report.json').write_text('{}')
            self.assertEqual(self.request(root,'/api/us/transfer')['status'], 400)
            (root/'data/us-transfer-latest.json').write_text(json.dumps(dict(directory=str(root))))
            self.assertEqual(self.request(root,'/api/us/transfer')['status'], 400)
