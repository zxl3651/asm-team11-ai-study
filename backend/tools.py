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
    from database import db
    db_items = db.load_mentorings()
    if db_items:
        return [_normalize_parsed_mentoring(item) for item in db_items]
    # Fallback to static JSON file if DB is empty
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


from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
import re
import os

def _get_solar_llm():
    return ChatOpenAI(
        model="solar-pro",
        api_key=os.environ.get("UPSTAGE_API_KEY", ""),
        base_url="https://api.upstage.ai/v1",
        temperature=0
    )

def analyze_query_for_search(user_query: str) -> dict:
    print(f"\n🔍 [RAG-STEP 1] Query Analysis 시작...")
    print(f"   └─ 사용자 자연어 질의: '{user_query}'")
    llm = _get_solar_llm()
    system_prompt = """사용자의 소마 특강/멘토링 검색용 입력(질문)을 분석하여 최적의 검색을 위해 정보를 추출하십시오.
반환 형식은 반드시 JSON 형태여야 하며, 다음 필드들을 포함해야 합니다:
{
  "search_query": "벡터 DB 검색에 적합하게 정리된 검색어 (예: 'Spring Boot 백엔드 멘토링')",
  "content_type": "mentoring 또는 lecture 또는 null",
  "keywords": ["핵심 기술/도메인 단어 목록", "예: ['Spring Boot', '백엔드']"]
}
JSON 외의 다른 텍스트는 응답에 포함하지 마십시오."""

    try:
        response = llm.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_query)
        ])
        text = response.content.strip()
        json_match = re.search(r"\{[\s\S]*\}", text)
        if json_match:
            res = json.loads(json_match.group(0))
            print(f"   └─ 분석 성공: search_query='{res.get('search_query')}', content_type='{res.get('content_type')}', keywords={res.get('keywords')}")
            return res
    except Exception as e:
        print(f"⚠️ [RAG-STEP 1] Query analysis failed: {str(e)}")
    return {
        "search_query": user_query,
        "content_type": None,
        "keywords": []
    }

def rerank_mentorings_with_llm(user_query: str, candidates: list[dict], limit: int = 5) -> list[dict]:
    if not candidates:
        return []
    
    print(f"\n🧠 [RAG-STEP 4] LLM Reranking 시작 (후보군 {len(candidates)}개)...")
    llm = _get_solar_llm()
    
    candidates_text = ""
    for idx, item in enumerate(candidates):
        candidates_text += f"""
[후보 {idx}]
ID: {item.get('id')}
구분: {item.get('type')}
제목: {item.get('title')}
멘토: {item.get('author')}
장소: {item.get('location')}
진행방식: {item.get('deliveryMethod')}
일정: {item.get('dateStr')} {item.get('timeRangeStr')}
남은 자리: {item.get('max_participants', 0) - item.get('current_participants', 0)}명
설명: {item.get('description', '')}
---
"""

    system_prompt = f"""사용자의 질문에 대해 가장 적절한 소마 멘토링/특강 후보들을 평가하여 최적의 추천 중요도 순서대로 정렬해 주십시오.
사용자 질문: "{user_query}"

응답 형식은 반드시 정렬된 후보 ID들의 JSON 리스트 형식이어야 합니다.
예시: ["123", "456", "789"]
결과에 해당 JSON 리스트 이외의 설명이나 다른 문구는 포함하지 마십시오."""

    try:
        response = llm.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=candidates_text)
        ])
        text = response.content.strip()
        json_match = re.search(r"\[[\s\S]*\]", text)
        if json_match:
            sorted_ids = json.loads(json_match.group(0))
            print(f"   └─ 리랭킹 순서 가공 완료: {sorted_ids[:limit]}")
            id_to_item = {str(item.get("id")): item for item in candidates}
            reranked = []
            for item_id in sorted_ids:
                item_id_str = str(item_id)
                if item_id_str in id_to_item:
                    reranked.append(id_to_item[item_id_str])
            seen_ids = set(str(item.get("id")) for item in reranked)
            for item in candidates:
                if str(item.get("id")) not in seen_ids:
                    reranked.append(item)
            return reranked[:limit]
    except Exception as e:
        print(f"⚠️ [RAG-STEP 4] LLM Reranking failed: {str(e)}")
    return candidates[:limit]

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
    
    analyzed_query = None
    search_query = query
    if query:
        analyzed_query = analyze_query_for_search(query)
        search_query = analyzed_query.get("search_query", query)
        if analyzed_query.get("content_type"):
            content_type = analyzed_query.get("content_type")

    vector_results = []
    if search_query:
        print(f"\n⚡ [RAG-STEP 2] ChromaDB 벡터 검색 수행...")
        print(f"   └─ 검색어: '{search_query}'")
        from vector_store import search_vector_mentorings
        vector_results = search_vector_mentorings(search_query, n_results=20)
        print(f"   └─ 벡터 매칭 완료 (ChromaDB 결과 {len(vector_results)}건 반환)")
    else:
        print("\n⚡ [RAG-STEP 2] 검색어가 제공되지 않아 벡터 검색을 건너뜁니다.")

    print(f"\n🎯 [RAG-STEP 3] SQLite 하이브리드 필터링 및 가중치 합산 시작...")
    results = []
    vector_ids = {res["id"]: res for res in vector_results}
    
    for item in items:
        item_id = str(item.get("id", ""))
        
        item_status = item.get("status", "")
        if status and item_status != status:
            continue

        if content_type and content_type in ("mentoring", "lecture"):
            if item.get("type") != content_type:
                continue

        score = 0
        is_vector_match = item_id in vector_ids
        if is_vector_match:
            distance = vector_ids[item_id].get("distance")
            similarity = max(0.0, 2.0 - (distance or 1.0))
            score += similarity * 10
        elif search_query:
            q_lower = search_query.lower()
            title_match = q_lower in item.get("title", "").lower()
            author_match = q_lower in item.get("author", "").lower()
            desc_match = q_lower in item.get("description", "").lower()
            if title_match or author_match or desc_match:
                score += 3
                
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

        if search_query or domains or stacks or goals:
            if score > 0:
                results.append({**item, "_score": score})
        else:
            results.append({**item, "_score": 0})

    results.sort(key=lambda x: x["_score"], reverse=True)
    for r in results:
        r.pop("_score", None)

    print(f"   └─ 필터링 및 점수화 완료: 전체 {len(results)}건 매칭")

    if query and results:
        candidates = results[:15]
        results = rerank_mentorings_with_llm(query, candidates, limit=5)
        
    spots_info = []
    for r in results:
        max_p = r.get("max_participants", 0) or 0
        cur_p = r.get("current_participants", 0) or 0
        spots_info.append({
            **r,
            "remaining_spots": max_p - cur_p,
        })

    print(f"🏆 [RAG-STEP 5] 최종 최적 추천 리스트 {len(spots_info)}건 도출 완료")
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
    from database import db
    return db.load_user_calendar()

def _load_team_info() -> list[dict]:
    from database import db
    return db.load_team_info()

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

