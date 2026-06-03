"""에이전트가 호출하는 도구(Tool)들.

기획서의 MVP 2개 도구:
  - search_mentors      : 조건에 맞는 멘토 검색
  - search_sessions     : 접수 중 멘토링/특강 검색
샘플 데이터(JSON) 기반으로 동작하며, 추후 DB/RAG 로 교체한다.
"""

import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def _load(name: str) -> list[dict]:
    with open(DATA_DIR / name, encoding="utf-8") as f:
        return json.load(f)


def search_mentors(stack: str = "", field: str = "", startup: bool | None = None) -> list[dict]:
    """스택/분야/창업경험 조건으로 멘토를 필터링한다."""
    mentors = _load("mentors.json")
    results = []
    for m in mentors:
        if stack and not any(stack.lower() in s.lower() for s in m["stacks"]):
            continue
        if field and not any(field in f for f in m["fields"]):
            continue
        if startup is not None and m["startup_experience"] != startup:
            continue
        results.append(m)
    return results


def search_sessions(field: str = "", only_open: bool = True) -> list[dict]:
    """분야 조건으로 멘토링/특강을 필터링한다. 기본은 접수중만."""
    sessions = _load("sessions.json")
    results = []
    for s in sessions:
        if only_open and s["status"] != "접수중":
            continue
        if field and not any(field in f for f in s["field"]):
            continue
        results.append(s)
    return results


# ── Upstage(OpenAI 호환) function calling 스키마 ──
TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "search_mentors",
            "description": "기술 스택/관심 분야/창업경험 조건에 맞는 소마 멘토를 검색한다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "stack": {"type": "string", "description": "예: Spring, React, Python"},
                    "field": {"type": "string", "description": "예: 백엔드, 창업, AI"},
                    "startup": {"type": "boolean", "description": "창업 경험 멘토만 찾을 때 true"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_sessions",
            "description": "접수 중인 소마 멘토링/특강을 분야 조건으로 검색한다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "field": {"type": "string", "description": "예: 클라우드, AI, 백엔드"},
                    "only_open": {"type": "boolean", "description": "접수중만 보려면 true(기본)"},
                },
            },
        },
    },
]

TOOL_IMPL = {
    "search_mentors": search_mentors,
    "search_sessions": search_sessions,
}
