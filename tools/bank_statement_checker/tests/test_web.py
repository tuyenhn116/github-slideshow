import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

from statement_checker.web import Handler
from tests.test_checker import build_statement


class WebTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def post(self, data, name="sao ke.pdf"):
        req = urllib.request.Request(self.base + "/api/analyze", data=data, method="POST",
                                     headers={"Content-Type": "application/pdf",
                                              "X-Filename": urllib.request.quote(name)})
        try:
            with urllib.request.urlopen(req) as res:
                return res.status, json.loads(res.read())
        except urllib.error.HTTPError as err:
            return err.code, json.loads(err.read())

    def test_index_page(self):
        with urllib.request.urlopen(self.base + "/") as res:
            self.assertIn("Kiểm tra sao kê", res.read().decode("utf-8"))

    def test_analyze_upload(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "s.pdf")
            build_statement(path)
            with open(path, "rb") as fh:
                status, body = self.post(fh.read(), "Sao kê tháng 1.pdf")
        self.assertEqual(status, 200)
        self.assertEqual(body["path"], "Sao kê tháng 1.pdf")
        self.assertLess(body["score"], 20)

    def test_empty_upload_rejected(self):
        status, body = self.post(b"")
        self.assertEqual(status, 400)


if __name__ == "__main__":
    unittest.main()
