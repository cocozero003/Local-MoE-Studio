"""Per-user authentication, conversations, tokens and document retrieval for Team Hub.

Only local SQLite storage; account/session/API secrets are hashed at rest.
"""
from __future__ import annotations

import hashlib
from contextlib import contextmanager
import hmac
import re
import secrets
import sqlite3
import time
from pathlib import Path

USERNAME_RE = re.compile(r"^[A-Za-z0-9._-]{3,30}$")
TOKEN_TTL = 8 * 3600


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _password_hash(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 390000).hex()


class TeamDB:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    @contextmanager
    def _connect(self):
        # sqlite3's own context manager commits but does not close the file.
        # Explicit close is needed for Windows cleanup and safe database management.
        db = sqlite3.connect(str(self.path), timeout=15)
        try:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA foreign_keys = ON")
            db.execute("PRAGMA busy_timeout = 15000")
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def _init(self):
        with self._connect() as db:
            db.execute("PRAGMA journal_mode = WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY, username TEXT NOT NULL UNIQUE,
                    salt TEXT NOT NULL, password_hash TEXT NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('admin','member')),
                    created REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    csrf TEXT NOT NULL, expires REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS api_keys (
                    id INTEGER PRIMARY KEY, token_hash TEXT NOT NULL UNIQUE,
                    prefix TEXT NOT NULL, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    created REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS conversations (
                    id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    title TEXT NOT NULL, created REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY, conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                    role TEXT NOT NULL CHECK(role IN ('user','assistant')),
                    content TEXT NOT NULL, created REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS documents (
                    id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    name TEXT NOT NULL, created REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS chunks (
                    id INTEGER PRIMARY KEY, document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                    seq INTEGER NOT NULL, content TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
                CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(conversation_id,id);
                CREATE INDEX IF NOT EXISTS idx_convs_user ON conversations(user_id,id);
                CREATE INDEX IF NOT EXISTS idx_doc_user ON documents(user_id,id);
            """)
            try:
                db.execute("CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(content, tokenize='trigram')")
                self.fts_available = True
            except sqlite3.OperationalError:
                self.fts_available = False

    def has_users(self):
        with self._connect() as db:
            return bool(db.execute("SELECT 1 FROM users LIMIT 1").fetchone())

    def create_user(self, username, password, role='member', *, initial=False):
        username = str(username).strip()
        if not USERNAME_RE.fullmatch(username):
            raise ValueError("Username must be 3-30 letters, numbers, dots, dashes or underscores")
        if not (12 <= len(password) <= 256):
            raise ValueError("Password must be at least 12 characters")
        if role not in ('member','admin'):
            raise ValueError('Invalid role')
        salt = secrets.token_hex(16)
        with self._connect() as db:
            if initial:
                # Atomic first-admin creation even if simultaneous setup requests arrive.
                db.execute('BEGIN IMMEDIATE')
                if db.execute('SELECT 1 FROM users LIMIT 1').fetchone():
                    raise ValueError('Administrator already configured')
                role = 'admin'
            cur = db.execute('INSERT INTO users(username,salt,password_hash,role,created) VALUES (?,?,?,?,?)',
                             (username,salt,_password_hash(password,salt),role,time.time()))
            return cur.lastrowid

    def authenticate(self, username, password):
        with self._connect() as db:
            row = db.execute('SELECT * FROM users WHERE username=?', (username,)).fetchone()
        # Deliberately do a password hash for invalid users too.
        salt = row['salt'] if row else '0' * 32
        expected = row['password_hash'] if row else '0' * 64
        correct = hmac.compare_digest(_password_hash(password,salt),expected)
        return dict(row) if correct and row else None

    def create_session(self,user_id):
        token = secrets.token_urlsafe(32)
        csrf = secrets.token_urlsafe(24)
        with self._connect() as db:
            db.execute('DELETE FROM sessions WHERE expires < ?', (time.time(),))
            db.execute('INSERT INTO sessions(token_hash,user_id,csrf,expires) VALUES (?,?,?,?)',
                       (_hash(token),user_id,csrf,time.time()+TOKEN_TTL))
        return token,csrf

    def session_user(self, token):
        if not token:
            return None
        with self._connect() as db:
            row=db.execute('''SELECT u.id,u.username,u.role,s.csrf FROM sessions s
                JOIN users u ON u.id=s.user_id WHERE s.token_hash=? AND s.expires>?''',
                (_hash(token),time.time())).fetchone()
            return dict(row) if row else None

    def logout(self,token):
        with self._connect() as db:
            db.execute('DELETE FROM sessions WHERE token_hash=?',(_hash(token),))

    def add_key(self,user_id):
        raw='lms_'+secrets.token_urlsafe(36)
        prefix=raw[:12]
        with self._connect() as db:
            db.execute('INSERT INTO api_keys(token_hash,prefix,user_id,created) VALUES (?,?,?,?)',
                       (_hash(raw),prefix,user_id,time.time()))
        return raw

    def key_user(self,raw):
        if not raw.startswith('lms_'):
            return None
        with self._connect() as db:
            row=db.execute('''SELECT u.id,u.username,u.role FROM api_keys k
                JOIN users u ON u.id=k.user_id WHERE token_hash=?''', (_hash(raw),)).fetchone()
            return dict(row) if row else None

    def keys(self,user_id):
        with self._connect() as db:
            return [dict(row) for row in db.execute('SELECT id,prefix,created FROM api_keys WHERE user_id=? ORDER BY id DESC',(user_id,))]

    def delete_key(self,user_id,key_id):
        with self._connect() as db:
            return db.execute('DELETE FROM api_keys WHERE id=? AND user_id=?',(key_id,user_id)).rowcount > 0

    def users(self):
        with self._connect() as db:
            return [dict(row) for row in db.execute('SELECT id,username,role,created FROM users ORDER BY id')]

    def add_conversation(self,user_id,title):
        with self._connect() as db:
            cur=db.execute('INSERT INTO conversations(user_id,title,created) VALUES (?,?,?)',
                           (user_id,title[:100],time.time()))
            return cur.lastrowid

    def conversations(self,user_id):
        with self._connect() as db:
            return [dict(row) for row in db.execute('SELECT id,title,created FROM conversations WHERE user_id=? ORDER BY id DESC LIMIT 100',(user_id,))]

    def owns_conversation(self,user_id,conversation_id):
        with self._connect() as db:
            return bool(db.execute('SELECT 1 FROM conversations WHERE id=? AND user_id=?',(conversation_id,user_id)).fetchone())

    def messages(self,user_id,conversation_id):
        with self._connect() as db:
            return [dict(row) for row in db.execute('''SELECT m.role,m.content,m.created FROM messages m
                 JOIN conversations c ON m.conversation_id=c.id
                 WHERE c.user_id=? AND c.id=? ORDER BY m.id ASC LIMIT 300''',(user_id,conversation_id))]

    def add_message(self,user_id,conversation_id,role,content):
        if not self.owns_conversation(user_id,conversation_id):
            raise PermissionError('Conversation not found')
        with self._connect() as db:
            db.execute('INSERT INTO messages(conversation_id,role,content,created) VALUES (?,?,?,?)',
                       (conversation_id,role,content,time.time()))

    def delete_conversation(self,user_id,conversation_id):
        with self._connect() as db:
            return db.execute('DELETE FROM conversations WHERE id=? AND user_id=?',(conversation_id,user_id)).rowcount > 0

    def add_document(self,user_id,name,text):
        # Plain-text chunks; lexical retriever. No external embeddings or cloud service.
        text = text[:800000]
        chunks=[]
        step=1700
        for i,start in enumerate(range(0,len(text),step)):
            part=text[start:start+1900].strip()
            if part:
                chunks.append((i,part))
        with self._connect() as db:
            cur=db.execute('INSERT INTO documents(user_id,name,created) VALUES (?,?,?)',
                           (user_id,name[:180],time.time()))
            doc_id=cur.lastrowid
            for seq,part in chunks:
                ci=db.execute('INSERT INTO chunks(document_id,seq,content) VALUES (?,?,?)',(doc_id,seq,part)).lastrowid
                if self.fts_available:
                    db.execute('INSERT INTO chunks_fts(rowid,content) VALUES (?,?)',(ci,part))
            return doc_id

    def documents(self,user_id):
        with self._connect() as db:
            return [dict(row) for row in db.execute('SELECT id,name,created FROM documents WHERE user_id=? ORDER BY id DESC',(user_id,))]

    def delete_document(self,user_id,doc_id):
        with self._connect() as db:
            rows=db.execute('SELECT c.id FROM chunks c JOIN documents d ON d.id=c.document_id WHERE d.user_id=? AND d.id=?',(user_id,doc_id)).fetchall()
            if self.fts_available:
                for row in rows:
                    db.execute('DELETE FROM chunks_fts WHERE rowid=?',(row['id'],))
            return db.execute('DELETE FROM documents WHERE id=? AND user_id=?',(doc_id,user_id)).rowcount > 0

    def search_documents(self,user_id,question,limit=4):
        q=question.strip()[:300]
        if len(q)<2:
            return []
        with self._connect() as db:
            if self.fts_available and len(q)>=3:
                # Trigram MATCH supports Thai and English without language-specific tokenization.
                terms = re.findall(r'[\w\u0e00-\u0e7f]{3,}',q,flags=re.UNICODE)
                terms = [term[:35] for term in terms if len(term)>=3][:6]
                for term in terms:
                    try:
                        rows=db.execute('''SELECT d.name,c.seq,c.content FROM chunks_fts f
                            JOIN chunks c ON c.id=f.rowid JOIN documents d ON d.id=c.document_id
                            WHERE d.user_id=? AND chunks_fts MATCH ? ORDER BY bm25(chunks_fts) LIMIT ?''',
                            (user_id,'"'+term.replace('"','')+'"',limit)).fetchall()
                        if rows:
                            return [dict(r) for r in rows]
                    except sqlite3.OperationalError:
                        pass
            # A fallback for very short questions and SQLite builds without FTS5.
            terms=re.findall(r'[\w\u0e00-\u0e7f]{2,}',q,flags=re.UNICODE)
            term = max(terms,key=len)[:80] if terms else q[:80]
            escaped=term.replace('\\','\\\\').replace('%','\\%').replace('_','\\_')
            rows=db.execute('''SELECT d.name,c.seq,c.content FROM chunks c
                    JOIN documents d ON d.id=c.document_id
                    WHERE d.user_id=? AND c.content LIKE ? ESCAPE '\\' LIMIT ?''',
                    (user_id,'%'+escaped+'%',limit)).fetchall()
            return [dict(r) for r in rows]
