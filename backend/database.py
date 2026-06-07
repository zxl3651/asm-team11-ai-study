import sqlite3
import json
import re
from pathlib import Path
from data_validation import (
    validate_calendar_event,
    validate_mentoring,
    validate_team,
    validate_user_info,
)

DB_FILE = Path(__file__).parent / "data" / "soma.db"

EXCLUDED_PARTICIPANT_NAMES = {
    "로그아웃", "공지사항", "등록일", "마이페이지", "멘토링", "특강", "접수내역",
    "모집안내", "링크드인", "교육과정", "연수센터", "전체메뉴", "신청", "취소",
    "상태", "승인", "이름", "소속", "연수생", "멘토",
    "목록", "블로그", "사업소개", "소마기술력", "소마사람들", "안녕하세요",
    "알림마당", "연혁", "월간일정", "유튜브", "이용약관", "인스타그램",
    "주요성과", "참여후기", "창업기업", "팀매칭", "페이스북", "회원정보", "거짓",
}


def normalize_trainee_name(value: str | None) -> str:
    return re.sub(r"\s+", "", str(value or "").strip())


def clean_participant_names(item: dict) -> list[str]:
    raw_names = (
        item.get("participantNames")
        or item.get("participants")
        or item.get("applicantNames")
        or item.get("appliedUserNames")
        or []
    )
    if isinstance(raw_names, str):
        raw_names = [
            part.strip()
            for part in raw_names.replace("·", ",").replace("/", ",").split(",")
        ]
    if not isinstance(raw_names, list):
        return []

    seen: set[str] = set()
    names: list[str] = []
    for raw_name in raw_names:
        clean_name = str(raw_name or "").strip()
        normalized = normalize_trainee_name(clean_name)
        if not clean_name or not normalized:
            continue
        if clean_name in EXCLUDED_PARTICIPANT_NAMES or normalized in EXCLUDED_PARTICIPANT_NAMES:
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        names.append(clean_name)

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
    if max_expected > 0 and len(names) > max_expected + 5:
        return []
    return names


def normalize_team_members(item: dict) -> list[str]:
    raw_members = item.get("members") or []
    if isinstance(raw_members, str):
        raw_members = [part.strip() for part in raw_members.replace("·", ",").split(",")]
    members: list[str] = []
    for name in [item.get("leader", ""), *(raw_members if isinstance(raw_members, list) else [])]:
        clean_name = str(name or "").strip()
        normalized = normalize_trainee_name(clean_name)
        if clean_name and normalized and normalized not in {normalize_trainee_name(member) for member in members}:
            members.append(clean_name)
    return members


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
            # 6. 정규화 팀 테이블
            conn.execute("""
                CREATE TABLE IF NOT EXISTS teams (
                    id TEXT PRIMARY KEY,
                    teamName TEXT UNIQUE,
                    leaderName TEXT,
                    mentorName TEXT,
                    projectName TEXT,
                    ictCategoryLarge TEXT,
                    ictCategoryMedium TEXT,
                    raw_json TEXT,
                    qualityStatus TEXT DEFAULT 'valid',
                    validationErrors TEXT DEFAULT '[]',
                    validationWarnings TEXT DEFAULT '[]',
                    canonicalText TEXT DEFAULT ''
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS team_members (
                    teamId TEXT,
                    teamName TEXT,
                    traineeName TEXT,
                    normalizedTraineeName TEXT,
                    role TEXT,
                    PRIMARY KEY (teamId, normalizedTraineeName)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS trainees (
                    normalizedName TEXT PRIMARY KEY,
                    name TEXT,
                    email TEXT DEFAULT '',
                    role TEXT DEFAULT '연수생',
                    source TEXT DEFAULT 'portal',
                    raw_json TEXT DEFAULT '{}'
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS mentoring_participants (
                    mentoringId TEXT,
                    traineeName TEXT,
                    normalizedTraineeName TEXT,
                    participantStatus TEXT DEFAULT 'registered',
                    source TEXT DEFAULT 'mentoring_detail',
                    syncedAt DATETIME DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (mentoringId, normalizedTraineeName)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS mentoring_embedding_docs (
                    docId TEXT PRIMARY KEY,
                    mentoringId TEXT,
                    docType TEXT,
                    canonicalText TEXT,
                    vectorStoreId TEXT,
                    syncedAt DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sync_runs (
                    id TEXT PRIMARY KEY,
                    startedAt DATETIME DEFAULT CURRENT_TIMESTAMP,
                    finishedAt DATETIME,
                    status TEXT,
                    listCount INTEGER DEFAULT 0,
                    detailSuccessCount INTEGER DEFAULT 0,
                    detailFailCount INTEGER DEFAULT 0,
                    participantLinkCount INTEGER DEFAULT 0,
                    vectorDocumentCount INTEGER DEFAULT 0
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sync_item_results (
                    syncRunId TEXT,
                    mentoringId TEXT,
                    url TEXT,
                    status TEXT,
                    errorMessage TEXT DEFAULT '',
                    participantCount INTEGER DEFAULT 0,
                    syncedAt DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_mentoring_participants_name ON mentoring_participants(normalizedTraineeName)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_team_members_name ON team_members(normalizedTraineeName)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_mentorings_startAt ON mentorings(startAt)")
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
            conn.execute("DELETE FROM mentoring_participants")
            conn.execute("DELETE FROM mentoring_embedding_docs")
            conn.execute("DELETE FROM sync_item_results WHERE syncRunId = 'latest'")
            conn.execute("""
                INSERT OR REPLACE INTO sync_runs (
                    id, startedAt, status, listCount, detailSuccessCount, detailFailCount, participantLinkCount, vectorDocumentCount
                ) VALUES ('latest', CURRENT_TIMESTAMP, 'running', ?, 0, 0, 0, 0)
            """, (len(items),))
            detail_success_count = 0
            detail_fail_count = 0
            participant_link_count = 0
            for item in items:
                quality = validate_mentoring(item)
                participant_names = clean_participant_names(item)
                raw_json = {**item, **quality, "participantNames": participant_names}
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
                    json.dumps(raw_json, ensure_ascii=False),
                    quality["startAt"],
                    quality["endAt"],
                    quality["qualityStatus"],
                    json.dumps(quality["validationErrors"], ensure_ascii=False),
                    json.dumps(quality["validationWarnings"], ensure_ascii=False),
                    quality["canonicalText"],
                ))
                mentoring_id = str(item.get("id", ""))
                detail_status = item.get("detailStatus") or item.get("detailFetchStatus") or ("success" if participant_names or item.get("location") or item.get("deliveryMethod") else "unknown")
                if detail_status in ("success", "ok", "parsed"):
                    detail_success_count += 1
                elif detail_status in ("failed", "error"):
                    detail_fail_count += 1
                conn.execute("""
                    INSERT INTO sync_item_results (
                        syncRunId, mentoringId, url, status, errorMessage, participantCount
                    ) VALUES ('latest', ?, ?, ?, ?, ?)
                """, (
                    mentoring_id,
                    item.get("url", ""),
                    detail_status,
                    item.get("detailError", ""),
                    len(participant_names),
                ))
                doc_id = f"mentoring:{mentoring_id}"
                conn.execute("""
                    INSERT OR REPLACE INTO mentoring_embedding_docs (
                        docId, mentoringId, docType, canonicalText, vectorStoreId
                    ) VALUES (?, ?, 'mentoring_event', ?, ?)
                """, (
                    doc_id,
                    mentoring_id,
                    quality["canonicalText"],
                    mentoring_id,
                ))
                for participant_name in participant_names:
                    normalized_name = normalize_trainee_name(participant_name)
                    if not normalized_name:
                        continue
                    conn.execute("""
                        INSERT OR IGNORE INTO trainees (normalizedName, name, source, raw_json)
                        VALUES (?, ?, 'mentoring_detail', ?)
                    """, (
                        normalized_name,
                        participant_name,
                        json.dumps({"name": participant_name}, ensure_ascii=False),
                    ))
                    conn.execute("""
                        INSERT OR REPLACE INTO mentoring_participants (
                            mentoringId, traineeName, normalizedTraineeName, participantStatus, source
                        ) VALUES (?, ?, ?, 'registered', 'mentoring_detail')
                    """, (mentoring_id, participant_name, normalized_name))
                    participant_link_count += 1
            conn.execute("""
                UPDATE sync_runs
                SET finishedAt = CURRENT_TIMESTAMP,
                    status = 'success',
                    detailSuccessCount = ?,
                    detailFailCount = ?,
                    participantLinkCount = ?,
                    vectorDocumentCount = (SELECT COUNT(*) FROM mentoring_embedding_docs)
                WHERE id = 'latest'
            """, (detail_success_count, detail_fail_count, participant_link_count))
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
        with self._get_conn() as conn:
            rows = conn.execute("""
                SELECT traineeName, COUNT(*) AS count
                FROM mentoring_participants
                GROUP BY normalizedTraineeName, traineeName
                ORDER BY count DESC, traineeName ASC
            """).fetchall()
            participant_counts = {row["traineeName"]: row["count"] for row in rows}
            total_links = conn.execute(
                "SELECT COUNT(*) AS count FROM mentoring_participants"
            ).fetchone()["count"] or 0
        return {
            "participant_count": len(participant_counts),
            "registration_link_count": total_links,
            "by_participant": dict(sorted(participant_counts.items(), key=lambda item: (-item[1], item[0]))),
        }

    def load_participant_registrations(
        self,
        participant_name: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[dict]:
        normalized_name = normalize_trainee_name(participant_name)
        with self._get_conn() as conn:
            where = []
            params: list[str] = []
            if normalized_name:
                where.append("mp.normalizedTraineeName = ?")
                params.append(normalized_name)
            if start_date:
                where.append("date(m.startAt) >= date(?)")
                params.append(start_date)
            if end_date:
                where.append("date(m.startAt) <= date(?)")
                params.append(end_date)
            where_sql = f"WHERE {' AND '.join(where)}" if where else ""
            cursor = conn.execute(f"""
                SELECT
                    mp.mentoringId,
                    mp.traineeName,
                    mp.normalizedTraineeName,
                    mp.participantStatus,
                    mp.source AS participantSource,
                    mp.syncedAt,
                    m.raw_json,
                    m.startAt,
                    m.endAt,
                    m.qualityStatus
                FROM mentoring_participants mp
                JOIN mentorings m ON m.id = mp.mentoringId
                {where_sql}
                ORDER BY m.startAt ASC, m.title ASC
            """, params)
            rows = cursor.fetchall()
            registrations: list[dict] = []
            for row in rows:
                raw_json = json.loads(row["raw_json"]) if row["raw_json"] else {}
                registrations.append({
                    **raw_json,
                    "id": row["mentoringId"],
                    "mentoringId": row["mentoringId"],
                    "ownerName": row["traineeName"],
                    "participantName": row["traineeName"],
                    "normalizedParticipantName": row["normalizedTraineeName"],
                    "participantStatus": row["participantStatus"],
                    "source": "mentoring_registration",
                    "participantSource": row["participantSource"],
                    "syncedAt": row["syncedAt"],
                    "startAt": row["startAt"],
                    "endAt": row["endAt"],
                    "qualityStatus": row["qualityStatus"],
                })
            return registrations

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
            conn.execute("DELETE FROM teams")
            conn.execute("DELETE FROM team_members")
            for item in items:
                quality = validate_team(item)
                team_name = item.get("teamName", "")
                team_id = team_name
                members = normalize_team_members(item)
                raw_json = {**item, **quality, "members": members}
                conn.execute("""
                    INSERT OR REPLACE INTO team_info (
                        teamName, leader, members, mentorName, projectName, 
                        ictCategoryLarge, ictCategoryMedium, raw_json,
                        qualityStatus, validationErrors, validationWarnings, canonicalText
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    team_name,
                    item.get("leader", ""),
                    ",".join(members),
                    item.get("mentorName", ""),
                    item.get("projectName", ""),
                    item.get("ictCategoryLarge", ""),
                    item.get("ictCategoryMedium", ""),
                    json.dumps(raw_json, ensure_ascii=False),
                    quality["qualityStatus"],
                    json.dumps(quality["validationErrors"], ensure_ascii=False),
                    json.dumps(quality["validationWarnings"], ensure_ascii=False),
                    quality["canonicalText"],
                ))
                conn.execute("""
                    INSERT OR REPLACE INTO teams (
                        id, teamName, leaderName, mentorName, projectName,
                        ictCategoryLarge, ictCategoryMedium, raw_json,
                        qualityStatus, validationErrors, validationWarnings, canonicalText
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    team_id,
                    team_name,
                    item.get("leader", ""),
                    item.get("mentorName", ""),
                    item.get("projectName", ""),
                    item.get("ictCategoryLarge", ""),
                    item.get("ictCategoryMedium", ""),
                    json.dumps(raw_json, ensure_ascii=False),
                    quality["qualityStatus"],
                    json.dumps(quality["validationErrors"], ensure_ascii=False),
                    json.dumps(quality["validationWarnings"], ensure_ascii=False),
                    quality["canonicalText"],
                ))
                leader_name = str(item.get("leader", "")).strip()
                for member_name in members:
                    normalized_name = normalize_trainee_name(member_name)
                    if not normalized_name:
                        continue
                    role = "leader" if normalize_trainee_name(leader_name) == normalized_name else "member"
                    conn.execute("""
                        INSERT OR IGNORE INTO trainees (normalizedName, name, source, raw_json)
                        VALUES (?, ?, 'team_info', ?)
                    """, (
                        normalized_name,
                        member_name,
                        json.dumps({"name": member_name}, ensure_ascii=False),
                    ))
                    conn.execute("""
                        INSERT OR REPLACE INTO team_members (
                            teamId, teamName, traineeName, normalizedTraineeName, role
                        ) VALUES (?, ?, ?, ?, ?)
                    """, (team_id, team_name, member_name, normalized_name, role))
            conn.commit()

    def load_team_info(self) -> list[dict]:
        with self._get_conn() as conn:
            cursor = conn.execute("SELECT raw_json FROM team_info")
            rows = cursor.fetchall()
            return [json.loads(row["raw_json"]) for row in rows]

    def load_team_members(self, team_name: str) -> list[str]:
        with self._get_conn() as conn:
            rows = conn.execute("""
                SELECT traineeName
                FROM team_members
                WHERE teamName = ?
                ORDER BY CASE role WHEN 'leader' THEN 0 ELSE 1 END, rowid
            """, (team_name,)).fetchall()
            return [row["traineeName"] for row in rows]

    def load_current_user_team(self) -> dict | None:
        current_user = self.load_user_info()
        normalized_name = normalize_trainee_name(current_user.get("name") if current_user else "")
        if not normalized_name:
            return None
        with self._get_conn() as conn:
            row = conn.execute("""
                SELECT t.raw_json
                FROM team_members tm
                JOIN teams t ON t.id = tm.teamId
                WHERE tm.normalizedTraineeName = ?
                ORDER BY t.teamName ASC
                LIMIT 1
            """, (normalized_name,)).fetchone()
            if not row:
                return None
            team = json.loads(row["raw_json"])
            team["members"] = self.load_team_members(team.get("teamName", ""))
            return team

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
            conn.execute("DELETE FROM mentoring_participants")
            conn.execute("DELETE FROM mentoring_embedding_docs")
            conn.execute("DELETE FROM team_info")
            conn.execute("DELETE FROM teams")
            conn.execute("DELETE FROM team_members")
            conn.execute("DELETE FROM trainees")
            conn.execute("DELETE FROM sync_runs")
            conn.execute("DELETE FROM sync_item_results")
            conn.execute("DELETE FROM user_info")
            conn.execute("DELETE FROM chat_messages")
            conn.commit()

    # ── 사용자 기본 정보 CRUD ──
    def save_user_info(self, item: dict | None):
        with self._get_conn() as conn:
            conn.execute("DELETE FROM user_info")
            if item:
                quality = validate_user_info(item)
                normalized_name = normalize_trainee_name(item.get("name"))
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
                if normalized_name:
                    conn.execute("""
                        INSERT OR REPLACE INTO trainees (
                            normalizedName, name, email, role, source, raw_json
                        ) VALUES (?, ?, ?, ?, 'user_info', ?)
                    """, (
                        normalized_name,
                        item.get("name", ""),
                        item.get("email", ""),
                        item.get("role", "연수생"),
                        json.dumps(item, ensure_ascii=False),
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
                "teams": {
                    "total": conn.execute("SELECT COUNT(*) AS count FROM teams").fetchone()["count"] or 0,
                },
                "team_members": {
                    "total": conn.execute("SELECT COUNT(*) AS count FROM team_members").fetchone()["count"] or 0,
                },
                "mentoring_participants": {
                    "total": conn.execute("SELECT COUNT(*) AS count FROM mentoring_participants").fetchone()["count"] or 0,
                },
            }

    def load_user_info(self) -> dict | None:
        with self._get_conn() as conn:
            cursor = conn.execute("SELECT raw_json FROM user_info")
            row = cursor.fetchone()
            return json.loads(row["raw_json"]) if row else None

    def get_sync_run_stats(self) -> dict:
        with self._get_conn() as conn:
            row = conn.execute("""
                SELECT *
                FROM sync_runs
                WHERE id = 'latest'
            """).fetchone()
            if not row:
                return {
                    "status": "empty",
                    "list_count": 0,
                    "detail_success_count": 0,
                    "detail_fail_count": 0,
                    "participant_link_count": 0,
                    "vector_document_count": 0,
                }
            return {
                "status": row["status"],
                "started_at": row["startedAt"],
                "finished_at": row["finishedAt"],
                "list_count": row["listCount"] or 0,
                "detail_success_count": row["detailSuccessCount"] or 0,
                "detail_fail_count": row["detailFailCount"] or 0,
                "participant_link_count": row["participantLinkCount"] or 0,
                "vector_document_count": row["vectorDocumentCount"] or 0,
            }

    def update_vector_document_count(self, count: int):
        with self._get_conn() as conn:
            conn.execute("""
                UPDATE sync_runs
                SET vectorDocumentCount = ?
                WHERE id = 'latest'
            """, (count,))
            conn.commit()

# 싱글톤 인스턴스 노출
db = SomaDB()
