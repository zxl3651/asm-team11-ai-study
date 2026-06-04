import json
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"

def _load_mentors() -> list[dict]:
    with open(DATA_DIR / "mentors.json", encoding="utf-8") as f:
        return json.load(f)

def search_mentors(
    stacks: list[str] | None = None,
    goals: list[str] | None = None,
    domains: list[str] | None = None,
    available_only: bool = True,
    limit: int = 10,
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
        "mentors": results[:limit],
    }


def _load_trainees() -> list[dict]:
    with open(DATA_DIR / "trainees.json", encoding="utf-8") as f:
        return json.load(f)


def search_trainees(
    roles: list[str] | None = None,
    stacks: list[str] | None = None,
    team_status: str | None = None,
    limit: int = 10,
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

    return {"total": len(results), "trainees": results[:limit]}


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
                    "limit": {
                        "type": "integer",
                        "description": "반환할 최대 결과 개수. 사용자가 특정 개수를 요청하면 이 값을 설정하세요. 기본값 10.",
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
                    "limit": {
                        "type": "integer",
                        "description": "반환할 최대 결과 개수. 사용자가 특정 개수를 요청하면 이 값을 설정하세요. 기본값 10.",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "request_client_fetch",
            "description": (
                "소프트웨어 마에스트로 부산 홈페이지의 최신 실시간 게시판 데이터(팀 매칭, 멘토링/특강, 월간일정 등)를 가져옵니다. "
                "사용자가 실시간 멘토링 현황, 새로운 팀 매칭, 일정 등을 물어볼 때 이 도구를 호출하세요."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "가져올 게시판 URL. 다음 중 하나를 선택하세요: \n1. 팀 매칭: https://swmaestro.ai/busan/sw/mypage/myTeam/team.do?menuNo=200093\n2. 멘토링/특강: https://swmaestro.ai/busan/sw/mypage/mentoLec/list.do?menuNo=200046\n3. 월간일정: https://swmaestro.ai/busan/sw/mypage/schedule/list.do?menuNo=200043",
                    }
                },
                "required": ["url"],
            },
        },
    },
]


def execute_tool(tool_name: str, tool_input: dict) -> str:
    limit = tool_input.get("limit", 10)
    if tool_name == "search_mentors":
        result = search_mentors(
            stacks=tool_input.get("stacks"),
            goals=tool_input.get("goals"),
            domains=tool_input.get("domains"),
            available_only=tool_input.get("available_only", True),
            limit=limit,
        )

    elif tool_name == "search_trainees":
        result = search_trainees(
            roles=tool_input.get("roles"),
            stacks=tool_input.get("stacks"),
            team_status=tool_input.get("team_status"),
            limit=limit,
        )
    else:
        result = {"error": f"알 수 없는 도구: {tool_name}"}

    return json.dumps(result, ensure_ascii=False, indent=2)
