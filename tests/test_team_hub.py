"""Security, user isolation, API compatibility and document retrieval smoke tests."""
import base64
import io
import json
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from localmoestudio.team_db import TeamDB
from localmoestudio.team_server import TeamHTTPServer,extract_document


class Backend(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_GET(self):
        if self.path=='/health':
            payload=b'{"status":"ok"}'
        elif self.path=='/v1/models':
            payload=b'{"object":"list","data":[{"id":"test-gguf","object":"model"}]}'
        else:
            self.send_error(404);return
        self.send_response(200)
        self.send_header('Content-Type','application/json')
        self.send_header('Content-Length',str(len(payload)))
        self.end_headers();self.wfile.write(payload)
    def do_POST(self):
        request=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        self.send_response(200)
        if request.get('stream'):
            self.send_header('Content-Type','text/event-stream');self.end_headers()
            for token in ['Hello',' world']:
                raw=('data: '+json.dumps({'choices':[{'delta':{'content':token}}]})+'\n\n').encode()
                self.wfile.write(raw);self.wfile.flush()
            self.wfile.write(b'data: [DONE]\n\n')
        else:
            payload=json.dumps({'choices':[{'message':{'role':'assistant','content':'Hello world'}}]}).encode()
            self.send_header('Content-Length',str(len(payload)));self.end_headers();self.wfile.write(payload)


class TeamTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.backend=ThreadingHTTPServer(('127.0.0.1',0),Backend)
        self.backend_thread=threading.Thread(target=self.backend.serve_forever,daemon=True)
        self.backend_thread.start()
        self.srv=TeamHTTPServer(('127.0.0.1',0),Path(self.tmp.name)/'team.db',
              'http://127.0.0.1:'+str(self.backend.server_port))
        self.thread=threading.Thread(target=self.srv.serve_forever,daemon=True)
        self.thread.start()
        self.base='http://127.0.0.1:'+str(self.srv.server_port)

    def tearDown(self):
        self.srv.shutdown();self.srv.server_close();self.thread.join(timeout=3)
        self.backend.shutdown();self.backend.server_close();self.backend_thread.join(timeout=3)
        self.tmp.cleanup()

    def request(self,path,data=None,method='GET',cookie=None,csrf=None,api=None,origin=None,host=None):
        headers={}
        if data is not None:headers['Content-Type']='application/json'
        if cookie:headers['Cookie']='lms_session='+cookie
        if csrf:headers['X-CSRF-Token']=csrf
        if api:headers['Authorization']='Bearer '+api
        if origin:headers['Origin']=origin
        if host:headers['Host']=host
        req=urllib.request.Request(self.base+path,
          data=None if data is None else json.dumps(data).encode(),headers=headers,method=method)
        try:
            with urllib.request.urlopen(req,timeout=5) as response:
                body=response.read().decode()
                return response.status,body,response.headers
        except urllib.error.HTTPError as error:
            return error.code,error.read().decode(),error.headers

    def admin(self):
        status,body,headers=self.request('/api/setup',{'username':'adminuser','password':'my-secret-password-123'},method='POST')
        self.assertEqual(status,201)
        cookie=headers['Set-Cookie'].split('lms_session=')[1].split(';')[0]
        csrf=json.loads(body)['csrf']
        return cookie,csrf

    def test_first_setup_login_and_csrf(self):
        status,_,_=self.request('/api/me')
        self.assertEqual(status,401)
        token,csrf=self.admin()
        status,_,_=self.request('/api/users',{'username':'bob','password':'bob-super-password-123'},method='POST',cookie=token)
        self.assertEqual(status,401)
        status,_,_=self.request('/api/users',{'username':'bob','password':'bob-super-password-123'},method='POST',cookie=token,csrf=csrf)
        self.assertEqual(status,201)
        status,_,_=self.request('/api/setup',{'username':'other','password':'another-long-password'},method='POST')
        self.assertEqual(status,400)
        status,_,_=self.request('/api/users',cookie=token)
        self.assertEqual(status,200)

    def test_user_chat_document_isolation_and_keys(self):
        cookie,csrf=self.admin()
        status,_,_=self.request('/api/users',{'username':'alice','password':'alice-password-123'},method='POST',cookie=cookie,csrf=csrf)
        self.assertEqual(status,201)
        status,body,hdr=self.request('/api/login',{'username':'alice','password':'alice-password-123'},method='POST')
        self.assertEqual(status,200)
        alice_cookie=hdr['Set-Cookie'].split('lms_session=')[1].split(';')[0]
        alice_csrf=json.loads(body)['csrf']
        status,body,_=self.request('/api/conversations',{'title':'Private'},method='POST',cookie=cookie,csrf=csrf)
        conv=json.loads(body)['id']
        status,_,_=self.request('/api/conversations/'+str(conv),cookie=alice_cookie)
        self.assertEqual(status,404)
        raw=base64.b64encode('Confidential content on Thai regulation and medical devices'.encode()).decode()
        status,body,_=self.request('/api/documents',{'name':'secret.txt','content_base64':raw},method='POST',cookie=cookie,csrf=csrf)
        self.assertEqual(status,201)
        doc_id=json.loads(body)['id']
        status,body,_=self.request('/api/search?q=Confidential',cookie=alice_cookie)
        self.assertEqual(len(json.loads(body)['items']),0)
        status,body,_=self.request('/api/search?q=Confidential',cookie=cookie)
        self.assertGreaterEqual(len(json.loads(body)['items']),1)
        status,body,_=self.request('/api/keys',{},method='POST',cookie=alice_cookie,csrf=alice_csrf)
        key=json.loads(body)['api_key']
        self.assertTrue(key.startswith('lms_'))
        status,body,_=self.request('/v1/models',api=key)
        self.assertEqual(status,200)
        self.assertIn('test-gguf',body)
        status,_,_=self.request('/api/documents/'+str(doc_id),method='DELETE',cookie=alice_cookie,csrf=alice_csrf)
        self.assertEqual(status,404)
        status,body,_=self.request('/api/chat/send',{'conversation_id':conv,'message':'hello'},method='POST',cookie=cookie,csrf=csrf)
        self.assertEqual(status,200)
        self.assertIn('Hello',body)
        status,body,_=self.request('/api/conversations/'+str(conv),cookie=cookie)
        self.assertEqual(len(json.loads(body)['items']),2)
        status,body,_=self.request('/v1/chat/completions',{'model':'test-gguf','messages':[{'role':'user','content':'Hello'}]},method='POST',api=key)
        self.assertEqual(status,200)
        self.assertIn('Hello world',body)

    def test_origin_and_host_rejection(self):
        cookie,csrf=self.admin()
        status,_,_=self.request('/api/keys',{},method='POST',cookie=cookie,csrf=csrf,origin='https://evil.invalid')
        self.assertEqual(status,403)
        status,_,_=self.request('/api/me',cookie=cookie,host='attacker.invalid')
        self.assertEqual(status,403)

    def test_static_ui_and_untrusted_path(self):
        status,body,_=self.request('/')
        self.assertEqual(status,200)
        self.assertIn('Local MoE Studio',body)
        for path in ('/app.js','/app.css'):
            status,_,_=self.request(path)
            self.assertEqual(status,200)
        status,_,_=self.request('/private-data')
        self.assertEqual(status,401)

    def test_extractor_txt_and_docx(self):
        self.assertEqual(extract_document('ok.md',b'# Title'), '# Title')
        with io.BytesIO() as stream:
            with zipfile.ZipFile(stream,'w') as z:
                z.writestr('word/document.xml','<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Test document</w:t></w:r></w:p></w:body></w:document>')
            self.assertIn('Test document',extract_document('ok.docx',stream.getvalue()))
        with self.assertRaises(ValueError):extract_document('bad.exe',b'NO')


if __name__=='__main__':unittest.main()
