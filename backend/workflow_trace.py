from typing import Sequence

from langchain_core.messages import AIMessage, BaseMessage


def _mermaid_label(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


def build_workflow_mermaid(
    messages: Sequence[BaseMessage],
    intent: str | None = None,
    data_readiness: dict | None = None,
    blocked_reason: str | None = None,
) -> str:
    """Render the full workflow and highlight the selected path."""
    called_tools: list[str] = []
    for msg in messages:
        if isinstance(msg, AIMessage):
            for tool_call in msg.tool_calls or []:
                called_tools.append(tool_call["name"])

    used_tools = set(called_tools)
    has_tools = bool(called_tools)

    lines = [
        "flowchart TD",
        '  IN(["Input: 사용자 채팅 요청"])',
        '  RESTORE["대화 기억 복원"]',
        '  USERCTX["사용자 기본정보 확인"]',
        '  INTENT{"LLM 의도 분류"}',
        '  READY{"데이터 준비 상태 확인"}',
        '  BLOCK["필요 데이터 미수집 안내"]',
        '  LLM{"도구 실행 계획 선택"}',
        '  DIRECT["직접 답변 경로"]',
        '  CAL["사용자 일정 조회"]',
        '  MENTORINGS["멘토링/특강 검색"]',
        '  MENTORS["멘토 검색"]',
        '  TRAINEES["연수생 검색"]',
        '  TEAM["팀 매칭 정보 조회"]',
        '  RAG["벡터 검색 / 조건 필터링 / 리랭킹"]',
        '  SCHEDULE["일정 충돌 검토"]',
        '  EVIDENCE{"근거 검증"}',
        '  MERGE["조회 결과 통합"]',
        '  ANSWER["답변 생성"]',
        '  OUT(["Output: 사용자 응답"])',
        "",
        "  IN --> RESTORE --> USERCTX --> INTENT --> READY",
        "  READY -->|필수 데이터 부족| BLOCK --> ANSWER",
        "  READY -->|처리 가능| LLM",
        "  LLM -->|도구 없이 답변| DIRECT --> ANSWER",
        "  LLM -->|일정 확인 필요| CAL --> SCHEDULE --> EVIDENCE",
        "  LLM -->|특강/멘토링 추천| MENTORINGS --> RAG --> EVIDENCE",
        "  LLM -->|멘토 후보 추천| MENTORS --> EVIDENCE",
        "  LLM -->|동료/팀원 탐색| TRAINEES --> EVIDENCE",
        "  LLM -->|우리 팀 질문| TEAM --> EVIDENCE",
        "  EVIDENCE --> MERGE --> ANSWER --> OUT",
        "",
        "  classDef active fill:#dcfce7,stroke:#16a34a,stroke-width:3px,color:#052e16;",
        "  classDef base fill:#f8fafc,stroke:#cbd5e1,stroke-width:1px,color:#334155;",
        "  classDef decision fill:#eef2ff,stroke:#6366f1,stroke-width:2px,color:#312e81;",
        "  class IN,RESTORE,USERCTX,INTENT,READY,ANSWER,OUT active;",
        "  class DIRECT,BLOCK,LLM,CAL,MENTORINGS,MENTORS,TRAINEES,TEAM,RAG,SCHEDULE,EVIDENCE,MERGE base;",
        "  class INTENT,READY,LLM,EVIDENCE decision;",
    ]

    active_nodes = []
    if blocked_reason:
        active_nodes.append("BLOCK")
    else:
        active_nodes.append("LLM")
    if "get_user_calendar" in used_tools:
        active_nodes.extend(["CAL", "SCHEDULE", "EVIDENCE", "MERGE"])
    if "search_mentorings" in used_tools:
        active_nodes.extend(["MENTORINGS", "RAG", "EVIDENCE", "MERGE"])
    if "search_mentors" in used_tools:
        active_nodes.extend(["MENTORS", "EVIDENCE", "MERGE"])
    if "search_trainees" in used_tools:
        active_nodes.extend(["TRAINEES", "EVIDENCE", "MERGE"])
    if "get_team_info" in used_tools:
        active_nodes.extend(["TEAM", "EVIDENCE", "MERGE"])
    if not has_tools and not blocked_reason:
        active_nodes.append("DIRECT")

    if active_nodes:
        lines.append(f"  class {','.join(sorted(set(active_nodes)))} active;")

    if called_tools:
        steps = " -> ".join(called_tools)
        lines.extend([
            "",
            f'  NOTE["실제 호출 순서: {_mermaid_label(steps)}"]',
            "  NOTE:::active",
        ])
    if intent:
        lines.extend([
            "",
            f'  INTENT_NOTE["분류된 의도: {_mermaid_label(intent)}"]',
            "  INTENT_NOTE:::active",
        ])
    if blocked_reason:
        lines.extend([
            "",
            f'  BLOCK_NOTE["중단 사유: {_mermaid_label(blocked_reason)}"]',
            "  BLOCK_NOTE:::active",
        ])
    if data_readiness:
        summary = []
        for key in ("user_info", "user_calendar", "mentorings", "team_info"):
            counts = data_readiness.get(key, {})
            total = counts.get("total", 0)
            usable = int(counts.get("valid", 0) or 0) + int(counts.get("partial", 0) or 0)
            summary.append(f"{key} {usable}/{total}")
        lines.extend([
            "",
            f'  READY_NOTE["데이터 준비 상태: {_mermaid_label(", ".join(summary))}"]',
            "  READY_NOTE:::active",
        ])

    return "\n".join(lines)
