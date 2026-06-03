import sqlite3
import json
from pathlib import Path

DB_FILE = Path(__file__).parent / "data" / "soma.db"

class SomaDB:
    def __init__(self, db_path: Path = DB_FILE):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_db()

    def _get_conn(self):
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self):
        with self._get_conn() as conn:
            # 1. 멘토링/특강 테이블
            conn.execute("""
                CREATE TABLE IF NOT EXISTS mentorings (
                    id TEXT PRIMARY KEY,
                    type TEXT,
                    title TEXT,
                    author TEXT,
                    dateStr TEXT,
                    timeRangeStr TEXT,
                    status TEXT,
                    location TEXT,
                    deliveryMethod TEXT,
                    isOnline INTEGER,
                    raw_json TEXT
                )
            """)
            # 2. 개인 시간표 테이블
            conn.execute("""
                CREATE TABLE IF NOT EXISTS user_calendar (
                    id TEXT PRIMARY KEY,
                    title TEXT,
                    url TEXT,
                    author TEXT,
                    dateStr TEXT,
                    timeRangeStr TEXT,
                    status TEXT,
                    isApproved INTEGER,
                    raw_json TEXT
                )
            """)
            # 3. 팀 매칭 테이블
            conn.execute("""
                CREATE TABLE IF NOT EXISTS team_info (
                    teamName TEXT PRIMARY KEY,
                    leader TEXT,
                    members TEXT,
                    mentorName TEXT,
                    projectName TEXT,
                    ictCategoryLarge TEXT,
                    ictCategoryMedium TEXT,
                    raw_json TEXT
                )
            """)
            # 4. 대화 기록 테이블 (영속 기억)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS chat_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT,
                    role TEXT,
                    content TEXT,
                    tool_calls TEXT,
                    tool_call_id TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

    # ── 멘토링 데이터 CRUD ──
    def save_mentorings(self, items: list[dict]):
        with self._get_conn() as conn:
            conn.execute("DELETE FROM mentorings")
            for item in items:
                conn.execute("""
                    INSERT OR REPLACE INTO mentorings (
                        id, type, title, author, dateStr, timeRangeStr, status, 
                        location, deliveryMethod, isOnline, raw_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    str(item.get("id", "")),
                    item.get("type", ""),
                    item.get("title", ""),
                    item.get("author", ""),
                    item.get("dateStr", ""),
                    item.get("timeRangeStr", ""),
                    item.get("status", ""),
                    item.get("location", ""),
                    item.get("deliveryMethod", ""),
                    1 if item.get("isOnline") else 0,
                    json.dumps(item, ensure_ascii=False)
                ))
            conn.commit()

    def load_mentorings(self) -> list[dict]:
        with self._get_conn() as conn:
            cursor = conn.execute("SELECT raw_json FROM mentorings")
            rows = cursor.fetchall()
            return [json.loads(row["raw_json"]) for row in rows]

    # ── 개인 시간표 CRUD ──
    def save_user_calendar(self, items: list[dict]):
        with self._get_conn() as conn:
            conn.execute("DELETE FROM user_calendar")
            for item in items:
                conn.execute("""
                    INSERT OR REPLACE INTO user_calendar (
                        id, title, url, author, dateStr, timeRangeStr, status, isApproved, raw_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    str(item.get("id", "")),
                    item.get("title", ""),
                    item.get("url", ""),
                    item.get("author", ""),
                    item.get("dateStr", ""),
                    item.get("timeRangeStr", ""),
                    item.get("status", ""),
                    1 if item.get("isApproved") else 0,
                    json.dumps(item, ensure_ascii=False)
                ))
            conn.commit()

    def load_user_calendar(self) -> list[dict]:
        with self._get_conn() as conn:
            cursor = conn.execute("SELECT raw_json FROM user_calendar")
            rows = cursor.fetchall()
            return [json.loads(row["raw_json"]) for row in rows]

    # ── 팀 매칭 CRUD ──
    def save_team_info(self, items: list[dict]):
        with self._get_conn() as conn:
            conn.execute("DELETE FROM team_info")
            for item in items:
                conn.execute("""
                    INSERT OR REPLACE INTO team_info (
                        teamName, leader, members, mentorName, projectName, 
                        ictCategoryLarge, ictCategoryMedium, raw_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    item.get("teamName", ""),
                    item.get("leader", ""),
                    ",".join(item.get("members", [])) if isinstance(item.get("members"), list) else str(item.get("members", "")),
                    item.get("mentorName", ""),
                    item.get("projectName", ""),
                    item.get("ictCategoryLarge", ""),
                    item.get("ictCategoryMedium", ""),
                    json.dumps(item, ensure_ascii=False)
                ))
            conn.commit()

    def load_team_info(self) -> list[dict]:
        with self._get_conn() as conn:
            cursor = conn.execute("SELECT raw_json FROM team_info")
            rows = cursor.fetchall()
            return [json.loads(row["raw_json"]) for row in rows]

    # ── 대화 기억(Session Messages) CRUD ──
    def save_chat_message(self, session_id: str, role: str, content: str, tool_calls: str = None, tool_call_id: str = None):
        with self._get_conn() as conn:
            conn.execute("""
                INSERT INTO chat_messages (session_id, role, content, tool_calls, tool_call_id)
                VALUES (?, ?, ?, ?, ?)
            """, (session_id, role, content, tool_calls, tool_call_id))
            conn.commit()

    def load_chat_history(self, session_id: str, limit: int = 30) -> list[dict]:
        with self._get_conn() as conn:
            cursor = conn.execute("""
                SELECT role, content, tool_calls, tool_call_id 
                FROM chat_messages 
                WHERE session_id = ? 
                ORDER BY id ASC
            """, (session_id,))
            rows = cursor.fetchall()
            history = []
            for row in rows:
                msg = {
                    "role": row["role"],
                    "content": row["content"] or ""
                }
                if row["tool_calls"]:
                    msg["tool_calls"] = json.loads(row["tool_calls"])
                if row["tool_call_id"]:
                    msg["tool_call_id"] = row["tool_call_id"]
                history.append(msg)
            return history[-limit:]

    def clear_chat_history(self, session_id: str):
        with self._get_conn() as conn:
            conn.execute("DELETE FROM chat_messages WHERE session_id = ?", (session_id,))
            conn.commit()

# 싱글톤 인스턴스 노출
db = SomaDB()
