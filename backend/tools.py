import json
from pathlib import Path
import contextvars

DATA_DIR = Path(__file__).parent / "data"
REALTIME_MENTORINGS_FILE = DATA_DIR / "mentorings_realtime.json"

# 실시간 상태 전송용 ContextVar
status_callback_var = contextvars.ContextVar("status_callback", default=None)

def report_status(message: str):
    callback = status_callback_var.get()
    if callback:
        try:
            callback(message)
        except Exception:
            pass

def _load_mentors() -> list[dict]:
    path = DATA_DIR / "mentors.json"
    if not path.exists():
        report_status("멘토 원본 데이터가 아직 수집되지 않았어요.")
        return []
    with open(path, encoding="utf-8") as f:
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
        # canonical / validation fields from SQLite validation layer
        "startAt": item.get("startAt", ""),
        "endAt": item.get("endAt", ""),
        "qualityStatus": item.get("qualityStatus", "valid"),
        "validationErrors": item.get("validationErrors", []),
        "validationWarnings": item.get("validationWarnings", []),
        "canonicalText": item.get("canonicalText", ""),
    }
    return normalized


def _load_mentorings() -> list[dict]:
    from database import db
    db_items = db.load_mentorings()
    if db_items:
        return [_normalize_parsed_mentoring(item) for item in db_items]
    # Fallback to static JSON file if DB is empty
    path = DATA_DIR / "mentorings.json"
    if not path.exists():
        report_status("멘토링/특강 원본 데이터가 아직 수집되지 않았어요.")
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f)



def search_mentors(
    stacks: list[str] | None = None,
    goals: list[str] | None = None,
    domains: list[str] | None = None,
    available_only: bool = True,
) -> dict:
    """멘토를 조건에 맞게 검색하여 반환합니다."""
    mentors = _load_mentors()
    report_status(f"멘토 {len(mentors)}명을 불러왔어요...")
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

    report_status(f"조건에 맞는 멘토 {len(results)}명을 추렸어요...")
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
        model="solar-pro3",
        api_key=os.environ.get("UPSTAGE_API_KEY", ""),
        base_url="https://api.upstage.ai/v1",
        temperature=0
    )

def analyze_query_for_search(user_query: str) -> dict:
    report_status("검색 의도를 정리하고 있어요...")
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
            keywords = res.get('keywords', [])
            report_status(f"검색 키워드를 뽑았어요: {', '.join(keywords) if keywords else res.get('search_query')}")
            print(f"   └─ 분석 성공: search_query='{res.get('search_query')}', content_type='{res.get('content_type')}', keywords={res.get('keywords')}")
            return res
    except Exception as e:
        print(f"⚠️ [RAG-STEP 1] Query analysis failed: {str(e)}")
    report_status("검색 의도를 원문 기준으로 처리하고 있어요...")
    return {
        "search_query": user_query,
        "content_type": None,
        "keywords": []
    }

def rerank_mentorings_with_llm(user_query: str, candidates: list[dict], limit: int = 5) -> list[dict]:
    if not candidates:
        return []
    
    report_status(f"후보 {len(candidates)}건의 관련도를 비교하고 있어요...")
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
            report_status(f"추천 우선순위 {min(limit, len(sorted_ids))}건을 정리했어요...")
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
    report_status("기본 점수 기준으로 추천 순서를 정리하고 있어요...")
    return candidates[:limit]

def _match_date(date_query: str, item: dict) -> bool:
    if not date_query:
        return True
    dq = date_query.replace(" ", "").replace("-", "").replace("/", "").lower()
    date_str = item.get("dateStr", "").replace(" ", "").replace("-", "").replace("/", "").lower()
    start_at = item.get("startAt", "").replace(" ", "").replace("-", "").replace("t", "").replace(":", "").lower()
    
    if dq in date_str or dq in start_at:
        return True
        
    import re
    match = re.search(r"(\d{1,2})[월/.]+(\d{1,2})일?", date_query)
    if match:
        m, d = int(match.group(1)), int(match.group(2))
        m_str_1 = f"{m:02d}{d:02d}"
        m_str_2 = f"{m}월{d}일"
        if m_str_1 in date_str or m_str_1 in start_at or m_str_2 in date_str:
            return True
            
    ymd_match = re.search(r"(20\d{2})[년/.-]*(\d{1,2})[월/.-]*(\d{1,2})", date_query)
    if ymd_match:
        y, m, d = ymd_match.group(1), int(ymd_match.group(2)), int(ymd_match.group(3))
        target_iso = f"{y}-{m:02d}-{d:02d}"
        if target_iso in item.get("startAt", "") or target_iso in item.get("dateStr", ""):
            return True
            
    return False

def search_mentorings(
    content_type: str | None = None,
    domains: list[str] | None = None,
    stacks: list[str] | None = None,
    goals: list[str] | None = None,
    status: str | None = None,
    query: str | None = None,
    date_query: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict:
    """멘토링 및 특강을 조건에 맞게 검색합니다."""
    items = [item for item in _load_mentorings() if item.get("qualityStatus", "valid") != "invalid"]
    
    # ─── 신청 가능한 후보 추천일 때만 과거 일정 및 이미 등록된 일정 필터링 ───
    if status == "접수중":
        from datetime import datetime
        
        now_dt = datetime.now()
        current_user = _get_current_user_name()
        user_cal = _mentoring_registration_events_for_user(current_user)
        registered_ids = {str(c.get("id")) for c in user_cal if c.get("qualityStatus", "valid") != "invalid" and "취소" not in c.get("status", "") and "반려" not in c.get("status", "")}
        registered_titles = {c.get("title") for c in user_cal if c.get("qualityStatus", "valid") != "invalid" and "취소" not in c.get("status", "") and "반려" not in c.get("status", "")}
        
        filtered_items = []
        for item in items:
            start_at_str = item.get("startAt")
            if start_at_str:
                try:
                    start_dt = datetime.fromisoformat(start_at_str)
                    if start_dt < now_dt:
                        continue
                except Exception:
                    pass
            item_id = str(item.get("id", ""))
            item_title = item.get("title", "")
            if item_id in registered_ids or item_title in registered_titles:
                continue
            filtered_items.append(item)
        items = filtered_items

    report_status(f"멘토링/특강 {len(items)}건을 불러왔어요...")
    
    analyzed_query = None
    search_query = query
    if query:
        analyzed_query = analyze_query_for_search(query)
        search_query = analyzed_query.get("search_query", query)
        if analyzed_query.get("content_type"):
            content_type = analyzed_query.get("content_type")

    vector_results = []
    if search_query:
        report_status("비슷한 특강과 멘토링을 의미 기반으로 찾고 있어요...")
        print(f"\n⚡ [RAG-STEP 2] ChromaDB 벡터 검색 수행...")
        print(f"   └─ 검색어: '{search_query}'")
        from vector_store import search_vector_mentorings
        vector_results = search_vector_mentorings(search_query, n_results=20)
        report_status(f"의미가 가까운 후보 {len(vector_results)}건을 찾았어요...")
        print(f"   └─ 벡터 매칭 완료 (ChromaDB 결과 {len(vector_results)}건 반환)")
    else:
        print("\n⚡ [RAG-STEP 2] 검색어가 제공되지 않아 벡터 검색을 건너뜁니다.")

    report_status(f"후보 {len(items)}건을 조건에 맞게 걸러보고 있어요...")
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

        # 명시적인 날짜 필터 적용
        if date_query and not _match_date(date_query, item):
            continue

        # 날짜 범위 필터 적용 (start_date, end_date)
        if start_date or end_date:
            item_date = item.get("startAt", "")
            if not item_date and item.get("dateStr"):
                from data_validation import parse_date
                item_date = parse_date(item.get("dateStr"))
            if item_date:
                day_str = item_date.split("T")[0]
                if start_date and day_str < start_date:
                    continue
                if end_date and day_str > end_date:
                    continue
            else:
                # 날짜 파싱이 안 되는 건은 범위 필터 적용 시 필터링 처리
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
            searchable_text = item.get("canonicalText") or item.get("description", "")
            desc_match = q_lower in searchable_text.lower()
            
            # 날짜 매칭 여부 확인
            date_match = (
                q_lower in item.get("dateStr", "").lower() 
                or q_lower in item.get("startAt", "").lower()
                or _match_date(search_query, item)
            )
            
            if title_match or author_match or desc_match or date_match:
                score += 5 if date_match else 3
                
        if domains:
            item_domain = item.get("domain", "").lower()
            item_title = item.get("title", "").lower()
            item_desc = (item.get("canonicalText") or item.get("description", "")).lower()
            matched = [d for d in domains if d.lower() in item_domain or d.lower() in item_title or d.lower() in item_desc]
            if matched:
                score += len(matched) * 3

        if stacks:
            item_stacks_lower = [s.lower() for s in item.get("stacks", [])]
            item_title = item.get("title", "").lower()
            item_desc = (item.get("canonicalText") or item.get("description", "")).lower()
            matched = [s for s in stacks if s.lower() in item_stacks_lower or s.lower() in item_title or s.lower() in item_desc]
            if matched:
                score += len(matched) * 2

        if goals:
            item_goals = item.get("goals", [])
            item_title = item.get("title", "").lower()
            item_desc = (item.get("canonicalText") or item.get("description", "")).lower()
            matched = [g for g in goals if g in item_goals or g in item_title or g in item_desc]
            if matched:
                score += len(matched)

        if search_query or domains or stacks or goals or date_query:
            if score > 0 or date_query:  # date_query로 필터된 건은 score가 0이라도 결과에 포함
                results.append({**item, "_score": score})
        else:
            results.append({**item, "_score": 0})

    results.sort(key=lambda x: x["_score"], reverse=True)
    for r in results:
        r.pop("_score", None)

    report_status(f"조건에 맞는 후보 {len(results)}건을 추렸어요...")
    print(f"   └─ 필터링 및 점수화 완료: 전체 {len(results)}건 매칭")

    # 폴백: '접수중' + 요청 날짜범위에서 0건이면 해당 기간엔 신청 가능한 항목이 없는 것이다.
    # (예: 오늘이 주말이라 '이번 주'에 남은 접수중 특강이 없음)
    # 그냥 0건으로 끝내지 말고, 날짜범위를 풀어 다가오는 접수중 특강을 가까운 순으로 추천한다.
    if not results and status == "접수중" and (start_date or end_date):
        report_status("이번 기간엔 접수중 항목이 없어 다가오는 접수중 특강으로 넓혀보고 있어요...")
        fallback = search_mentorings(
            content_type=content_type,
            domains=domains,
            stacks=stacks,
            goals=goals,
            status=status,
            query=query,
            date_query=None,
            start_date=None,
            end_date=None,
        )
        fb_items = fallback.get("items", [])
        fb_items.sort(key=lambda x: (x.get("startAt") or "9999"))
        fb_items = fb_items[:15]
        return {
            "total": len(fb_items),
            "items": fb_items,
            "date_range_relaxed": True,
            "requested_range": {"start_date": start_date, "end_date": end_date},
            "note": (
                "요청한 기간에는 접수중(신청 가능) 특강/멘토링이 없어, "
                "다가오는 접수중 항목을 가까운 일정 순으로 확장해 제시합니다. "
                "답변에서 요청 기간엔 신청 가능한 항목이 없었다는 점을 먼저 안내하세요."
            ),
        }

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
            "schedule_quality": r.get("qualityStatus", "valid"),
        })

    print(f"🏆 [RAG-STEP 5] 최종 최적 추천 리스트 {len(spots_info)}건 도출 완료")
    return {
        "total": len(spots_info),
        "items": spots_info,
    }


def _load_trainees() -> list[dict]:
    path = DATA_DIR / "trainees.json"
    if not path.exists():
        report_status("연수생 원본 데이터가 아직 수집되지 않았어요.")
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def search_trainees(
    name: str | None = None,
    roles: list[str] | None = None,
    stacks: list[str] | None = None,
    team_status: str | None = None,
) -> dict:
    """연수생을 이름/역할/기술스택/팀 여부로 검색합니다."""
    trainees = _load_trainees()
    results = []
    name_query = "".join(str(name or "").split()).lower()

    for t in trainees:
        trainee_name_key = "".join(str(t.get("name", "")).split()).lower()
        if name_query and name_query not in trainee_name_key:
            continue

        if team_status and t.get("team_status") != team_status:
            continue

        score = 0
        if name_query:
            score += 10 if trainee_name_key == name_query else 5

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

        if name_query or roles or stacks:
            if score > 0:
                results.append({**t, "_score": score})
        else:
            results.append({**t, "_score": 0})

    results.sort(key=lambda x: x["_score"], reverse=True)
    for r in results:
        r.pop("_score", None)

    return {"total": len(results), "trainees": results[:20]}


USER_CALENDAR_FILE = DATA_DIR / "user_calendar.json"
TEAM_INFO_FILE = DATA_DIR / "team_info.json"

def _get_current_user_name() -> str | None:
    from database import db
    user_info = db.load_user_info()
    return user_info.get("name") if user_info else None

def _calendar_owner_for_query(user_name: str | None) -> str | None:
    if not user_name or user_name == "me":
        return _get_current_user_name()
    return user_name

def _participant_names_from_mentoring(item: dict) -> list[str]:
    from database import clean_participant_names
    return clean_participant_names(item)

def _mentoring_registration_events_for_user(owner_name: str | None) -> list[dict]:
    if not owner_name:
        return []
    from database import db
    return [
        item for item in db.load_participant_registrations(owner_name)
        if item.get("startAt") and item.get("endAt")
    ]

def _has_calendar_access(user_name: str | None) -> bool:
    from database import db
    # 상세 페이지에서 파싱된 participantNames 연결이 있어야 참여자별 신청 일정을 조회할 수 있습니다.
    stats = db.get_participant_registration_stats()
    return int(stats.get("registration_link_count", 0) or 0) > 0

def _load_calendar_for_user(user_name: str | None) -> list[dict]:
    owner_name = _calendar_owner_for_query(user_name)
    mentoring_events = _mentoring_registration_events_for_user(owner_name)
    return mentoring_events

def _load_user_calendar() -> list[dict]:
    return _load_calendar_for_user(None)

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
    status: str = Field(default="전체", description="접수 상태 필터. '접수중', '마감', '전체' 중 하나.")
    query: str | None = Field(default=None, description="특정 검색어 필터 (예: 특정 ID '9944' 혹은 제목 키워드)")
    date_query: str | None = Field(default=None, description="특정 날짜 필터 (예: '2026-06-06' 혹은 '6월 6일')")
    start_date: str | None = Field(default=None, description="조회 시작 날짜 (ISO 형식, 예: '2026-06-01')")
    end_date: str | None = Field(default=None, description="조회 종료 날짜 (ISO 형식, 예: '2026-06-07')")

@tool("search_mentorings", args_schema=MentoringSearchInput)
def search_mentorings_tool(
    content_type: str | None = None,
    domains: list[str] | None = None,
    stacks: list[str] | None = None,
    goals: list[str] | None = None,
    status: str = "전체",
    query: str | None = None,
    date_query: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
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
        date_query=date_query,
        start_date=start_date,
        end_date=end_date,
    )
    return json.dumps(result, ensure_ascii=False, indent=2)


class TraineeSearchInput(BaseModel):
    name: str | None = Field(default=None, description="조회할 연수생 이름. 예: '김민수'")
    roles: list[str] | None = Field(default=None, description="찾는 역할 목록. 예: ['백엔드', 'AI', '프론트엔드', '기획', '풀스택']")
    stacks: list[str] | None = Field(default=None, description="기술 스택 목록. 예: ['Python', 'React', 'Spring Boot']")
    team_status: str | None = Field(default=None, description="팀 빌딩 여부 필터. '팀없음'(팀원 모집 중) 또는 '팀있음' 중 선택.")

@tool("search_trainees", args_schema=TraineeSearchInput)
def search_trainees_tool(
    name: str | None = None,
    roles: list[str] | None = None,
    stacks: list[str] | None = None,
    team_status: str | None = None,
) -> str:
    """소마 연수생 목록을 이름, 역할, 스택, 팀 빌딩 여부 기준으로 검색하여 반환합니다."""
    result = search_trainees(name=name, roles=roles, stacks=stacks, team_status=team_status)
    return json.dumps(result, ensure_ascii=False, indent=2)


class CalendarSearchInput(BaseModel):
    start_date: str | None = Field(default=None, description="조회 시작 날짜 (ISO 형식, 예: '2026-06-01')")
    end_date: str | None = Field(default=None, description="조회 종료 날짜 (ISO 형식, 예: '2026-06-07')")
    user_name: str | None = Field(default=None, description="조회할 연수생의 이름 (기본값은 로그인된 본인)")


class ParticipantRegistrationInput(BaseModel):
    participant_name: str | None = Field(default=None, description="조회할 참여자 이름. 생략하면 로그인된 본인")
    start_date: str | None = Field(default=None, description="조회 시작 날짜 (ISO 형식, 예: '2026-06-01')")
    end_date: str | None = Field(default=None, description="조회 종료 날짜 (ISO 형식, 예: '2026-06-07')")


class TeamParticipantScheduleInput(BaseModel):
    team_name: str | None = Field(default=None, description="조회할 팀명. 생략하면 로그인 사용자의 팀을 사용")
    user_names: list[str] | None = Field(default=None, description="직접 지정할 팀원 이름 목록")
    start_date: str | None = Field(default=None, description="조회 시작 날짜 (ISO 형식, 예: '2026-06-01')")
    end_date: str | None = Field(default=None, description="조회 종료 날짜 (ISO 형식, 예: '2026-06-07')")


class VectorMentoringSearchInput(BaseModel):
    query: str = Field(description="의미 검색에 사용할 자연어 질의")
    n_results: int = Field(default=15, description="반환할 벡터 검색 후보 수")


def _filter_registration_events(
    events: list[dict],
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[dict]:
    if not start_date and not end_date:
        return events
    filtered = []
    for item in events:
        item_date = item.get("startAt", "")
        if not item_date and item.get("dateStr"):
            from data_validation import parse_date
            item_date = parse_date(item.get("dateStr"))
        if item_date:
            day_str = item_date.split("T")[0]
            if start_date and day_str < start_date:
                continue
            if end_date and day_str > end_date:
                continue
        filtered.append(item)
    return filtered


@tool("get_participant_registrations", args_schema=ParticipantRegistrationInput)
def get_participant_registrations_tool(
    participant_name: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> str:
    """멘토링/특강 상세에서 파싱한 신청자 명단(participantNames)을 기준으로 특정 참여자가 신청한 특강/멘토링 목록을 반환합니다."""
    owner_name = _get_current_user_name() if not participant_name or participant_name == "me" else participant_name
    report_status(f"{owner_name or '참여자'} 신청 특강/멘토링을 확인하고 있어요...")
    events = _filter_registration_events(
        _mentoring_registration_events_for_user(owner_name),
        start_date=start_date,
        end_date=end_date,
    )
    active_events = [
        item for item in events
        if item.get("qualityStatus", "valid") != "invalid"
        and "취소" not in item.get("status", "")
        and "반려" not in item.get("status", "")
    ]
    result = {
        "participant_name": owner_name,
        "data_source": "mentoring_detail_participant_names",
        "data_available": bool(owner_name),
        "total_active": len(active_events),
        "registrations": active_events,
    }
    if not active_events:
        result["warning"] = "멘토링/특강 상세 신청자 명단에서 해당 참여자의 신청 내역을 찾지 못했습니다."
    return json.dumps(result, ensure_ascii=False, indent=2)


@tool("get_team_participant_schedule", args_schema=TeamParticipantScheduleInput)
def get_team_participant_schedule_tool(
    team_name: str | None = None,
    user_names: list[str] | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> str:
    """팀원별 멘토링/특강 신청 일정을 정규화된 참여자 연결 테이블 기준으로 조회합니다."""
    from database import db

    resolved_team = None
    members = [name for name in (user_names or []) if str(name or "").strip()]
    if not members:
        if team_name:
            members = db.load_team_members(team_name)
            resolved_team = next((team for team in db.load_team_info() if team.get("teamName") == team_name), None)
        else:
            resolved_team = db.load_current_user_team()
            if resolved_team:
                team_name = resolved_team.get("teamName")
                members = resolved_team.get("members") or db.load_team_members(team_name)

    report_status(f"{team_name or '팀'} 팀원별 신청 일정을 확인하고 있어요...")
    by_member = {}
    busy_events = []
    for member in members:
        events = _filter_registration_events(
            _mentoring_registration_events_for_user(member),
            start_date=start_date,
            end_date=end_date,
        )
        active_events = [
            item for item in events
            if item.get("qualityStatus", "valid") != "invalid"
            and "취소" not in item.get("status", "")
            and "반려" not in item.get("status", "")
        ]
        by_member[member] = active_events
        for item in active_events:
            busy_events.append({
                "participantName": member,
                "mentoringId": item.get("mentoringId") or item.get("id"),
                "title": item.get("title", ""),
                "startAt": item.get("startAt"),
                "endAt": item.get("endAt"),
                "status": item.get("status", ""),
                "source": "mentoring_detail_participant_names",
            })

    return json.dumps({
        "team_name": team_name,
        "members": members,
        "data_source": "normalized_mentoring_participants",
        "member_count": len(members),
        "total_busy_events": len(busy_events),
        "by_member": by_member,
        "busy_events": busy_events,
    }, ensure_ascii=False, indent=2)


@tool("vector_search_mentorings", args_schema=VectorMentoringSearchInput)
def vector_search_mentorings_tool(query: str, n_results: int = 15) -> str:
    """ChromaDB 벡터 스토어에서 자연어 질의와 의미적으로 가까운 멘토링/특강 후보를 조회합니다."""
    report_status("벡터 스토어에서 의미 기반 후보를 조회하고 있어요...")
    from vector_store import search_vector_mentorings
    results = search_vector_mentorings(query, n_results=n_results)
    return json.dumps({
        "query": query,
        "data_source": "chroma_vector_store",
        "total": len(results),
        "items": results,
    }, ensure_ascii=False, indent=2)

@tool("get_user_calendar", args_schema=CalendarSearchInput)
def get_user_calendar_tool(
    start_date: str | None = None,
    end_date: str | None = None,
    user_name: str | None = None,
) -> str:
    """호환용 도구입니다. 멘토링/특강 상세의 신청자 명단(participantNames)을 기준으로 연수생의 신청 일정을 반환합니다."""
    report_status(f"{user_name or '사용자'} 일정을 불러오고 있어요...")
    has_access = _has_calendar_access(user_name)
    calendar = _load_calendar_for_user(user_name)
    
    calendar = _filter_registration_events(calendar, start_date=start_date, end_date=end_date)

    # 취소 또는 반려된 일정은 캘린더 충돌 분석 대상에서 제외
    active_calendar = [
        item for item in calendar
        if item.get("qualityStatus", "valid") != "invalid"
        and item.get("source", "user_history") != "center_schedule"
        and not str(item.get("id", "")).startswith("sch_")
        and "취소" not in item.get("status", "")
        and "반려" not in item.get("status", "")
    ]
    report_status(f"활성 일정 {len(active_calendar)}건을 확인했어요...")
    result = {
        "calendar_owner": user_name or _get_current_user_name() or "me",
        "data_available": has_access,
        "data_source": "mentoring_detail_participant_names" if has_access else "unavailable",
        "total_active": len(active_calendar),
        "total_including_cancelled": len(calendar),
        "calendar": active_calendar
    }
    if not has_access:
        result["warning"] = "현재 포털 동기화 데이터에 멘토링/특강 목록이 동기화되지 않아 일정을 조회할 수 없습니다."
    return json.dumps(result, ensure_ascii=False, indent=2)


class FreeSlotsInput(BaseModel):
    start_date: str = Field(description="조회 시작 날짜 (ISO 형식, 예: '2026-06-01')")
    end_date: str = Field(description="조회 종료 날짜 (ISO 형식, 예: '2026-06-07')")
    meeting_duration_hours: float = Field(default=2.0, description="필요한 연속 회의 시간 (시간 단위, 예: 2.0)")
    working_hour_start: int = Field(default=9, description="일정 탐색 시작 시간 (0-23, 예: 9)")
    working_hour_end: int = Field(default=22, description="일정 탐색 종료 시간 (0-23, 예: 22)")
    exclude_weekends: bool = Field(default=False, description="주말 제외 여부")
    user_name: str | None = Field(default=None, description="조회할 단일 연수생의 이름 (기본값은 로그인된 본인)")
    user_names: list[str] | None = Field(default=None, description="조회할 연수생들의 이름 목록 (팀 일정 조율 시 예: ['강자은', '장선우', '김민수'])")
    team_name: str | None = Field(default=None, description="팀 공통 멘토링/특강 일정을 찾기 위한 팀명. 예: '고래'")
    include_team_shared_mentorings: bool = Field(default=True, description="팀명과 일치하는 멘토링/특강 목록 항목을 팀 공통 차단 일정으로 포함할지 여부")
    recurring_busy_blocks: list[dict] | None = Field(
        default=None,
        description=(
            "반복 차단 시간 목록. 예: [{'weekdays':['월','화','수','목','금'], "
            "'start':'10:00', 'end':'12:00', 'title':'팀 정기 회의'}]"
        ),
    )

@tool("get_free_slots", args_schema=FreeSlotsInput)
def get_free_slots_tool(
    start_date: str,
    end_date: str,
    meeting_duration_hours: float = 2.0,
    working_hour_start: int = 9,
    working_hour_end: int = 22,
    exclude_weekends: bool = False,
    user_name: str | None = None,
    user_names: list[str] | None = None,
    team_name: str | None = None,
    include_team_shared_mentorings: bool = True,
    recurring_busy_blocks: list[dict] | None = None,
) -> str:
    """지정한 연수생(들)의 캘린더에서 조건에 맞는 빈 요일 및 시간대 슬롯을 분석하여 반환합니다.
    user_names에 여러 명의 이름을 전달하면 팀원 전체 공동 가용 시간대를 계산하려고 시도합니다.
    개인 접수내역은 사용하지 않고, 멘토링/특강 상세의 신청자 명단에서 확인된 신청 일정만 차단 시간으로 사용합니다.
    team_name이 있으면 멘토링/특강 목록에서 팀명과 일치하는 팀 공통 일정을 차단 시간에 포함합니다."""
    names = user_names if user_names else []
    if not names:
        if user_name:
            names = [user_name]
        else:
            names = ["me"]
            
    report_status(f"{', '.join(names)} 일정표에서 빈 시간대를 계산하고 있어요...")
    
    from datetime import datetime, timedelta
    
    try:
        s_date = datetime.fromisoformat(start_date).date()
        e_date = datetime.fromisoformat(end_date).date()
    except Exception as e:
        return json.dumps({"error": f"날짜 형식이 잘못되었습니다: {str(e)}"}, ensure_ascii=False)
        
    blocked_events = []
    calendar_coverage = []
    team_shared_events = []
    for name in names:
        calendar = _load_calendar_for_user(name)
        active_calendar = [
            item for item in calendar
            if item.get("qualityStatus", "valid") != "invalid"
            and item.get("source", "user_history") != "center_schedule"
            and not str(item.get("id", "")).startswith("sch_")
            and "취소" not in item.get("status", "")
            and "반려" not in item.get("status", "")
        ]
        calendar_coverage.append({
            "user_name": name,
            "data_available": True,
            "data_source": "mentoring_detail_participant_names",
            "active_event_count": len(active_calendar),
        })
        for item in active_calendar:
            start_at_str = item.get("startAt")
            end_at_str = item.get("endAt")
            title = item.get("title", "일정")
            if start_at_str and end_at_str:
                try:
                    s_dt = datetime.fromisoformat(start_at_str)
                    e_dt = datetime.fromisoformat(end_at_str)
                    blocked_events.append((s_dt, e_dt, title, name))
                except Exception:
                    pass

    if include_team_shared_mentorings and team_name:
        def normalize_text(value: str) -> str:
            return "".join(ch for ch in str(value or "").lower() if not ch.isspace())

        team_key = normalize_text(team_name)
        team_patterns = {
            team_key,
            normalize_text(f"팀 {team_name}"),
            normalize_text(f"{team_name}팀"),
        }
        from database import db
        for item in db.load_mentorings():
            title = item.get("title", "")
            normalized_title = normalize_text(title)
            if not team_key or not any(pattern and pattern in normalized_title for pattern in team_patterns):
                continue
            start_at_str = item.get("startAt")
            end_at_str = item.get("endAt")
            if not start_at_str or not end_at_str:
                continue
            try:
                s_dt = datetime.fromisoformat(start_at_str)
                e_dt = datetime.fromisoformat(end_at_str)
            except Exception:
                continue
            if s_dt.date() > e_date or e_dt.date() < s_date:
                continue
            event_title = title or "팀 공통 멘토링/특강"
            blocked_events.append((s_dt, e_dt, event_title, "team_shared"))
            team_shared_events.append({
                "id": item.get("id", ""),
                "title": event_title,
                "date": s_dt.date().isoformat(),
                "start": s_dt.strftime("%H:%M"),
                "end": e_dt.strftime("%H:%M"),
                "source": "mentorings_by_team_name",
            })

    weekday_aliases = {
        "월": 0, "월요일": 0, "mon": 0, "monday": 0, 0: 0,
        "화": 1, "화요일": 1, "tue": 1, "tuesday": 1, 1: 1,
        "수": 2, "수요일": 2, "wed": 2, "wednesday": 2, 2: 2,
        "목": 3, "목요일": 3, "thu": 3, "thursday": 3, 3: 3,
        "금": 4, "금요일": 4, "fri": 4, "friday": 4, 4: 4,
        "토": 5, "토요일": 5, "sat": 5, "saturday": 5, 5: 5,
        "일": 6, "일요일": 6, "sun": 6, "sunday": 6, 6: 6,
    }

    def parse_hhmm(value: str):
        parts = str(value or "").strip().split(":")
        if len(parts) < 2:
            raise ValueError("HH:MM 형식이 아닙니다.")
        return int(parts[0]), int(parts[1])

    for block in recurring_busy_blocks or []:
        raw_weekdays = block.get("weekdays") or block.get("days") or []
        if isinstance(raw_weekdays, str):
            if raw_weekdays in ("평일", "weekdays"):
                raw_weekdays = ["월", "화", "수", "목", "금"]
            else:
                raw_weekdays = [part.strip() for part in raw_weekdays.split(",") if part.strip()]
        weekday_set = {
            weekday_aliases.get(str(day).lower(), weekday_aliases.get(day))
            for day in raw_weekdays
        }
        weekday_set.discard(None)
        title = block.get("title") or block.get("label") or "차단 일정"
        try:
            start_hour, start_min = parse_hhmm(block.get("start") or block.get("start_time"))
            end_hour, end_min = parse_hhmm(block.get("end") or block.get("end_time"))
        except Exception:
            continue

        current = s_date
        while current <= e_date:
            if current.weekday() in weekday_set:
                blocked_events.append((
                    datetime(current.year, current.month, current.day, start_hour, start_min),
                    datetime(current.year, current.month, current.day, end_hour, end_min),
                    f"{title} ({block.get('start') or block.get('start_time')}~{block.get('end') or block.get('end_time')})",
                    "fixed_block",
                ))
            current += timedelta(days=1)

    availability_scope = "team" if len(names) > 1 else "current_user_only"
    scope_warning = None
    if availability_scope == "current_user_only":
        scope_warning = (
            "이 결과는 멘토링/특강 상세 신청자 명단에서 확인된 로그인 사용자 신청 일정과 명시된 차단 시간만 반영했습니다."
        )
                    
    blocked_intervals = [(e[0], e[1]) for e in blocked_events]
    
    free_slots = []
    current_day = s_date
    meeting_window_delta = timedelta(hours=meeting_duration_hours)
    meeting_window_step = timedelta(minutes=30)
    while current_day <= e_date:
        if exclude_weekends and current_day.weekday() in (5, 6):
            current_day += timedelta(days=1)
            continue
            
        day_start = datetime(current_day.year, current_day.month, current_day.day, working_hour_start, 0)
        day_end = datetime(current_day.year, current_day.month, current_day.day, working_hour_end, 0)
        
        day_blocked = []
        for s_dt, e_dt in blocked_intervals:
            overlap_start = max(day_start, s_dt)
            overlap_end = min(day_end, e_dt)
            if overlap_start < overlap_end:
                day_blocked.append((overlap_start, overlap_end))
                
        day_blocked.sort(key=lambda x: x[0])

        current_time = day_start
        day_free_intervals = []
        for b_start, b_end in day_blocked:
            if b_start > current_time:
                duration = (b_start - current_time).total_seconds() / 3600.0
                if duration >= meeting_duration_hours:
                    day_free_intervals.append((current_time, b_start, duration))
            current_time = max(current_time, b_end)
            
        if day_end > current_time:
            duration = (day_end - current_time).total_seconds() / 3600.0
            if duration >= meeting_duration_hours:
                day_free_intervals.append((current_time, day_end, duration))

        day_free = []
        day_meeting_windows = []
        for free_start, free_end, duration in day_free_intervals:
            day_free.append({
                "start": free_start.strftime("%H:%M"),
                "end": free_end.strftime("%H:%M"),
                "duration_hours": duration
            })

            window_start = free_start
            while window_start + meeting_window_delta <= free_end:
                window_end = window_start + meeting_window_delta
                day_meeting_windows.append({
                    "date": current_day.isoformat(),
                    "weekday": ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"][current_day.weekday()],
                    "start": window_start.strftime("%H:%M"),
                    "end": window_end.strftime("%H:%M"),
                    "duration_hours": meeting_duration_hours,
                })
                window_start += meeting_window_step
                
        free_slots.append({
            "date": current_day.isoformat(),
            "weekday": ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"][current_day.weekday()],
            "free_slots": day_free,
            "meeting_windows": day_meeting_windows,
        })
        current_day += timedelta(days=1)
        
    # ─── Visual Schedule Block Generation (for React ScheduleCalendar) ───
    time_slots = []
    curr_hour = working_hour_start
    curr_min = 0
    while curr_hour < working_hour_end:
        time_slots.append(f"{curr_hour:02d}:{curr_min:02d}")
        curr_min += 30
        if curr_min >= 60:
            curr_min = 0
            curr_hour += 1
            
    headers = []
    days = []
    curr = s_date
    while curr <= e_date:
        weekday_name = ["월", "화", "수", "목", "금", "토", "일"][curr.weekday()]
        headers.append(f"{weekday_name}({curr.strftime('%m/%d')})")
        days.append(curr)
        curr += timedelta(days=1)
        
    lines = []
    lines.append("HEADER: " + ",".join(headers))

    def compact_schedule_label(value: str, max_len: int = 24) -> str:
        cleaned = str(value or "").replace(",", " ").replace("|", " ").strip()
        if len(cleaned) <= max_len:
            return cleaned
        return cleaned[:max_len - 1].rstrip() + "…"
    
    for slot_time in time_slots:
        sh, sm = map(int, slot_time.split(":"))
        slot_values = []
        for day in days:
            slot_start = datetime(day.year, day.month, day.day, sh, sm)
            slot_end = slot_start + timedelta(minutes=30)
            
            overlapping_events = []
            for s_dt, e_dt, title, user_name in blocked_events:
                if max(slot_start, s_dt) < min(slot_end, e_dt):
                    overlapping_events.append((title, user_name))
                    
            if not overlapping_events:
                slot_values.append("가능")
            else:
                # Group by title to de-duplicate and find attendees
                from collections import defaultdict
                title_to_users = defaultdict(list)
                for title, user in overlapping_events:
                    if user not in title_to_users[title]:
                        title_to_users[title].append(user)
                
                formatted_groups = []
                for title, users in title_to_users.items():
                    title_clean = title.replace(",", " ").replace("|", " ").strip()
                    title_label = compact_schedule_label(title)
                    display_users = [u for u in users if u not in ("fixed_block", "team_shared")]
                    if display_users:
                        user_suffix = f" ({' · '.join(display_users)})"
                    else:
                        if "team_shared" in users:
                            user_suffix = " (팀공통)"
                        else:
                            user_suffix = ""
                    formatted_groups.append((title_clean, title_label, user_suffix, title))
                
                if len(formatted_groups) == 1:
                    title_clean, title_label, user_suffix, original_title = formatted_groups[0]
                    first_user = title_to_users[original_title][0]
                    if first_user == "fixed_block":
                        detail = f"{title_clean}: 질문에서 제외 조건으로 지정된 반복 차단 시간입니다."
                    elif first_user == "team_shared":
                        detail = f"{title_clean}{user_suffix}: 팀명 '{team_name}'과 연결된 공통 멘토링/특강 일정입니다."
                    else:
                        detail = f"{title_clean}{user_suffix}: 신청자 명단 기준 해당 참여자가 신청한 멘토링/특강 일정입니다."
                    detail = detail.replace(",", " ")
                    
                    if "회의" in original_title or "멘토링" in original_title:
                        if "고래" in original_title or "팀" in original_title:
                            slot_values.append(f"회의:{title_label}{user_suffix}||{detail}")
                        else:
                            slot_values.append(f"멘토링:{title_label}{user_suffix}||{detail}")
                    elif "특강" in original_title or first_user != "fixed_block":
                        slot_values.append(f"특강:{title_label}{user_suffix}||{detail}")
                    else:
                        slot_values.append(f"불가:{title_label}{user_suffix}||{detail}")
                else:
                    # Multiple different events overlapping in the same slot: fallback to a combined description
                    combined_desc = " / ".join(f"{t}{u}" for t, _, u, _ in formatted_groups).replace(",", " ")
                    combined_label = compact_schedule_label(combined_desc, max_len=28)
                    slot_values.append(f"불가:{combined_label}||{combined_desc}")
                    
        lines.append(f"{slot_time}: " + ",".join(slot_values))
        
    visual_schedule_block = "```schedule\n" + "\n".join(lines) + "\n```"
    
    all_meeting_windows = [
        window
        for day in free_slots
        for window in day.get("meeting_windows", [])
    ]

    result = {
        "start_date": start_date,
        "end_date": end_date,
        "meeting_duration_hours": meeting_duration_hours,
        "availability_scope": availability_scope,
        "scope_warning": scope_warning,
        "calendar_coverage": calendar_coverage,
        "missing_user_names": [],
        "data_basis": "mentoring_detail_participant_names_only",
        "team_shared_events": team_shared_events,
        "recurring_busy_blocks": recurring_busy_blocks or [],
        "schedule": free_slots,
        "meeting_windows": all_meeting_windows,
        "visual_schedule_block": visual_schedule_block
    }
    return json.dumps(result, ensure_ascii=False, indent=2)


class TeamInfoInput(BaseModel):
    trainee_name: str | None = Field(
        default=None,
        description="조회할 연수생 이름. 그 연수생이 팀장 또는 팀원으로 속한 팀을 반환한다. 생략하면 로그인 사용자의 팀.",
    )
    team_name: str | None = Field(
        default=None,
        description="조회할 팀명. 예: '고래'. trainee_name 보다 우선 적용된다.",
    )


@tool("get_team_info", args_schema=TeamInfoInput)
def get_team_info_tool(trainee_name: str | None = None, team_name: str | None = None) -> str:
    """소마 연수생 팀 매칭 정보(팀명, 팀장, 팀원 목록, 멘토명, 프로젝트명 등)를 반환합니다.
    - trainee_name 을 주면 그 연수생이 팀장/팀원으로 속한 팀을 찾습니다(특정인의 팀·멘토 매칭 확인).
    - team_name 을 주면 해당 팀을 찾습니다.
    - 둘 다 없으면 로그인한 사용자의 팀을 반환합니다.
    팀명·팀원·전담 멘토·매칭 여부·프로젝트 정보를 물을 때 이 툴을 호출하세요."""
    all_teams = [item for item in _load_team_info() if item.get("qualityStatus", "valid") != "invalid"]
    current_user_name = _get_current_user_name()

    def _belongs(team: dict, name: str) -> bool:
        n = (name or "").strip()
        return bool(n) and (team.get("leader") == n or n in (team.get("members") or []))

    scope = ""
    matched: list[dict] = []
    if team_name:
        report_status(f"'{team_name}' 팀 정보를 찾고 있어요...")
        tn = team_name.strip()
        matched = [t for t in all_teams if (t.get("teamName") or "").strip() == tn]
        scope = "by_team_name"
    elif trainee_name and trainee_name not in ("me", current_user_name):
        report_status(f"{trainee_name} 연수생의 팀을 찾고 있어요...")
        matched = [t for t in all_teams if _belongs(t, trainee_name)]
        scope = "by_trainee_name"
    else:
        report_status("소속 팀 정보를 불러오고 있어요...")
        matched = [t for t in all_teams if _belongs(t, current_user_name or "")]
        scope = "current_user_team"

    # 조회 대상은 있는데(이름/팀명 지정) 매칭 0건이면, 엉뚱한 팀을 반환하지 말고 명확히 '없음'을 알린다.
    queried = team_name or (trainee_name if scope == "by_trainee_name" else None)
    if not matched and queried:
        report_status(f"'{queried}' 에 해당하는 팀을 찾지 못했어요.")
        return json.dumps({
            "total": 0,
            "current_user_name": current_user_name,
            "scope": scope,
            "queried": queried,
            "team_info": [],
            "warning": f"동기화된 팀 매칭 데이터에서 '{queried}' 에 해당하는 팀을 찾지 못했습니다. (전체 {len(all_teams)}개 팀)",
        }, ensure_ascii=False, indent=2)

    report_status(f"팀 정보 {len(matched)}건을 확인했어요...")
    return json.dumps({
        "total": len(matched),
        "current_user_name": current_user_name,
        "scope": scope,
        "team_info": matched,
    }, ensure_ascii=False, indent=2)


# 멘토 정적 데이터(노션 크롤링) 기반 검색 도구 — seonghyeon 이식분.
# minsu 의 search_mentors_tool 대신 분야/멘토유형/창업경험 교차검색이 가능한 버전을 쓰고,
# 검색 전 실제 값 확인용 list_facets 를 추가한다.
from mentor_tools import list_facets_tool, search_mentors_tool as facet_search_mentors_tool

# LangChain 에이전트용 통합 툴 리스트
LATEST_TOOLS = [
    facet_search_mentors_tool,
    list_facets_tool,
    search_mentorings_tool,
    vector_search_mentorings_tool,
    search_trainees_tool,
    get_participant_registrations_tool,
    get_team_participant_schedule_tool,
    get_user_calendar_tool,
    get_team_info_tool,
    get_free_slots_tool,
]
