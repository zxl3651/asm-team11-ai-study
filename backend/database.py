import sqlite3
import json
from pathlib import Path
from data_validation import (
    validate_calendar_event,
    validate_mentoring,
    validate_team,
    validate_user_info,
)

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
            self._ensure_columns(conn, "mentorings", {
                "startAt": "TEXT",
                "endAt": "TEXT",
                "qualityStatus": "TEXT DEFAULT 'valid'",
                "validationErrors": "TEXT DEFAULT '[]'",
                "validationWarnings": "TEXT DEFAULT '[]'",
                "canonicalText": "TEXT DEFAULT ''",
            })
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
            self._ensure_columns(conn, "user_calendar", {
                "ownerName": "TEXT DEFAULT ''",
                "source": "TEXT DEFAULT 'user_history'",
                "startAt": "TEXT",
                "endAt": "TEXT",
                "qualityStatus": "TEXT DEFAULT 'valid'",
                "validationErrors": "TEXT DEFAULT '[]'",
                "validationWarnings": "TEXT DEFAULT '[]'",
                "canonicalText": "TEXT DEFAULT ''",
            })
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
            self._ensure_columns(conn, "team_info", {
                "qualityStatus": "TEXT DEFAULT 'valid'",
                "validationErrors": "TEXT DEFAULT '[]'",
                "validationWarnings": "TEXT DEFAULT '[]'",
                "canonicalText": "TEXT DEFAULT ''",
            })
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
            # 5. 사용자 기본 정보 테이블
            conn.execute("""
                CREATE TABLE IF NOT EXISTS user_info (
                    id TEXT PRIMARY KEY,
                    name TEXT,
                    email TEXT,
                    phone TEXT,
                    role TEXT,
                    techStacks TEXT,
                    raw_json TEXT
                )
            """)
            self._ensure_columns(conn, "user_info", {
                "qualityStatus": "TEXT DEFAULT 'valid'",
                "validationErrors": "TEXT DEFAULT '[]'",
                "validationWarnings": "TEXT DEFAULT '[]'",
                "canonicalText": "TEXT DEFAULT ''",
            })
            conn.commit()

    def _ensure_columns(self, conn: sqlite3.Connection, table: str, columns: dict[str, str]):
        cursor = conn.execute(f"PRAGMA table_info({table})")
        existing = {row["name"] for row in cursor.fetchall()}
        for column, definition in columns.items():
            if column not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    # ── 멘토링 데이터 CRUD ──
    def save_mentorings(self, items: list[dict]):
        with self._get_conn() as conn:
            conn.execute("DELETE FROM mentorings")
            for item in items:
                quality = validate_mentoring(item)
                conn.execute("""
                    INSERT OR REPLACE INTO mentorings (
                        id, type, title, author, dateStr, timeRangeStr, status, 
                        location, deliveryMethod, isOnline, raw_json,
                        startAt, endAt, qualityStatus, validationErrors, validationWarnings, canonicalText
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    json.dumps({**item, **quality}, ensure_ascii=False),
                    quality["startAt"],
                    quality["endAt"],
                    quality["qualityStatus"],
                    json.dumps(quality["validationErrors"], ensure_ascii=False),
                    json.dumps(quality["validationWarnings"], ensure_ascii=False),
                    quality["canonicalText"],
                ))
            conn.commit()

    def load_mentorings(self) -> list[dict]:
        with self._get_conn() as conn:
            cursor = conn.execute("SELECT raw_json FROM mentorings")
            rows = cursor.fetchall()
            return [json.loads(row["raw_json"]) for row in rows]

    def get_mentoring_stats(self) -> dict:
        with self._get_conn() as conn:
            total = conn.execute("SELECT COUNT(*) AS count FROM mentorings").fetchone()["count"] or 0
            with_location = conn.execute(
                "SELECT COUNT(*) AS count FROM mentorings WHERE COALESCE(location, '') <> ''"
            ).fetchone()["count"] or 0
            with_delivery = conn.execute(
                "SELECT COUNT(*) AS count FROM mentorings WHERE COALESCE(deliveryMethod, '') <> ''"
            ).fetchone()["count"] or 0
            by_status_rows = conn.execute(
                "SELECT status, COUNT(*) AS count FROM mentorings GROUP BY status ORDER BY count DESC"
            ).fetchall()
            return {
                "total": total,
                "with_location": with_location,
                "with_delivery_method": with_delivery,
                "by_status": {row["status"] or "알수없음": row["count"] for row in by_status_rows},
            }

    def get_participant_registration_stats(self) -> dict:
        participant_counts: dict[str, int] = {}
        total_links = 0
        for item in self.load_mentorings():
            raw_names = (
                item.get("participantNames")
                or item.get("participants")
                or item.get("applicantNames")
                or item.get("appliedUserNames")
                or []
            )
            if isinstance(raw_names, str):
                raw_names = [part.strip() for part in raw_names.replace("·", ",").replace("/", ",").split(",")]
            if not isinstance(raw_names, list):
                continue
            excluded_names = {
                "로그아웃", "공지사항", "등록일", "마이페이지", "멘토링", "특강", "접수내역",
                "모집안내", "링크드인", "교육과정", "연수센터", "전체메뉴", "신청", "취소",
                "상태", "승인", "이름", "소속", "연수생", "멘토",
                "목록", "블로그", "사업소개", "소마기술력", "소마사람들", "안녕하세요",
                "알림마당", "연혁", "월간일정", "유튜브", "이용약관", "인스타그램",
                "주요성과", "참여후기", "창업기업", "팀매칭", "페이스북", "회원정보", "거짓",
            }
            seen_names = []
            for name in raw_names:
                clean_name = str(name or "").strip()
                if clean_name and clean_name not in excluded_names and clean_name not in seen_names:
                    seen_names.append(clean_name)
            max_expected = (
                item.get("maxParticipants")
                or item.get("max_participants")
                or item.get("totalCount")
                or item.get("appliedCount")
                or 0
            )
            try:
                max_expected = int(max_expected)
            except Exception:
                max_expected = 0
            if max_expected > 0 and len(seen_names) > max_expected + 5:
                continue
            for name in seen_names:
                participant_counts[name] = participant_counts.get(name, 0) + 1
                total_links += 1
        return {
            "participant_count": len(participant_counts),
            "registration_link_count": total_links,
            "by_participant": dict(sorted(participant_counts.items(), key=lambda item: (-item[1], item[0]))),
        }

    # ── 개인 시간표 CRUD ──
    def save_user_calendar(self, items: list[dict], owner_name: str | None = None):
        with self._get_conn() as conn:
            normalized_owner = (owner_name or "").strip()
            if normalized_owner:
                conn.execute("DELETE FROM user_calendar WHERE ownerName = ? OR ownerName = ''", (normalized_owner,))
            else:
                conn.execute("DELETE FROM user_calendar WHERE ownerName = ''")
            for item in items:
                quality = validate_calendar_event(item)
                original_id = str(item.get("id", ""))
                db_id = f"{normalized_owner}:{original_id}" if normalized_owner else original_id
                raw_json = {
                    **item,
                    **quality,
                    "id": original_id,
                    "originalId": original_id,
                    "ownerName": normalized_owner,
                }
                conn.execute("""
                    INSERT OR REPLACE INTO user_calendar (
                        id, ownerName, title, url, author, dateStr, timeRangeStr, status, isApproved, raw_json, source,
                        startAt, endAt, qualityStatus, validationErrors, validationWarnings, canonicalText
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    db_id,
                    normalized_owner,
                    item.get("title", ""),
                    item.get("url", ""),
                    item.get("author", ""),
                    item.get("dateStr", ""),
                    item.get("timeRangeStr", ""),
                    item.get("status", ""),
                    1 if item.get("isApproved") else 0,
                    json.dumps(raw_json, ensure_ascii=False),
                    item.get("source", "user_history"),
                    quality["startAt"],
                    quality["endAt"],
                    quality["qualityStatus"],
                    json.dumps(quality["validationErrors"], ensure_ascii=False),
                    json.dumps(quality["validationWarnings"], ensure_ascii=False),
                    quality["canonicalText"],
                ))
            conn.commit()

    def load_user_calendar(self, owner_name: str | None = None) -> list[dict]:
        with self._get_conn() as conn:
            if owner_name is None:
                cursor = conn.execute("SELECT raw_json FROM user_calendar")
            else:
                normalized_owner = owner_name.strip()
                cursor = conn.execute("SELECT raw_json FROM user_calendar WHERE ownerName = ?", (normalized_owner,))
            rows = cursor.fetchall()
            return [json.loads(row["raw_json"]) for row in rows]

    def has_user_calendar_for_owner(self, owner_name: str | None) -> bool:
        normalized_owner = (owner_name or "").strip()
        if not normalized_owner:
            return False
        with self._get_conn() as conn:
            count = conn.execute(
                "SELECT COUNT(*) AS count FROM user_calendar WHERE ownerName = ?",
                (normalized_owner,),
            ).fetchone()["count"] or 0
            return count > 0

    def get_user_calendar_stats(self) -> dict:
        with self._get_conn() as conn:
            total = conn.execute("SELECT COUNT(*) AS count FROM user_calendar").fetchone()["count"] or 0
            by_source_rows = conn.execute(
                "SELECT source, COUNT(*) AS count FROM user_calendar GROUP BY source ORDER BY count DESC"
            ).fetchall()
            by_owner_rows = conn.execute(
                "SELECT ownerName, COUNT(*) AS count FROM user_calendar GROUP BY ownerName ORDER BY count DESC"
            ).fetchall()
            by_owner_source_rows = conn.execute(
                "SELECT ownerName, source, COUNT(*) AS count FROM user_calendar GROUP BY ownerName, source"
            ).fetchall()
            by_owner_source: dict[str, dict[str, int]] = {}
            for row in by_owner_source_rows:
                owner = row["ownerName"] or "unknown"
                source = row["source"] or "unknown"
                by_owner_source.setdefault(owner, {})[source] = row["count"]
            return {
                "total": total,
                "by_source": {row["source"] or "unknown": row["count"] for row in by_source_rows},
                "by_owner": {row["ownerName"] or "unknown": row["count"] for row in by_owner_rows},
                "by_owner_source": by_owner_source,
            }

    # ── 팀 매칭 CRUD ──
    def save_team_info(self, items: list[dict]):
        with self._get_conn() as conn:
            conn.execute("DELETE FROM team_info")
            for item in items:
                quality = validate_team(item)
                conn.execute("""
                    INSERT OR REPLACE INTO team_info (
                        teamName, leader, members, mentorName, projectName, 
                        ictCategoryLarge, ictCategoryMedium, raw_json,
                        qualityStatus, validationErrors, validationWarnings, canonicalText
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    item.get("teamName", ""),
                    item.get("leader", ""),
                    ",".join(item.get("members", [])) if isinstance(item.get("members"), list) else str(item.get("members", "")),
                    item.get("mentorName", ""),
                    item.get("projectName", ""),
                    item.get("ictCategoryLarge", ""),
                    item.get("ictCategoryMedium", ""),
                    json.dumps({**item, **quality}, ensure_ascii=False),
                    quality["qualityStatus"],
                    json.dumps(quality["validationErrors"], ensure_ascii=False),
                    json.dumps(quality["validationWarnings"], ensure_ascii=False),
                    quality["canonicalText"],
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

    def clear_all_portal_data(self):
        with self._get_conn() as conn:
            conn.execute("DELETE FROM user_calendar")
            conn.execute("DELETE FROM mentorings")
            conn.execute("DELETE FROM team_info")
            conn.execute("DELETE FROM user_info")
            conn.execute("DELETE FROM chat_messages")
            conn.commit()

    # ── 사용자 기본 정보 CRUD ──
    def save_user_info(self, item: dict | None):
        with self._get_conn() as conn:
            conn.execute("DELETE FROM user_info")
            if item:
                quality = validate_user_info(item)
                conn.execute("""
                    INSERT OR REPLACE INTO user_info (
                        id, name, email, phone, role, techStacks, raw_json,
                        qualityStatus, validationErrors, validationWarnings, canonicalText
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    "me",
                    item.get("name", ""),
                    item.get("email", ""),
                    item.get("phone", ""),
                    item.get("role", ""),
                    ",".join(item.get("techStacks", [])) if isinstance(item.get("techStacks"), list) else str(item.get("techStacks", "")),
                    json.dumps({**item, **quality}, ensure_ascii=False),
                    quality["qualityStatus"],
                    json.dumps(quality["validationErrors"], ensure_ascii=False),
                    json.dumps(quality["validationWarnings"], ensure_ascii=False),
                    quality["canonicalText"],
                ))
            conn.commit()

    def get_data_readiness(self) -> dict:
        with self._get_conn() as conn:
            def counts(table: str) -> dict:
                row = conn.execute(
                    f"""
                    SELECT
                        COUNT(*) AS total,
                        SUM(CASE WHEN qualityStatus = 'valid' THEN 1 ELSE 0 END) AS valid,
                        SUM(CASE WHEN qualityStatus = 'partial' THEN 1 ELSE 0 END) AS partial,
                        SUM(CASE WHEN qualityStatus = 'invalid' THEN 1 ELSE 0 END) AS invalid
                    FROM {table}
                    """
                ).fetchone()
                return {
                    "total": row["total"] or 0,
                    "valid": row["valid"] or 0,
                    "partial": row["partial"] or 0,
                    "invalid": row["invalid"] or 0,
                }

            return {
                "user_info": counts("user_info"),
                "user_calendar": counts("user_calendar"),
                "mentorings": counts("mentorings"),
                "team_info": counts("team_info"),
            }

    def load_user_info(self) -> dict | None:
        with self._get_conn() as conn:
            cursor = conn.execute("SELECT raw_json FROM user_info")
            row = cursor.fetchone()
            return json.loads(row["raw_json"]) if row else None

# 싱글톤 인스턴스 노출
db = SomaDB()
