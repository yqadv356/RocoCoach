"""Local single-user memory: explicit preferences and observed learning events."""
import json
from pathlib import Path
import sqlite3

from rococoach.config import ROOT

DEFAULT_DB = ROOT / "data/private/coach.sqlite3"


class Memory:
    def __init__(self, path=None):
        self.path = Path(path or DEFAULT_DB)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS profile (id INTEGER PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS events (
                  id TEXT PRIMARY KEY, kind TEXT NOT NULL, value TEXT NOT NULL,
                  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
                CREATE TABLE IF NOT EXISTS match_sessions (
                  id TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS control_requests (
                  id TEXT PRIMARY KEY, value TEXT NOT NULL);
            """)

    def connect(self):
        return sqlite3.connect(self.path)

    def profile(self):
        with self.connect() as db:
            row = db.execute("SELECT value FROM profile WHERE id=1").fetchone()
        return json.loads(row[0]) if row else {"nickname":"小训练家", "preference":"简洁、先给提示", "mood":"平静"}

    def save_profile(self, nickname, preference, mood):
        if mood not in {"平静", "有点挫败", "想挑战"}:
            raise ValueError("请选择支持的心情。")
        value = {"nickname":nickname.strip()[:30] or "小训练家", "preference":preference.strip()[:200], "mood":mood}
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO profile VALUES (1,?)", (json.dumps(value, ensure_ascii=False),))
        return value

    def add(self, event_id, kind, value):
        if kind not in {"review", "quiz", "chat", "turn"}:
            raise ValueError("不支持的记忆事件。")
        with self.connect() as db:
            db.execute("INSERT OR IGNORE INTO events(id,kind,value) VALUES (?,?,?)",
                       (event_id, kind, json.dumps(value, ensure_ascii=False)))

    def recent(self, limit=5):
        with self.connect() as db:
            rows = db.execute("SELECT kind,value,created_at FROM events ORDER BY rowid DESC LIMIT ?", (limit,)).fetchall()
        return [{"kind":k,"value":json.loads(v),"created_at":t} for k,v,t in rows]

    def summary(self):
        with self.connect() as db:
            rows=db.execute("SELECT kind,value FROM events WHERE kind IN ('review','quiz') ORDER BY rowid DESC LIMIT 5").fetchall()
        recent=[{"kind":k,"value":json.loads(v)} for k,v in rows]
        return {"profile":self.profile(),"recent":[
            {"kind":e["kind"],"topic":e["value"].get("topic", "招式比较"),
             "correct":e["value"].get("correct"),"focus":e["value"].get("focus"),"focus_status":e["value"].get("focus_status"),"mode":e["value"].get("mode")}
            for e in recent],
            "note":"只记录用户明确偏好和已发生的练习，不据此断言真实段位或性格。"}

    def chat_history(self, limit=6):
        with self.connect() as db:
            rows=db.execute("SELECT value FROM events WHERE kind='chat' ORDER BY rowid DESC LIMIT ?",(limit,)).fetchall()
        return [json.loads(row[0]) for row in reversed(rows)]

    def save_match(self, match):
        with self.connect() as db:
            db.execute('INSERT INTO match_sessions(id,value) VALUES (?,?) ON CONFLICT(id) DO UPDATE SET value=excluded.value',
                       (match['id'],json.dumps(match,ensure_ascii=False)))

    def latest_match(self):
        with self.connect() as db:
            row=db.execute('SELECT value FROM match_sessions ORDER BY rowid DESC LIMIT 1').fetchone()
        return json.loads(row[0]) if row else None
