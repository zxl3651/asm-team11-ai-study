import json
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
REALTIME_MENTORINGS_FILE = DATA_DIR / "mentorings_realtime.json"

def _load_mentors() -> list[dict]:
    with open(DATA_DIR / "mentors.json", encoding="utf-8") as f:
        return json.load(f)

def _normalize_parsed_mentoring(item: dict) -> dict:
    """Content Script에서 파싱된 멘토링 데이터를 에이전트 도구 호환 구조로 정규화."""
    normalized = {
        "id": item.get("id", ""),
        "type": item.get("type", "lecture"),
        "title": item.get("title", ""),
        "url": item.get("url", ""),
        "status": item.get("status", "알수없음"),
        "author": item.get("author", ""),
        "dateStr": item.get("dateStr", ""),
        "timeRangeStr": item.get("timeRangeStr", ""),
        "registrationPeriod": item.get("registrationPeriod", ""),
        "registeredDate": item.get("registeredDate", ""),
        "isApproved": item.get("isApproved", False),
        # 파싱 데이터에는 이 필드들이 없을 수 있으므로 fallback
        "mentor_name": item.get("mentor_name", item.get("author", "")),
        "domain": item.get("domain", ""),
        "stacks": item.get("stacks", []),
        "goals": item.get("goals", []),
        "description": item.get("description", item.get("title", "")),
        "max_participants": item.get("max_participants", item.get("maxParticipants", 0)),
        "current_participants": item.get("current_participants", item.get("currentParticipants", 0)),
        "deadline": item.get("deadline", ""),
        "schedule": item.get("schedule", f"{item.get('dateStr', '')} {item.get('timeRangeStr', '')}"),
        # 신규 크롤링 연동 상세 정보
        "location": item.get("location", ""),
        "deliveryMethod": item.get("deliveryMethod", ""),
        "isOnline": item.get("isOnline", True if item.get("isOnline") is None else item.get("isOnline")),
    }
    return normalized


def _load_mentorings() -> list[dict]:
    if REALTIME_MENTORINGS_FILE.exists():
        try:
            with open(REALTIME_MENTORINGS_FILE, encoding="utf-8") as f:
                raw = json.load(f)
                return [_normalize_parsed_mentoring(item) for item in raw]
        except Exception:
            pass
    with open(DATA_DIR / "mentorings.json", encoding="utf-8") as f:
        return json.load(f)



def search_mentors(
    stacks: list[str] | None = None,
    goals: list[str] | None = None,
    domains: list[str] | None = None,
    available_only: bool = True,
) -> dict:
    """멘토를 조건에 맞게 검색하여 반환합니다."""
    mentors = _load_mentors()
    results = []

    for m in mentors:
        if available_only and not m.get("available", True):
            continue

        score = 0

        if stacks:
            mentor_stacks_lower = [s.lower() for s in m.get("stacks", [])]
            matched = [s for s in stacks if s.lower() in mentor_stacks_lower]
            if matched:
                score += len(matched) * 3

        if goals:
            mentor_goals = m.get("goals", [])
            matched = [g for g in goals if g in mentor_goals]
            if matched:
                score += len(matched) * 2

        if domains:
            mentor_domains_lower = [d.lower() for d in m.get("domains", [])]
            matched = [d for d in domains if d.lower() in mentor_domains_lower]
            if matched:
                score += len(matched) * 2

        if stacks or goals or domains:
            if score > 0:
                results.append({**m, "_score": score})
        else:
            results.append({**m, "_score": 0})

    results.sort(key=lambda x: x["_score"], reverse=True)
    for r in results:
        r.pop("_score", None)

    return {
        "total": len(results),
        "mentors": results[:10],
    }


def search_mentorings(
    content_type: str | None = None,
    domains: list[str] | None = None,
    stacks: list[str] | None = None,
    goals: list[str] | None = None,
    status: str = "접수중",
    query: str | None = None,
) -> dict:
    """멘토링 및 특강을 조건에 맞게 검색합니다."""
    items = _load_mentorings()
    results = []

    for item in items:
        item_status = item.get("status", "")
        if status and item_status != status:
            continue

        if content_type and content_type in ("mentoring", "lecture"):
            if item.get("type") != content_type:
                continue

        # query 검색어 필터 (제목, ID, 작성자, 장소, 설명 매칭)
        if query:
            q_lower = query.lower()
            title_match = q_lower in item.get("title", "").lower()
            id_match = q_lower == str(item.get("id", ""))
            author_match = q_lower in item.get("author", "").lower()
            desc_match = q_lower in item.get("description", "").lower()
            loc_match = q_lower in item.get("location", "").lower()
            
            if not (title_match or id_match or author_match or desc_match or loc_match):
                continue

        score = 0

        if domains:
            item_domain = item.get("domain", "").lower()
            item_title = item.get("title", "").lower()
            item_desc = item.get("description", "").lower()
            matched = [d for d in domains if d.lower() in item_domain or d.lower() in item_title or d.lower() in item_desc]
            if matched:
                score += len(matched) * 3

        if stacks:
            item_stacks_lower = [s.lower() for s in item.get("stacks", [])]
            item_title = item.get("title", "").lower()
            item_desc = item.get("description", "").lower()
            matched = [s for s in stacks if s.lower() in item_stacks_lower or s.lower() in item_title or s.lower() in item_desc]
            if matched:
                score += len(matched) * 2

        if goals:
            item_goals = item.get("goals", [])
            item_title = item.get("title", "").lower()
            item_desc = item.get("description", "").lower()
            matched = [g for g in goals if g in item_goals or g in item_title or g in item_desc]
            if matched:
                score += len(matched)

        if domains or stacks or goals:
            if score > 0:
                results.append({**item, "_score": score})
        else:
            results.append({**item, "_score": 0})

    results.sort(key=lambda x: x["_score"], reverse=True)
    for r in results:
        r.pop("_score", None)

    spots_info = []
    for r in results:
        max_p = r.get("max_participants", 0) or 0
        cur_p = r.get("current_participants", 0) or 0
        spots_info.append({
            **r,
            "remaining_spots": max_p - cur_p,
        })

    return {
        "total": len(spots_info),
        "items": spots_info,
    }


def _load_trainees() -> list[dict]:
    with open(DATA_DIR / "trainees.json", encoding="utf-8") as f:
        return json.load(f)


def search_trainees(
    roles: list[str] | None = None,
    stacks: list[str] | None = None,
    team_status: str | None = None,
) -> dict:
    """연수생을 역할/기술스택/팀 여부로 검색합니다."""
    trainees = _load_trainees()
    results = []

    for t in trainees:
        if team_status and t.get("team_status") != team_status:
            continue

        score = 0

        if roles:
            trainee_roles_lower = [r.lower() for r in t.get("roles", [])]
            matched = [r for r in roles if r.lower() in trainee_roles_lower]
            if matched:
                score += len(matched) * 3

        if stacks:
            trainee_stacks_lower = [s.lower() for s in t.get("stacks", [])]
            matched = [s for s in stacks if s.lower() in trainee_stacks_lower]
            if matched:
                score += len(matched) * 2

        if roles or stacks:
            if score > 0:
                results.append({**t, "_score": score})
        else:
            results.append({**t, "_score": 0})

    results.sort(key=lambda x: x["_score"], reverse=True)
    for r in results:
        r.pop("_score", None)

    return {"total": len(results), "trainees": results[:20]}


# 유저 일정 조회 목업 데이터 파일
USER_CALENDAR_FILE = DATA_DIR / "user_calendar.json"
TEAM_INFO_FILE = DATA_DIR / "team_info.json"

def _load_user_calendar() -> list[dict]:
    if USER_CALENDAR_FILE.exists():
        with open(USER_CALENDAR_FILE, encoding="utf-8") as f:
            return json.load(f)
    return []

def _load_team_info() -> list[dict]:
    if TEAM_INFO_FILE.exists():
        with open(TEAM_INFO_FILE, encoding="utf-8") as f:
            return json.load(f)
    return []

# LangChain Structured Tools 정의
from langchain_core.tools import tool
from pydantic import BaseModel, Field

class MentorSearchInput(BaseModel):
    stacks: list[str] | None = Field(default=None, description="검색할 기술 스택 목록. 예: ['Spring', 'Java', 'AWS']")
    goals: list[str] | None = Field(default=None, description="목표 목록. '취업' 또는 '창업' 중 선택.")
    domains: list[str] | None = Field(default=None, description="관심 분야 목록. 예: ['클라우드', '대규모 트래픽', '스타트업']")
    available_only: bool = Field(default=True, description="현재 멘토링 가능한 멘토만 검색할지 여부.")

@tool("search_mentors", args_schema=MentorSearchInput)
def search_mentors_tool(
    stacks: list[str] | None = None,
    goals: list[str] | None = None,
    domains: list[str] | None = None,
    available_only: bool = True,
) -> str:
    """소마 멘토를 기술 스택, 멘토링 목표(취업/창업), 전문 분야(도메인) 조건에 맞게 검색하여 반환합니다."""
    result = search_mentors(stacks=stacks, goals=goals, domains=domains, available_only=available_only)
    return json.dumps(result, ensure_ascii=False, indent=2)


class MentoringSearchInput(BaseModel):
    content_type: str | None = Field(default=None, description="콘텐츠 유형. 'mentoring'(멘토링) 또는 'lecture'(특강) 중 하나.")
    domains: list[str] | None = Field(default=None, description="관심 분야 목록. 예: ['클라우드', '백엔드', 'ML/AI']")
    stacks: list[str] | None = Field(default=None, description="기술 스택 목록. 예: ['Python', 'AWS']")
    goals: list[str] | None = Field(default=None, description="목표 목록. '취업' 또는 '창업'")
    status: str = Field(default="접수중", description="접수 상태 필터. '접수중', '마감', '전체' 중 하나.")
    query: str | None = Field(default=None, description="특정 검색어 필터 (예: 특정 ID '9944' 혹은 제목 키워드)")

@tool("search_mentorings", args_schema=MentoringSearchInput)
def search_mentorings_tool(
    content_type: str | None = None,
    domains: list[str] | None = None,
    stacks: list[str] | None = None,
    goals: list[str] | None = None,
    status: str = "접수중",
    query: str | None = None,
) -> str:
    """소마 멘토링과 특강 스케줄을 조건에 맞게 검색하여 반환합니다. 남은 자리와 접수 상태 필터가 포함되어 있습니다."""
    status_filter = status if status != "전체" else None
    result = search_mentorings(
        content_type=content_type,
        domains=domains,
        stacks=stacks,
        goals=goals,
        status=status_filter,
        query=query,
    )
    return json.dumps(result, ensure_ascii=False, indent=2)


class TraineeSearchInput(BaseModel):
    roles: list[str] | None = Field(default=None, description="찾는 역할 목록. 예: ['백엔드', 'AI', '프론트엔드', '기획', '풀스택']")
    stacks: list[str] | None = Field(default=None, description="기술 스택 목록. 예: ['Python', 'React', 'Spring Boot']")
    team_status: str | None = Field(default=None, description="팀 빌딩 여부 필터. '팀없음'(팀원 모집 중) 또는 '팀있음' 중 선택.")

@tool("search_trainees", args_schema=TraineeSearchInput)
def search_trainees_tool(
    roles: list[str] | None = None,
    stacks: list[str] | None = None,
    team_status: str | None = None,
) -> str:
    """소마 연수생 목록을 역할, 스택, 팀 빌딩 여부 기준으로 검색하여 반환합니다."""
    result = search_trainees(roles=roles, stacks=stacks, team_status=team_status)
    return json.dumps(result, ensure_ascii=False, indent=2)


@tool("get_user_calendar")
def get_user_calendar_tool() -> str:
    """현재 로그인한 연수생의 개인 시간표(접수 완료된 특강 및 멘토링 일정) 목록을 반환합니다.
    일정이 겹치는지 분석할 때 이 캘린더 데이터를 참조하세요."""
    calendar = _load_user_calendar()
    # 취소 또는 반려된 일정은 캘린더 충돌 분석 대상에서 제외
    active_calendar = [
        item for item in calendar
        if "취소" not in item.get("status", "") and "반려" not in item.get("status", "")
    ]
    result = {
        "total_active": len(active_calendar),
        "total_including_cancelled": len(calendar),
        "calendar": active_calendar
    }
    return json.dumps(result, ensure_ascii=False, indent=2)


@tool("get_team_info")
def get_team_info_tool() -> str:
    """현재 로그인한 연수생의 소속 팀 매칭 정보(팀명, 팀장, 팀원 목록, 멘토명, 프로젝트명 등)를 반환합니다.
    사용자의 팀명, 팀원, 전담 멘토, 프로젝트 개발 기술 스택이나 도메인 등의 정보를 물어볼 때 이 툴을 호출하여 참조하세요."""
    team_info = _load_team_info()
    result = {
        "total": len(team_info),
        "team_info": team_info
    }
    return json.dumps(result, ensure_ascii=False, indent=2)


# LangChain 에이전트용 통합 툴 리스트
LATEST_TOOLS = [
    search_mentors_tool,
    search_mentorings_tool,
    search_trainees_tool,
    get_user_calendar_tool,
    get_team_info_tool,
]

