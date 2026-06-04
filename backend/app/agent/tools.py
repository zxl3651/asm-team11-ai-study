"""에이전트가 호출하는 도구(Tool)들.

기획서의 MVP 도구:
  - list_facets      : 데이터에 실제로 존재하는 스택/분야/멘토유형 값을 조회 (탐색용)
  - search_mentors   : 조건에 맞는 멘토 검색 (랭킹 포함)
  - search_sessions  : 접수 중 멘토링/특강 검색
샘플 데이터(JSON) 기반으로 동작하며, 추후 DB/RAG 로 교체한다.

에이전트가 자율적으로 분기(branching)하도록 설계됐다:
  사용자의 자연어 → (필요시) list_facets 로 실제 값 확인
  → search_mentors 로 조회 → 결과가 비거나 과하면 조건을 바꿔 재검색.
"""

import json
import re
from collections import Counter
from pathlib import Path

from app import context_store

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

MAX_RESULTS = 15  # LLM 이 추론하기 좋은 상한 (랭킹 상위만 반환)


def _load(name: str) -> list[dict]:
    with open(DATA_DIR / name, encoding="utf-8") as f:
        return json.load(f)


def _norm(s: str) -> str:
    """'Next.js' / 'next js' / 'NextJs' 를 같은 키로 정규화한다.
    영문/숫자/한글만 남기고 소문자화 (점·공백·하이픈 제거)."""
    return re.sub(r"[^0-9a-z가-힣]", "", s.lower())


def _tokens(query: str) -> list[str]:
    """'React, Node.js' 처럼 여러 값이 한 문자열로 오는 경우를 쪼갠다."""
    return [_norm(t) for t in query.replace("/", ",").split(",") if _norm(t)]


def _hit_count(query: str, values: list[str]) -> int:
    """query 토큰 중 values 와 (정규화 후) 부분일치하는 토큰 수."""
    if not query:
        return 0
    nvals = [_norm(v) for v in values]
    return sum(any(tok in v for v in nvals) for tok in _tokens(query))


def _required(query: str, values: list[str]) -> bool:
    """query 가 비었으면 통과, 아니면 토큰 중 하나라도 맞아야 통과."""
    return _hit_count(query, values) > 0 if query else True


def list_facets(kind: str = "") -> dict:
    """멘토 데이터에 실제로 존재하는 값 목록을 빈도순으로 반환한다.

    사용자의 자연어 표현이 데이터의 실제 값과 다를 수 있으므로
    (예: 'Next.js' → 'NextJs', '풀스택'은 stack 이 아니라 field),
    검색 전에 이 도구로 실제 값을 확인해 정확히 조회할 수 있다.

    kind: 'stacks' | 'fields' | 'types' (비우면 셋 다, 각 상위 40개)
    """
    mentors = _load("mentors.json")
    out: dict[str, list[str]] = {}
    kinds = [kind] if kind in ("stacks", "fields", "types") else ["stacks", "fields", "types"]
    for k in kinds:
        c: Counter = Counter()
        for m in mentors:
            for v in m.get(k, []):
                c[v] += 1
        out[k] = [f"{v} ({n})" for v, n in c.most_common(40)]
    return out


def search_mentors(
    stack: str = "",
    field: str = "",
    mentor_type: str = "",
    startup: bool | None = None,
) -> dict:
    """스택/분야/멘토유형/창업경험 조건으로 멘토를 필터링하고 랭킹한다.

    여러 조건을 주면 AND(모두 만족)로 거르고, 일치한 항목 수(score)가 높은
    순으로 정렬해 상위 결과만 반환한다. 각 멘토에 왜 뽑혔는지 matched 를 붙인다.
    """
    mentors = _load("mentors.json")
    scored = []
    for m in mentors:
        if not _required(stack, m["stacks"]):
            continue
        if not _required(field, m["fields"]):
            continue
        if not _required(mentor_type, m.get("types", [])):
            continue
        if startup is not None and m["startup_experience"] != startup:
            continue

        score = (
            _hit_count(stack, m["stacks"])
            + _hit_count(field, m["fields"])
            + _hit_count(mentor_type, m.get("types", []))
        )
        matched = {
            "stacks": [s for s in m["stacks"] if _hit_count(stack, [s])],
            "fields": [f for f in m["fields"] if _hit_count(field, [f])],
        }
        scored.append((score, {**m, "_score": score, "matched": matched}))

    scored.sort(key=lambda x: x[0], reverse=True)
    results = [m for _, m in scored[:MAX_RESULTS]]
    return {
        "total_matched": len(scored),
        "returned": len(results),
        "mentors": results,
    }


def _teamed_names() -> set[str]:
    """팀매칭 캐시에서 '이미 팀이 있는' 연수생 이름 집합을 만든다."""
    names: set[str] = set()
    for team in context_store.get_teams():
        for m in team.get("members", []):
            n = m.strip()
            if n:
                names.add(n)
    return names


def search_trainees(stack: str = "", looking_for_team: bool | None = None) -> dict:
    """기술 스택/팀 구성 여부로 연수생(동료)을 검색해 일치도순으로 반환한다.

    팀 구성 여부(has_team / looking_for_team)는 연수생 명단(static)과
    팀매칭 캐시(실시간, 확장이 올림)를 대조해 판별한다 — 노션의 옛 정보가 아니라
    현재 팀매칭 현황 기준. 팀매칭 캐시가 비어 있으면 팀 여부는 알 수 없다(null).
    연수생 개인정보는 이메일만 제공한다(전화번호 등은 수집하지 않음).
    """
    trainees = _load("trainees.json")
    teamed = _teamed_names()
    have_teams = bool(teamed)  # 팀매칭 데이터가 로드돼 있는가
    scored = []
    for t in trainees:
        if not _required(stack, t["stacks"]):
            continue
        has_team = (t["name"] in teamed) if have_teams else None
        if looking_for_team is not None and have_teams and (not has_team) != looking_for_team:
            continue
        score = _hit_count(stack, t["stacks"])
        matched = [s for s in t["stacks"] if _hit_count(stack, [s])]
        scored.append((score, {**t, "_score": score, "matched": matched, "has_team": has_team}))

    scored.sort(key=lambda x: x[0], reverse=True)
    results = [t for _, t in scored[:MAX_RESULTS]]
    out = {"total_matched": len(scored), "returned": len(results), "trainees": results}
    if not have_teams and looking_for_team is not None:
        out["note"] = "팀매칭 데이터가 아직 로드되지 않아 팀 구성 여부로 거를 수 없습니다."
    return out


def search_teams(query: str = "", only_with_mentor: bool | None = None) -> dict:
    """팀매칭 현황을 검색한다(확장이 올린 실시간 캐시).

    query 는 팀명/팀원/멘토명 키워드. only_with_mentor=True 면 멘토가 매칭된 팀만.
    '누가 어느 팀인지', '어떤 팀에 어떤 멘토가 붙었는지' 같은 질문에 쓴다.
    """
    teams = context_store.get_teams()
    if not teams:
        return {"returned": 0, "teams": [], "note": "팀매칭 데이터가 아직 로드되지 않았습니다(확장이 소마 포털에서 동기화 필요)."}
    results = []
    for tm in teams:
        hay = [tm.get("team", ""), tm.get("leader", ""), tm.get("mentor", "")] + tm.get("members", [])
        if query and not _required(query, hay):
            continue
        if only_with_mentor is not None and bool(tm.get("mentor")) != only_with_mentor:
            continue
        results.append(tm)
    return {"returned": len(results), "teams": results[:MAX_RESULTS]}


def search_sessions(query: str = "", session_type: str = "") -> dict:
    """접수중인 특강/멘토링을 검색한다.

    데이터는 확장이 사용자 세션으로 실시간 파싱해 백엔드에 올린 캐시에서 읽는다
    (로그인 필요 데이터라 서버가 직접 못 긁음). 캐시가 비어 있으면 빈 결과.
    query 는 제목/멘토명 키워드, session_type 은 '특강' 또는 '멘토링'.
    """
    sessions = context_store.get_sessions()
    if not sessions:
        return {
            "returned": 0,
            "sessions": [],
            "note": "특강/멘토링 데이터가 아직 로드되지 않았습니다(확장이 소마 포털에서 동기화 필요).",
        }
    results = []
    for s in sessions:
        if session_type and session_type not in s.get("type", ""):
            continue
        if query and not (_required(query, [s.get("title", "")]) or _required(query, [s.get("mentor", "")])):
            continue
        remaining = max(s.get("capacity", 0) - s.get("applied", 0), 0)
        results.append({**s, "remaining_spots": remaining})
    shown = results[:MAX_RESULTS]
    return {"total_open": len(results), "shown_count": len(shown), "sessions": shown}


# ── Upstage(OpenAI 호환) function calling 스키마 ──
TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "list_facets",
            "description": (
                "멘토 데이터에 '실제로 존재하는' 스택/분야/멘토유형 값을 빈도순으로 조회한다. "
                "사용자가 말한 표현이 데이터와 정확히 일치하는지 모를 때, 또는 어떤 분류가 "
                "있는지 파악해 검색 조건을 정확히 세우고 싶을 때 먼저 호출한다. "
                "(예: '풀스택'이 stack 인지 field 인지, 'Next.js'가 어떤 표기로 저장됐는지 확인)"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "kind": {
                        "type": "string",
                        "enum": ["stacks", "fields", "types"],
                        "description": "조회할 분류. 비우면 셋 다 반환.",
                    }
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_mentors",
            "description": (
                "조건에 맞는 소마 멘토를 검색해 일치도(score) 높은 순으로 반환한다. "
                "여러 조건은 AND 로 적용된다. 결과의 total_matched 가 0 이면 조건을 완화하고, "
                "너무 많으면 조건을 더해 좁힌다."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "stack": {
                        "type": "string",
                        "description": "기술 스택. 예: Spring, React, NextJs. 표기가 헷갈리면 list_facets 로 확인.",
                    },
                    "field": {
                        "type": "string",
                        "description": "관심/전문 분야. 사용자가 분야를 직접 말한 경우에만 채운다. 예: 풀스택, 백엔드, 창업, AI, 클라우드",
                    },
                    "mentor_type": {
                        "type": "string",
                        "description": "멘토 유형. 예: 기술멘토, 비기술멘토, 국내멘토, 해외멘토",
                    },
                    "startup": {"type": "boolean", "description": "창업 경험 멘토만 찾을 때 true"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_trainees",
            "description": (
                "기술 스택/팀 구성 여부로 동료 연수생을 검색한다. '팀원 구하는 사람', "
                "'React 쓰는 연수생' 같은 질문에 사용. 개인정보는 이메일만 제공된다."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "stack": {"type": "string", "description": "기술 스택. 예: React, Python, Spring"},
                    "looking_for_team": {
                        "type": "boolean",
                        "description": "아직 팀을 구하는 중인 연수생만 보려면 true",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_teams",
            "description": (
                "팀매칭 현황을 검색한다. 팀명/팀원/멘토명 키워드(query)로 거르고, "
                "only_with_mentor=true 면 멘토 매칭된 팀만. '○○는 어느 팀이야', "
                "'△△팀 멤버 누구야', '멘토 □□가 맡은 팀' 같은 질문에 사용."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "팀명/팀원이름/멘토명 키워드"},
                    "only_with_mentor": {"type": "boolean", "description": "멘토가 매칭된 팀만 보려면 true"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_sessions",
            "description": (
                "접수 중인 소마 특강/자유멘토링을 검색한다. 제목·멘토명 키워드(query)나 "
                "종류(session_type: '특강'/'멘토링')로 거른다. 남은 자리(remaining_spots)도 함께 준다."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "제목/멘토명 키워드. 예: LLM, 쿠버네티스, 창업, 강준혁"},
                    "session_type": {"type": "string", "description": "'특강' 또는 '멘토링'. 종류 무관이면 비움"},
                },
            },
        },
    },
]

TOOL_IMPL = {
    "list_facets": list_facets,
    "search_mentors": search_mentors,
    "search_trainees": search_trainees,
    "search_teams": search_teams,
    "search_sessions": search_sessions,
}
