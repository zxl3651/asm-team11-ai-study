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
    """실제 LangGraph 실행 경로를 그대로 반영한 mermaid 를 생성한다.

    그래프 토폴로지(agent.py):
        IN → RESTORE → USERCTX → INTENT
        INTENT ─(범위 밖/우회)→ OOS → OUT
        INTENT ─(정상)→ READY
        READY ─(데이터 부족)→ BLOCK → OUT
        READY ─(처리 가능)→ AGENT
        AGENT ─(도구 필요)→ ACTION → AGENT   (루프)
        AGENT ─(답변)→ ANSWER → OUT
        AGENT ─(조회 한도/반복)→ FAILED → OUT
    """
    called_tools: list[str] = []
    for msg in messages:
        if isinstance(msg, AIMessage):
            for tool_call in msg.tool_calls or []:
                called_tools.append(tool_call["name"])
    has_tools = bool(called_tools)
    is_out_of_scope = intent == "out_of_scope"

    action_label = "도구 실행"
    if called_tools:
        # 중복 제거하되 호출 순서 유지
        seen: list[str] = []
        for name in called_tools:
            if name not in seen:
                seen.append(name)
        action_label = "도구 실행: " + ", ".join(seen)

    lines = [
        "flowchart TD",
        '  IN(["입력: 사용자 채팅 요청"])',
        '  RESTORE["대화 기억 복원"]',
        '  USERCTX["사용자 기본정보 확인"]',
        '  INTENT{"의도 분류"}',
        '  OOS["범위 밖/우회 시도 → 정중히 거절"]',
        '  READY{"데이터 준비 상태 확인"}',
        '  BLOCK["필요 데이터 미수집 안내"]',
        '  AGENT{"에이전트: 도구 호출 계획 / 답변 작성"}',
        f'  ACTION["{_mermaid_label(action_label)}"]',
        '  FAILED["조회 한도 도달 → 수집 결과로 답변 합성"]',
        '  ANSWER["답변 생성"]',
        '  OUT(["출력: 사용자 응답"])',
        "",
        "  IN --> RESTORE --> USERCTX --> INTENT",
        "  INTENT -->|범위 밖·우회 시도| OOS --> OUT",
        "  INTENT -->|소마 관련| READY",
        "  READY -->|필수 데이터 부족| BLOCK --> OUT",
        "  READY -->|처리 가능| AGENT",
        "  AGENT -->|도구 필요| ACTION --> AGENT",
        "  AGENT -->|조회 한도·반복| FAILED --> OUT",
        "  AGENT -->|답변 작성| ANSWER --> OUT",
        "",
        "  classDef active fill:#dcfce7,stroke:#16a34a,stroke-width:3px,color:#052e16;",
        "  classDef base fill:#f8fafc,stroke:#cbd5e1,stroke-width:1px,color:#334155;",
        "  classDef decision fill:#eef2ff,stroke:#6366f1,stroke-width:2px,color:#312e81;",
        "  classDef stop fill:#fef2f2,stroke:#ef4444,stroke-width:2px,color:#7f1d1d;",
        "  class IN,RESTORE,USERCTX,ANSWER,OUT base;",
        "  class INTENT,READY,AGENT decision;",
        "  class OOS,BLOCK,FAILED stop;",
        "  class ACTION base;",
    ]

    # 실제로 지나간 경로만 하이라이트
    active_nodes = ["IN", "RESTORE", "USERCTX", "INTENT", "OUT"]
    if is_out_of_scope:
        active_nodes.append("OOS")
    elif blocked_reason:
        active_nodes.extend(["READY", "BLOCK"])
    else:
        active_nodes.append("READY")
        active_nodes.append("AGENT")
        if has_tools:
            active_nodes.append("ACTION")
        active_nodes.append("ANSWER")

    lines.append(f"  class {','.join(sorted(set(active_nodes)))} active;")

    # 보조 주석
    if intent:
        lines.append(f'  INTENT_NOTE["분류된 의도: {_mermaid_label(intent)}"]:::active')
    if called_tools and not is_out_of_scope:
        steps = " → ".join(called_tools)
        lines.append(f'  TOOL_NOTE["실제 호출 순서: {_mermaid_label(steps)}"]:::active')
        detail_notes = []
        if "get_team_participant_schedule" in called_tools:
            detail_notes.append("정규화 신청자 연결 기반 팀원별 신청 일정")
        if "get_free_slots" in called_tools:
            detail_notes.append("공통 빈 시간 계산")
        if "vector_search_mentorings" in called_tools:
            detail_notes.append("벡터 후보 탐색")
        if "search_mentorings" in called_tools:
            detail_notes.append("리랭킹")
        if detail_notes:
            lines.append(f'  TOOL_DETAIL["{_mermaid_label(" → ".join(detail_notes))}"]:::active')
        if "get_team_participant_schedule" in called_tools and "get_free_slots" in called_tools:
            lines.append('  TOOL_EDGE_NOTE["get_team_participant_schedule -> get_free_slots"]:::active')
    if blocked_reason:
        lines.append(f'  BLOCK_NOTE["중단 사유: {_mermaid_label(blocked_reason)}"]:::stop')
    if data_readiness and not is_out_of_scope:
        summary = []
        for key in ("user_info", "user_calendar", "mentorings", "team_info"):
            counts = data_readiness.get(key, {})
            total = counts.get("total", 0)
            usable = int(counts.get("valid", 0) or 0) + int(counts.get("partial", 0) or 0)
            summary.append(f"{key} {usable}/{total}")
        lines.append(f'  READY_NOTE["데이터 준비 상태: {_mermaid_label(", ".join(summary))}"]:::active')

    return "\n".join(lines)
