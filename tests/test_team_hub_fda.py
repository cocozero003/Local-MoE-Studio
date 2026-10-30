"""Thai FDA Team Hub integration tests without controlled production data."""
import json
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from localmoestudio.team_server import TeamHTTPServer


class Backend(BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def do_GET(self):
        if self.path=="/health":
            payload=b'{"status":"ok"}'
        elif self.path=="/v1/models":
            payload=b'{"object":"list","data":[{"id":"test","object":"model"}]}'
        else:
            self.send_error(404);return
        self.send_response(200);self.send_header("Content-Type","application/json")
        self.send_header("Content-Length",str(len(payload)));self.end_headers();self.wfile.write(payload)
    def do_POST(self):
        body=self.rfile.read(int(self.headers["Content-Length"]))
        self.server.last_request=json.loads(body)
        payload=b'data: {"choices":[{"delta":{"content":"FDA answer"}}]}\n\ndata: [DONE]\n\n'
        self.send_response(200);self.send_header("Content-Type","text/event-stream")
        self.send_header("Content-Length",str(len(payload)));self.end_headers();self.wfile.write(payload)


class ThaiFDATeamHubTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.backend=ThreadingHTTPServer(("127.0.0.1",0),Backend);self.backend.last_request=None
        self.bt=threading.Thread(target=self.backend.serve_forever,daemon=True);self.bt.start()
        self.srv=TeamHTTPServer(("127.0.0.1",0),Path(self.tmp.name)/"team.db",
              "http://127.0.0.1:"+str(self.backend.server_port))
        self.st=threading.Thread(target=self.srv.serve_forever,daemon=True);self.st.start()
        self.base="http://127.0.0.1:"+str(self.srv.server_port)
        self.patches=[
            patch("localmoestudio.team_server.fda_status",return_value={"available":True,"version":"V3.17","engine":"test"}),
            patch("localmoestudio.team_server.fda_analyze",return_value={
                "version":"V3.17","query":{"candidate_class":"MEDICAL_DEVICE"},
                "precedents":[{"portfolio_rank":1,"portfolio_role":"BEST_ANALOGUE",
                "precedent_product":"Test dressing","precedent_year":"2026",
                "historical_class":"MEDICAL_DEVICE"}],
                "human_authorization_required":True}),
            patch("localmoestudio.team_server.fda_grounding_context",return_value="FDA_GROUNDING_CONTEXT"),
        ]
        for p in self.patches:p.start()

    def tearDown(self):
        for p in reversed(self.patches):p.stop()
        self.srv.shutdown();self.srv.server_close();self.st.join(timeout=3)
        self.backend.shutdown();self.backend.server_close();self.bt.join(timeout=3)
        self.tmp.cleanup()

    def request(self,path,data=None,method="GET",cookie=None,csrf=None):
        headers={}
        if data is not None:headers["Content-Type"]="application/json"
        if cookie:headers["Cookie"]="lms_session="+cookie
        if csrf:headers["X-CSRF-Token"]=csrf
        req=urllib.request.Request(self.base+path,data=None if data is None else json.dumps(data).encode(),
                                   headers=headers,method=method)
        try:
            with urllib.request.urlopen(req,timeout=5) as response:
                return response.status,response.read().decode(),response.headers
        except urllib.error.HTTPError as e:
            return e.code,e.read().decode(),e.headers

    def admin(self):
        status,body,headers=self.request("/api/setup",
            {"username":"adminuser","password":"my-secret-password-123"},method="POST")
        self.assertEqual(status,201)
        return headers["Set-Cookie"].split("lms_session=")[1].split(";")[0],json.loads(body)["csrf"]

    def test_fda_status_analyze_and_chat_grounding(self):
        cookie,csrf=self.admin()
        status,body,_=self.request("/api/fda/status",cookie=cookie)
        self.assertEqual(status,200);self.assertTrue(json.loads(body)["available"])
        status,body,_=self.request("/api/fda/analyze",{"text":"wound dressing","top_k":5},
                                   method="POST",cookie=cookie,csrf=csrf)
        self.assertEqual(status,200)
        self.assertEqual(json.loads(body)["query"]["candidate_class"],"MEDICAL_DEVICE")
        status,body,_=self.request("/api/conversations",{"title":"FDA"},method="POST",cookie=cookie,csrf=csrf)
        conv=json.loads(body)["id"]
        status,body,_=self.request("/api/chat/send",
            {"conversation_id":conv,"message":"classify wound dressing","mode":"thai_fda"},
            method="POST",cookie=cookie,csrf=csrf)
        self.assertEqual(status,200)
        self.assertIn("FDA answer",body)
        self.assertIn("BEST_ANALOGUE",body)
        self.assertEqual(self.backend.last_request["messages"][0]["content"],"FDA_GROUNDING_CONTEXT")

if __name__=="__main__":unittest.main()
