"""Privacy-first conversation storage: one JSON file per local session."""
import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

class SessionStore:
    def __init__(self, directory):
        self.directory=Path(directory)
        self.directory.mkdir(parents=True,exist_ok=True)
    def _path(self,sid):
        if not re.fullmatch(r'[a-f0-9]{32}',sid): raise ValueError('Invalid session identifier')
        return self.directory / (sid+'.json')
    def _write(self,sid,record):
        path=self._path(sid); temp=path.with_suffix('.tmp')
        temp.write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
        os.replace(temp,path)
    def create(self):
        sid=uuid.uuid4().hex
        self._write(sid,{'id':sid,'title':'New chat','updated':datetime.now(timezone.utc).isoformat(), 'messages':[]})
        return sid
    def read(self,sid):
        return json.loads(self._path(sid).read_text(encoding='utf-8'))
    def append_pair(self,sid,user_text,assistant_text):
        record=self.read(sid)
        record['messages'].extend([{'role':'user','content':user_text}, {'role':'assistant','content':assistant_text}])
        if record['title']=='New chat': record['title']=user_text.strip()[:70] or 'New chat'
        record['updated']=datetime.now(timezone.utc).isoformat()
        self._write(sid,record)
    def list_all(self):
        items=[]
        for f in self.directory.glob('*.json'):
            try:
                record=json.loads(f.read_text(encoding='utf-8'))
                if record.get('id')==f.stem: items.append({k:record.get(k) for k in ('id','title','updated')})
            except (OSError,ValueError): continue
        return sorted(items,key=lambda x:x.get('updated',''),reverse=True)
    def delete(self,sid):
        self._path(sid).unlink(missing_ok=True)
