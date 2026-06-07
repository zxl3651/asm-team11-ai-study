"""멘토 정적 데이터(노션 크롤링) 기반 검색 도구.

seonghyeon 브랜치의 강점이던 `list_facets` + `search_mentors`(스택·분야·멘토유형·
창업경험 교차검색, 일치 근거 포함)를 LangChain 도구로 이식한 모듈.

멘토는 실시간 파싱이 아니라 정적 JSON(`data/mentors.json`)을 소스로 쓴다.
일정/특강/팀 정보는 minsu 파이프라인(DB·실시간 파싱)을 그대로 사용한다.
"""

import json
import re
from collections import Counter
from pathlib import Path

from langchain_core.tools import tool
from pydantic import BaseModel, Field

DATA_DIR = Path(__file__).parent / "data"
MAX_RESULTS = 15


def report_status(message: str) -> None:
    """tools.report_status 로 위임 (순환 import 방지를 위해 지연 로드)."""
    from tools import report_status as _report
    _report(message)


def _load_mentors() -> list[dict]:
    path = DATA_DIR / "mentors.json"
    if not path.exists():
        report_status("멘토 원본 데이터가 아직 수집되지 않았어요.")
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _norm(s: str) -> str:
    """'Next.js' / 'next js' / 'NextJs' 를 같은 키로 정규화(영숫자·한글만, 소문자)."""
    return re.sub(r"[^0-9a-z가-힣]", "", s.lower())


def _tokens(query: str) -> list[str]:
    return [_norm(t) for t in query.replace("/", ",").split(",") if _norm(t)]


def _hit_count(query: str, values: list[str]) -> int:
    if not query:
        return 0
    nvals = [_norm(v) for v in values]
    return sum(any(tok in v for v in nvals) for tok in _tokens(query))


def _required(query: str, values: list[str]) -> bool:
    return _hit_count(query, values) > 0 if query else True


def list_facets(kind: str = "") -> dict:
    """멘토 데이터에 실제로 존재하는 스택/분야/멘토유형 값을 빈도순으로 반환."""
    mentors = _load_mentors()
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
    """스택/분야/멘토유형/창업경험 조건으로 멘토를 AND 필터링하고 일치도순 랭킹."""
    mentors = _load_mentors()
    report_status(f"멘토 {len(mentors)}명을 불러왔어요...")
    scored = []
    for m in mentors:
        if not _required(stack, m.get("stacks", [])):
            continue
        if not _required(field, m.get("fields", [])):
            continue
        if not _required(mentor_type, m.get("types", [])):
            continue
        if startup is not None and m.get("startup_experience", False) != startup:
            continue

        score = (
            _hit_count(stack, m.get("stacks", []))
            + _hit_count(field, m.get("fields", []))
            + _hit_count(mentor_type, m.get("types", []))
        )
        matched = {
            "stacks": [s for s in m.get("stacks", []) if _hit_count(stack, [s])],
            "fields": [f for f in m.get("fields", []) if _hit_count(field, [f])],
        }
        scored.append((score, {**m, "_score": score, "matched": matched}))

    scored.sort(key=lambda x: x[0], reverse=True)
    results = [m for _, m in scored[:MAX_RESULTS]]
    report_status(f"조건에 맞는 멘토 {len(scored)}명을 추렸어요...")
    return {
        "total_matched": len(scored),
        "returned": len(results),
        "mentors": results,
    }


# ── LangChain Structured Tools ──

class ListFacetsInput(BaseModel):
    kind: str | None = Field(
        default=None,
        description="조회할 분류: 'stacks' | 'fields' | 'types'. 비우면 셋 다 반환.",
    )


@tool("list_facets", args_schema=ListFacetsInput)
def list_facets_tool(kind: str | None = None) -> str:
    """멘토 데이터에 '실제로 존재하는' 스택/분야/멘토유형 값을 빈도순으로 조회한다.
    사용자가 말한 표현이 데이터와 정확히 일치하는지 모를 때(예: '풀스택'이 stack인지 field인지,
    'Next.js'가 어떤 표기로 저장됐는지) search_mentors 호출 전에 먼저 사용한다."""
    return json.dumps(list_facets(kind=kind or ""), ensure_ascii=False, indent=2)


class MentorFacetSearchInput(BaseModel):
    stack: str | None = Field(default=None, description="기술 스택. 예: Spring, React, NextJs. 표기가 헷갈리면 list_facets로 확인.")
    field: str | None = Field(default=None, description="관심/전문 분야. 예: 풀스택, 백엔드, 창업, AI, 클라우드")
    mentor_type: str | None = Field(default=None, description="멘토 유형. 예: 기술멘토, 비기술멘토, 국내멘토, 해외멘토")
    startup: bool | None = Field(default=None, description="창업 경험 멘토만 찾을 때 true")


@tool("search_mentors", args_schema=MentorFacetSearchInput)
def search_mentors_tool(
    stack: str | None = None,
    field: str | None = None,
    mentor_type: str | None = None,
    startup: bool | None = None,
) -> str:
    """조건에 맞는 소마 멘토를 검색해 일치도(score) 높은 순으로 반환한다. 여러 조건은 AND로 적용된다.
    각 멘토에 왜 뽑혔는지 matched(일치한 스택/분야)가 포함된다.
    total_matched가 0이면 조건을 완화하고, 너무 많으면 조건을 더해 좁힌다."""
    result = search_mentors(
        stack=stack or "",
        field=field or "",
        mentor_type=mentor_type or "",
        startup=startup,
    )
    return json.dumps(result, ensure_ascii=False, indent=2)
