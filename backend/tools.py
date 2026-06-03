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
    status: str = "접수중",
    query: str | None = None,
    date_query: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict:
    """멘토링 및 특강을 조건에 맞게 검색합니다."""
    items = [item for item in _load_mentorings() if item.get("qualityStatus", "valid") != "invalid"]
    
    # ─── 과거 일정 및 이미 등록된 일정 필터링 ───
    if not query:
        from datetime import datetime
        from database import db
        
        now_dt = datetime.now()
        user_cal = db.load_user_calendar()
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

MOCK_MEMBER_CALENDARS = {
    "강자은": [
        {
            "id": "mock_je_1",
            "title": "불편한 대화를 잘 하려면",
            "author": "한기용",
            "dateStr": "2026-06-01(월)",
            "timeRangeStr": "10:30:00 ~ 12:30:00",
            "status": "접수완료",
            "isApproved": True,
            "source": "user_history",
            "startAt": "2026-06-01T10:30:00",
            "endAt": "2026-06-01T12:30:00",
            "qualityStatus": "valid"
        },
        {
            "id": "mock_je_2",
            "title": "팀 고래 멘토링",
            "author": "한기용",
            "dateStr": "2026-06-02(화)",
            "timeRangeStr": "13:00:00 ~ 14:00:00",
            "status": "접수완료",
            "isApproved": True,
            "source": "user_history",
            "startAt": "2026-06-02T13:00:00",
            "endAt": "2026-06-02T14:00:00",
            "qualityStatus": "valid"
        },
        {
            "id": "mock_je_3",
            "title": "클라우드 서비스 배포 실무 특강",
            "author": "홍길동",
            "dateStr": "2026-06-03(수)",
            "timeRangeStr": "14:00:00 ~ 16:00:00",
            "status": "접수완료",
            "isApproved": True,
            "source": "user_history",
            "startAt": "2026-06-03T14:00:00",
            "endAt": "2026-06-03T16:00:00",
            "qualityStatus": "valid"
        },
        {
            "id": "mock_je_4",
            "title": "고래팀 프로젝트 기획 피드백 멘토링",
            "author": "한기용",
            "dateStr": "2026-06-04(목)",
            "timeRangeStr": "19:00:00 ~ 21:00:00",
            "status": "접수완료",
            "isApproved": True,
            "source": "user_history",
            "startAt": "2026-06-04T19:00:00",
            "endAt": "2026-06-04T21:00:00",
            "qualityStatus": "valid"
        }
    ],
    "장선우": [
        {
            "id": "mock_sw_1",
            "title": "팀 고래 멘토링",
            "author": "한기용",
            "dateStr": "2026-06-02(화)",
            "timeRangeStr": "13:00:00 ~ 14:00:00",
            "status": "접수완료",
            "isApproved": True,
            "source": "user_history",
            "startAt": "2026-06-02T13:00:00",
            "endAt": "2026-06-02T14:00:00",
            "qualityStatus": "valid"
        },
        {
            "id": "mock_sw_2",
            "title": "대규모 서비스 DB 설계 및 튜닝 특강",
            "author": "강성욱",
            "dateStr": "2026-06-03(수)",
            "timeRangeStr": "10:00:00 ~ 12:00:00",
            "status": "접수완료",
            "isApproved": True,
            "source": "user_history",
            "startAt": "2026-06-03T10:00:00",
            "endAt": "2026-06-03T12:00:00",
            "qualityStatus": "valid"
        },
        {
            "id": "mock_sw_3",
            "title": "고래팀 자유멘토링을 통한 아이디어 확장해보기",
            "author": "한대용",
            "dateStr": "2026-06-04(목)",
            "timeRangeStr": "20:00:00 ~ 21:30:00",
            "status": "접수완료",
            "isApproved": True,
            "source": "user_history",
            "startAt": "2026-06-04T20:00:00",
            "endAt": "2026-06-04T21:30:00",
            "qualityStatus": "valid"
        },
        {
            "id": "mock_sw_4",
            "title": "스타트업 인프라 아키텍처 설계 멘토링",
            "author": "박순영",
            "dateStr": "2026-06-05(금)",
            "timeRangeStr": "14:00:00 ~ 17:00:00",
            "status": "접수완료",
            "isApproved": True,
            "source": "user_history",
            "startAt": "2026-06-05T14:00:00",
            "endAt": "2026-06-05T17:00:00",
            "qualityStatus": "valid"
        }
    ]
}

def _load_calendar_for_user(user_name: str | None) -> list[dict]:
    from database import db
    user_info = db.load_user_info()
    current_user_name = user_info.get("name", "김민수") if user_info else "김민수"
    if not user_name or user_name == current_user_name or user_name == "me":
        return db.load_user_calendar()
    return MOCK_MEMBER_CALENDARS.get(user_name, [])

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
    status: str = Field(default="접수중", description="접수 상태 필터. '접수중', '마감', '전체' 중 하나.")
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
    status: str = "접수중",
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


class CalendarSearchInput(BaseModel):
    start_date: str | None = Field(default=None, description="조회 시작 날짜 (ISO 형식, 예: '2026-06-01')")
    end_date: str | None = Field(default=None, description="조회 종료 날짜 (ISO 형식, 예: '2026-06-07')")
    user_name: str | None = Field(default=None, description="조회할 연수생의 이름 (기본값은 로그인된 본인)")

@tool("get_user_calendar", args_schema=CalendarSearchInput)
def get_user_calendar_tool(
    start_date: str | None = None,
    end_date: str | None = None,
    user_name: str | None = None,
) -> str:
    """특정 연수생의 개인 시간표(접수 완료된 특강 및 멘토링 일정) 목록을 반환합니다.
    user_name을 지정하여 다른 팀원의 일정을 개별적으로 조회할 수 있습니다."""
    report_status(f"{user_name or '사용자'} 일정을 불러오고 있어요...")
    calendar = _load_calendar_for_user(user_name)
    
    # 날짜 범위 필터 적용
    if start_date or end_date:
        filtered = []
        for item in calendar:
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
        calendar = filtered

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
        "total_active": len(active_calendar),
        "total_including_cancelled": len(calendar),
        "calendar": active_calendar
    }
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
) -> str:
    """지정한 연수생(들)의 캘린더에서 조건에 맞는 빈 요일 및 시간대 슬롯을 분석하여 반환합니다.
    user_names에 여러 명의 이름을 전달하여 팀원 전체의 공동 가용 시간대(공통 빈 슬롯)를 한번에 찾을 수 있습니다."""
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
                    
    blocked_intervals = [(e[0], e[1]) for e in blocked_events]
    
    free_slots = []
    current_day = s_date
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
        day_free = []
        for b_start, b_end in day_blocked:
            if b_start > current_time:
                duration = (b_start - current_time).total_seconds() / 3600.0
                if duration >= meeting_duration_hours:
                    day_free.append({
                        "start": current_time.strftime("%H:%M"),
                        "end": b_start.strftime("%H:%M"),
                        "duration_hours": duration
                    })
            current_time = max(current_time, b_end)
            
        if day_end > current_time:
            duration = (day_end - current_time).total_seconds() / 3600.0
            if duration >= meeting_duration_hours:
                day_free.append({
                    "start": current_time.strftime("%H:%M"),
                    "end": day_end.strftime("%H:%M"),
                    "duration_hours": duration
                })
                
        free_slots.append({
            "date": current_day.isoformat(),
            "weekday": ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"][current_day.weekday()],
            "free_slots": day_free
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
    
    for slot_time in time_slots:
        sh, sm = map(int, slot_time.split(":"))
        slot_values = []
        for day in days:
            slot_start = datetime(day.year, day.month, day.day, sh, sm)
            slot_end = slot_start + timedelta(minutes=30)
            
            overlap_event = None
            for s_dt, e_dt, title, user_name in blocked_events:
                if max(slot_start, s_dt) < min(slot_end, e_dt):
                    overlap_event = (title, user_name)
                    break
                    
            if not overlap_event:
                slot_values.append("가능")
            else:
                title, user_name = overlap_event
                title_clean = title.replace(",", " ").replace(":", " ").strip()
                if len(title_clean) > 8:
                    title_clean = title_clean[:7] + ".."
                
                if "회의" in title or "멘토링" in title:
                    if "고래" in title or "팀" in title:
                        slot_values.append("회의")
                    else:
                        slot_values.append(f"멘토링:{title_clean}")
                elif "특강" in title:
                    slot_values.append(f"특강:{title_clean}")
                else:
                    slot_values.append("불가")
                    
        lines.append(f"{slot_time}: " + ",".join(slot_values))
        
    visual_schedule_block = "```schedule\n" + "\n".join(lines) + "\n```"
    
    result = {
        "start_date": start_date,
        "end_date": end_date,
        "meeting_duration_hours": meeting_duration_hours,
        "schedule": free_slots,
        "visual_schedule_block": visual_schedule_block
    }
    return json.dumps(result, ensure_ascii=False, indent=2)


@tool("get_team_info")
def get_team_info_tool() -> str:
    """현재 로그인한 연수생의 소속 팀 매칭 정보(팀명, 팀장, 팀원 목록, 멘토명, 프로젝트명 등)를 반환합니다.
    사용자의 팀명, 팀원, 전담 멘토, 프로젝트 개발 기술 스택이나 도메인 등의 정보를 물어볼 때 이 툴을 호출하여 참조하세요."""
    report_status("소속 팀 정보를 불러오고 있어요...")
    team_info = [item for item in _load_team_info() if item.get("qualityStatus", "valid") != "invalid"]
    report_status(f"팀 매칭 정보 {len(team_info)}건을 확인했어요...")
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
    get_free_slots_tool,
]
