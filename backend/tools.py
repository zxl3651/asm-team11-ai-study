import json
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"

def _load_mentors() -> list[dict]:
    with open(DATA_DIR / "mentors.json", encoding="utf-8") as f:
        return json.load(f)

def _load_mentorings() -> list[dict]:
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
) -> dict:
    """멘토링 및 특강을 조건에 맞게 검색합니다."""
    items = _load_mentorings()
    results = []

    for item in items:
        if status and item.get("status") != status:
            continue

        if content_type and content_type in ("mentoring", "lecture"):
            if item.get("type") != content_type:
                continue

        score = 0

        if domains:
            item_domain = item.get("domain", "").lower()
            matched = [d for d in domains if d.lower() in item_domain]
            if matched:
                score += len(matched) * 3

        if stacks:
            item_stacks_lower = [s.lower() for s in item.get("stacks", [])]
            matched = [s for s in stacks if s.lower() in item_stacks_lower]
            if matched:
                score += len(matched) * 2

        if goals:
            item_goals = item.get("goals", [])
            matched = [g for g in goals if g in item_goals]
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
        spots_info.append({
            **r,
            "remaining_spots": r["max_participants"] - r["current_participants"],
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


TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "search_mentors",
            "description": (
                "소마 멘토를 조건(기술 스택, 목표, 관심 분야)에 맞게 검색합니다. "
                "사용자가 '멘토 추천', '멘토 찾기', '멘토 알려줘' 등을 요청할 때 사용하세요."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "stacks": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "검색할 기술 스택 목록. 예: ['Spring', 'Java', 'AWS']",
                    },
                    "goals": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "목표 목록. '취업' 또는 '창업' 중 선택.",
                    },
                    "domains": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "관심 분야 목록. 예: ['클라우드', '대규모 트래픽', '스타트업']",
                    },
                    "available_only": {
                        "type": "boolean",
                        "description": "현재 멘토링 가능한 멘토만 검색할지 여부. 기본값 true.",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_mentorings",
            "description": (
                "소마 멘토링과 특강을 조건에 맞게 검색합니다. "
                "사용자가 '멘토링 알려줘', '특강 찾아줘', '신청할 수 있는 거 뭐 있어' 등을 요청할 때 사용하세요."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "content_type": {
                        "type": "string",
                        "description": "콘텐츠 유형. 'mentoring'(멘토링) 또는 'lecture'(특강). 미지정 시 모두 검색.",
                    },
                    "domains": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "관심 분야 목록. 예: ['클라우드', '백엔드', 'ML/AI']",
                    },
                    "stacks": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "기술 스택 목록. 예: ['Python', 'AWS']",
                    },
                    "goals": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "목표 목록. '취업' 또는 '창업'",
                    },
                    "status": {
                        "type": "string",
                        "description": "접수 상태 필터. '접수중', '마감', '전체' 중 하나. 기본값: '접수중'",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_trainees",
            "description": (
                "소마 연수생을 역할/기술스택/팀 여부로 검색합니다. "
                "사용자가 '연수생 찾아줘', '팀원 구하는 사람 있어?', '백엔드 연수생 알려줘' 등을 요청할 때 사용하세요."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "roles": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "찾는 역할 목록. 예: ['백엔드', 'AI', '프론트엔드', '기획', '풀스택']",
                    },
                    "stacks": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "기술 스택 목록. 예: ['Python', 'React', 'Spring Boot']",
                    },
                    "team_status": {
                        "type": "string",
                        "description": "팀 여부 필터. '팀없음'(팀원 모집 중) 또는 '팀있음'. 미지정 시 전체.",
                    },
                },
            },
        },
    },
]


def execute_tool(tool_name: str, tool_input: dict) -> str:
    if tool_name == "search_mentors":
        result = search_mentors(
            stacks=tool_input.get("stacks"),
            goals=tool_input.get("goals"),
            domains=tool_input.get("domains"),
            available_only=tool_input.get("available_only", True),
        )
    elif tool_name == "search_mentorings":
        status = tool_input.get("status", "접수중")
        if status == "전체":
            status = None
        result = search_mentorings(
            content_type=tool_input.get("content_type"),
            domains=tool_input.get("domains"),
            stacks=tool_input.get("stacks"),
            goals=tool_input.get("goals"),
            status=status,
        )
    elif tool_name == "search_trainees":
        result = search_trainees(
            roles=tool_input.get("roles"),
            stacks=tool_input.get("stacks"),
            team_status=tool_input.get("team_status"),
        )
    else:
        result = {"error": f"알 수 없는 도구: {tool_name}"}

    return json.dumps(result, ensure_ascii=False, indent=2)
