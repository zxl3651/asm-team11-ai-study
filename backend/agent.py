import json
import re
import uuid

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph

from agent_intent import extract_user_message, fallback_intent, normalize_intent, parse_json_object, readiness_block_reason
from agent_prompts import BASE_SYSTEM_PROMPT, INTENT_CLASSIFICATION_PROMPT, build_intent_instruction, build_user_info_prompt
from agent_state import AgentState, TOOL_STATUS_LABELS
from tools import LATEST_TOOLS, report_status, status_callback_var
from workflow_trace import build_workflow_mermaid


def _is_simple_team_info_query(user_message: str) -> bool:
    text = user_message.strip().lower()
    if any(keyword in text for keyword in ["시간", "일정", "스케줄", "회의", "빈 시간", "가능한 시간", "추천", "특강", "멘토링"]):
        return False
    return any(keyword in text for keyword in ["내 팀", "우리 팀", "팀 알려", "팀 정보", "팀원이", "팀원 ", "프로젝트"])


def _is_personal_fixed_meeting_recommendation(user_message: str) -> bool:
    text = user_message.strip().lower()
    has_personal_scope = any(keyword in text for keyword in ["내 일정", "나의 일정", "내 수강", "수강 이력", "내가 이미 신청", "내가 신청"])
    has_fixed_meeting = "정기 회의" in text or "고정 회의" in text or ("회의" in text and ("제외" in text or "피해서" in text))
    has_recommendation = any(keyword in text for keyword in ["특강", "멘토링", "추천", "골라"])
    return has_personal_scope and has_fixed_meeting and has_recommendation


def _target_trainee_name_from_query(user_message: str) -> str | None:
    text = user_message.strip()
    match = re.search(r"([가-힣]{2,5})\s*연수생(?:의|이|은|는|을|를|에\s*대해서)?\s*팀", text)
    if match:
        return match.group(1)
    match = re.search(r"([가-힣]{2,5})\s*연수생의?\s*소속\s*팀", text)
    if match:
        return match.group(1)
    return None


def _target_trainee_info_name_from_query(user_message: str) -> str | None:
    text = user_message.strip()
    if _target_trainee_name_from_query(text):
        return None
    patterns = [
        r"([가-힣]{2,5})\s*연수생(?:의|이|은|는|을|를)?\s*(?:정보|프로필|기본\s*정보)",
        r"([가-힣]{2,5})\s*연수생(?:에\s*대해서|에\s*관해서)\s*(?:알려|궁금|정보)",
        r"([가-힣]{2,5})\s*연수생.*(?:알려줘|알고\s*싶어)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1)
    return None


def _is_team_meeting_availability_query(user_message: str) -> bool:
    text = user_message.strip().lower()
    if (
        any(keyword in text for keyword in ["내 일정", "나의 일정", "내 수강", "수강 이력", "내가 이미 신청", "내가 신청"])
        and any(keyword in text for keyword in ["특강", "멘토링", "추천", "골라"])
        and ("정기 회의" in text or "고정 회의" in text or ("회의" in text and ("제외" in text or "피해서" in text)))
    ):
        return False
    has_team_scope = (
        any(keyword in text for keyword in ["우리 팀", "팀 정보를", "팀 정보", "팀원", "소속 팀"])
        or any(keyword in text for keyword in ["팀에", "팀의", "팀이", "팀은", "팀에서"])
        or (_target_trainee_name_from_query(user_message) is not None and "팀" in text)
    )
    has_meeting = "회의" in text
    has_availability = any(keyword in text for keyword in ["가능", "빈 시간", "후보", "시간대", "요일"])
    return has_team_scope and has_meeting and has_availability


def _current_turn_messages(messages: list[BaseMessage]) -> list[BaseMessage]:
    last_human_index = 0
    for idx, msg in enumerate(messages):
        if isinstance(msg, HumanMessage):
            last_human_index = idx
    return messages[last_human_index:]


def _has_tool_call(messages: list[BaseMessage], tool_name: str) -> bool:
    for msg in messages:
        if isinstance(msg, AIMessage):
            for tool_call in getattr(msg, "tool_calls", []) or []:
                if tool_call.get("name") == tool_name:
                    return True
    return False


def _tool_call_signature(tool_call: dict) -> str:
    return json.dumps({
        "name": tool_call.get("name"),
        "args": tool_call.get("args") or {},
    }, ensure_ascii=False, sort_keys=True)


def _has_repeated_tool_call(messages: list[BaseMessage], latest_message: AIMessage) -> bool:
    previous_signatures = set()
    for msg in messages[:-1]:
        if isinstance(msg, AIMessage):
            for tool_call in getattr(msg, "tool_calls", []) or []:
                previous_signatures.add(_tool_call_signature(tool_call))
    for tool_call in getattr(latest_message, "tool_calls", []) or []:
        if _tool_call_signature(tool_call) in previous_signatures:
            return True
    return False


def _team_member_names_from_tool_messages(messages: list[BaseMessage]) -> list[str]:
    for msg in reversed(messages):
        if not isinstance(msg, ToolMessage):
            continue
        content = msg.content or ""
        if '"team_info"' not in content:
            continue
        try:
            parsed = json.loads(content)
        except Exception:
            continue
        teams = parsed.get("team_info") or []
        if not teams:
            continue
        team = teams[0]
        names = []
        leader = team.get("leader")
        if leader:
            names.append(leader)
        members = team.get("members") or []
        if isinstance(members, list):
            names.extend(members)
        deduped = []
        for name in names:
            if name and name not in deduped:
                deduped.append(name)
        return deduped
    return []


def _team_name_from_tool_messages(messages: list[BaseMessage]) -> str | None:
    for msg in reversed(messages):
        if not isinstance(msg, ToolMessage):
            continue
        content = msg.content or ""
        if '"team_info"' not in content:
            continue
        try:
            parsed = json.loads(content)
        except Exception:
            continue
        teams = parsed.get("team_info") or []
        if teams:
            return teams[0].get("teamName") or None
    return None


def _json_tool_payloads(messages: list[BaseMessage]) -> list[dict]:
    payloads: list[dict] = []
    for msg in messages:
        if not isinstance(msg, ToolMessage):
            continue
        try:
            parsed = json.loads(msg.content or "")
        except Exception:
            continue
        if isinstance(parsed, dict):
            payloads.append(parsed)
    return payloads


def _current_week_range_from_messages(messages: list[BaseMessage]) -> tuple[str, str]:
    for msg in messages:
        if not isinstance(msg, SystemMessage):
            continue
        content = msg.content or ""
        match = re.search(r"이번 주 범위:\s*(\d{4}-\d{2}-\d{2}).*?~\s*(\d{4}-\d{2}-\d{2})", content, re.S)
        if match:
            return match.group(1), match.group(2)

    from datetime import datetime, timedelta
    now = datetime.now()
    start_of_week = now - timedelta(days=now.weekday())
    end_of_week = start_of_week + timedelta(days=6)
    return start_of_week.strftime("%Y-%m-%d"), end_of_week.strftime("%Y-%m-%d")


def _tool_call_message(name: str, args: dict) -> dict:
    return {
        "name": name,
        "args": args,
        "id": f"call_{uuid.uuid4().hex[:12]}",
        "type": "tool_call",
    }


def _fixed_meeting_recommendation_tool_message(messages: list[BaseMessage]) -> AIMessage:
    start_date, end_date = _current_week_range_from_messages(messages)
    user_query = extract_user_message(messages)
    fixed_block = {
        "weekdays": ["월", "화", "수", "목", "금"],
        "start": "10:00",
        "end": "12:00",
        "title": "팀 정기 회의",
    }
    return AIMessage(
        content="",
        tool_calls=[
            _tool_call_message("get_participant_registrations", {
                "participant_name": "me",
                "start_date": start_date,
                "end_date": end_date,
            }),
            _tool_call_message("search_mentorings", {
                "start_date": start_date,
                "end_date": end_date,
                "status": "접수중",
                "query": user_query,
            }),
            _tool_call_message("get_free_slots", {
                "user_name": "me",
                "start_date": start_date,
                "end_date": end_date,
                "working_hour_start": 9,
                "working_hour_end": 22,
                "recurring_busy_blocks": [fixed_block],
            }),
        ],
    )


def _team_info_tool_message(user_message: str | None = None) -> AIMessage:
    args = {}
    trainee_name = _target_trainee_name_from_query(user_message or "")
    if trainee_name:
        args["trainee_name"] = trainee_name
    return AIMessage(
        content="",
        tool_calls=[_tool_call_message("get_team_info", args)],
    )


def _team_free_slots_tool_message(messages: list[BaseMessage]) -> AIMessage:
    start_date, end_date = _current_week_range_from_messages(messages)
    team_member_names = _team_member_names_from_tool_messages(messages)
    team_name = _team_name_from_tool_messages(messages)
    args = {
        "start_date": start_date,
        "end_date": end_date,
        "meeting_duration_hours": 2.0,
        "working_hour_start": 9,
        "working_hour_end": 22,
        "user_names": team_member_names,
    }
    if team_name:
        args["team_name"] = team_name
        args["include_team_shared_mentorings"] = True
    return AIMessage(
        content="",
        tool_calls=[
            _tool_call_message("get_team_participant_schedule", {
                "team_name": team_name,
                "user_names": team_member_names,
                "start_date": start_date,
                "end_date": end_date,
            }),
            _tool_call_message("get_free_slots", args),
        ],
    )


def _trainee_search_tool_message(user_message: str) -> AIMessage:
    trainee_name = _target_trainee_info_name_from_query(user_message)
    args = {"name": trainee_name} if trainee_name else {}
    return AIMessage(
        content="",
        tool_calls=[_tool_call_message("search_trainees", args)],
    )


def _contains_raw_tool_call_text(content: str | None) -> bool:
    if not content:
        return False
    return "<|tool_call:" in content or "<tool_call" in content or "tool_call:begin" in content


# solar-pro3(추론 모델)가 최종 답변 대신 자기 사고 과정을 content에 내보내는 경우가
# 간헐적으로 있다(예: "We need to respond..."). 한국어 전용 서비스이므로 영어 메타-추론
# 문구로 시작하면 누출로 간주한다.
_REASONING_LEAK_PREFIXES = (
    "we need", "we have", "we should", "we can", "we must", "we'll", "we are",
    "the user", "user wants", "user is asking", "user asked",
    "let me", "let's", "first,", "first ", "i need", "i should", "i will", "i'll", "i have to",
    "okay,", "ok,", "alright,", "so the", "so,", "now,", "now i", "based on the",
    "looking at", "to answer", "the question", "the assistant", "as an ai", "we want",
)


def _looks_like_reasoning_leak(content: str | None) -> bool:
    if not content:
        return False
    head = content.strip().lower()
    return any(head.startswith(prefix) for prefix in _REASONING_LEAK_PREFIXES)


def _latest_visual_schedule_block(messages: list[BaseMessage]) -> str:
    for payload in reversed(_json_tool_payloads(messages)):
        block = payload.get("visual_schedule_block")
        if isinstance(block, str) and block.strip().startswith("```schedule"):
            return block.strip()
    return ""


def _fixed_recommendation_answer_from_tools(messages: list[BaseMessage]) -> str:
    from datetime import datetime

    payloads = _json_tool_payloads(messages)
    registrations_payload = next((p for p in reversed(payloads) if "registrations" in p), {})
    search_payload = next((p for p in reversed(payloads) if "items" in p), {})
    registered_ids = {
        str(item.get("id", ""))
        for item in registrations_payload.get("registrations", []) or []
        if item.get("id")
    }

    def parse_dt(value: str | None):
        if not value:
            return None
        try:
            return datetime.fromisoformat(value)
        except Exception:
            return None

    def overlaps_fixed_meeting(start_dt, end_dt) -> bool:
        if not start_dt or not end_dt or start_dt.weekday() >= 5:
            return False
        fixed_start = start_dt.replace(hour=10, minute=0, second=0, microsecond=0)
        fixed_end = start_dt.replace(hour=12, minute=0, second=0, microsecond=0)
        return max(start_dt, fixed_start) < min(end_dt, fixed_end)

    candidates = []
    for item in search_payload.get("items", []) or []:
        item_id = str(item.get("id", ""))
        if item_id and item_id in registered_ids:
            continue
        if item.get("status") != "접수중":
            continue
        start_dt = parse_dt(item.get("startAt"))
        end_dt = parse_dt(item.get("endAt"))
        if overlaps_fixed_meeting(start_dt, end_dt):
            continue
        remaining = item.get("remaining_spots")
        if remaining is None:
            max_p = item.get("max_participants", 0) or 0
            cur_p = item.get("current_participants", 0) or 0
            remaining = max_p - cur_p if max_p else None
        if remaining is not None and remaining <= 0:
            continue
        candidates.append((start_dt or datetime.max, item, remaining))

    candidates.sort(key=lambda entry: entry[0])
    selected = candidates[:7]
    lines = [
        "제외 기준",
        "",
        "- 정규화된 신청자 명단 기준으로 이미 신청한 멘토링/특강은 제외했습니다.",
        "- 평일 10:00~12:00 고정 회의 시간과 겹치는 후보는 제외했습니다.",
        "- 접수중이고 잔여 인원이 있는 이번 주 후보만 남겼습니다.",
        "",
        "추천 후보",
    ]
    if not selected:
        lines.extend([
            "",
            "이번 주 조건에 맞는 접수중 특강/멘토링 후보를 찾지 못했습니다.",
        ])
    else:
        lines.append("")
        for _, item, remaining in selected:
            author = item.get("mentor_name") or item.get("author") or "미기재"
            remaining_text = f"{remaining}자리" if remaining is not None else "정원 정보 미기재"
            lines.append(
                f"- {item.get('dateStr', '날짜 미기재')} {item.get('timeRangeStr', '시간 미기재')} · "
                f"{item.get('title', '제목 미기재')} · {author} · {remaining_text}"
            )
        lines.extend([
            "",
            "추천 근거",
            "",
            "- 일정 충돌 여부는 구조화된 시작/종료 시각 기준으로 판단했습니다.",
            "- 관심사 매칭은 질문 키워드와 벡터 검색 후보를 보조 근거로 사용했습니다.",
        ])
    visual_schedule_block = _latest_visual_schedule_block(messages)
    if visual_schedule_block:
        lines.extend(["", "주간 가용 시간 시각화", "", visual_schedule_block])
    return "\n".join(lines).strip()


def _trainee_info_answer_from_tools(messages: list[BaseMessage], user_message: str) -> str:
    payloads = _json_tool_payloads(messages)
    result = next((payload for payload in reversed(payloads) if "trainees" in payload), {})
    trainees = result.get("trainees") or []
    target_name = _target_trainee_info_name_from_query(user_message)

    if not trainees:
        if target_name:
            return f"동기화된 연수생 목록에서 `{target_name}` 연수생 정보를 찾지 못했습니다."
        return "조건에 맞는 연수생 정보를 찾지 못했습니다."

    trainee = trainees[0]
    lines = ["연수생 정보", ""]
    lines.append(f"- 이름: {trainee.get('name') or '미기재'}")
    roles = trainee.get("roles") or []
    if roles:
        lines.append(f"- 역할: {', '.join(roles)}")
    stacks = trainee.get("stacks") or []
    if stacks:
        lines.append(f"- 기술 스택: {', '.join(stacks)}")
    if trainee.get("team_status"):
        lines.append(f"- 팀 상태: {trainee.get('team_status')}")
    if trainee.get("email"):
        lines.append(f"- 이메일: {trainee.get('email')}")
    if len(trainees) > 1:
        lines.extend([
            "",
            f"동명이인 또는 부분 일치 후보가 {len(trainees)}명 있습니다. 가장 가까운 후보 1명을 먼저 표시했습니다.",
        ])
    return "\n".join(lines).strip()


def _compact_team_meeting_candidates(free_slots_result: dict, max_representatives: int = 5) -> list[str]:
    windows = free_slots_result.get("meeting_windows") or []
    if not windows:
        return ["이번 주 조건에서 2시간 연속으로 모두 비는 후보를 찾지 못했습니다."]

    representatives = []
    seen_dates = set()
    for window in windows:
        date = window.get("date")
        if date in seen_dates:
            continue
        seen_dates.add(date)
        representatives.append(
            f"{window.get('weekday')}({date}) {window.get('start')}~{window.get('end')}"
        )
        if len(representatives) >= max_representatives:
            break

    if len(windows) > len(representatives):
        return [
            f"{', '.join(representatives)} 등 총 {len(windows)}개 후보가 있습니다.",
            "전체 가능/불가 구간은 아래 주간 캘린더에서 확인하세요.",
        ]
    return [f"{', '.join(representatives)} 후보가 있습니다."]


def _compact_free_slot_ranges(free_slots_result: dict, max_days: int = 7) -> list[str]:
    schedule = free_slots_result.get("schedule") or []
    lines = []
    for day in schedule[:max_days]:
        ranges = day.get("free_slots") or []
        if not ranges:
            continue
        range_text = ", ".join(f"{slot.get('start')}~{slot.get('end')}" for slot in ranges[:3])
        more = " 등" if len(ranges) > 3 else ""
        lines.append(f"- {day.get('weekday')}({day.get('date')}): {range_text}{more}")
    return lines


def _team_meeting_answer_from_tools(messages: list[BaseMessage]) -> str:
    payloads = _json_tool_payloads(messages)
    free_slots_result = next((payload for payload in reversed(payloads) if "meeting_windows" in payload), {})
    team_schedule_payload = next((payload for payload in reversed(payloads) if payload.get("by_member") and payload.get("members")), {})
    team_payload = next((payload for payload in reversed(payloads) if payload.get("team_info")), {})
    team = (team_payload.get("team_info") or [{}])[0]

    team_name = team.get("teamName") or "미기재"
    leader = team.get("leader") or "미기재"
    members = team.get("members") or []
    if isinstance(members, str):
        members_text = members
    else:
        members_text = ", ".join(members) if members else "미기재"
    mentor = team.get("mentorName") or team.get("mentor") or "미기재"
    project = team.get("projectName") or "미기재"

    coverage = free_slots_result.get("calendar_coverage") or []
    coverage_lines = []
    for item in coverage:
        coverage_lines.append(f"- {item.get('user_name')}: 신청 일정 {item.get('active_event_count', 0)}건")

    member_schedule_lines = []
    by_member = team_schedule_payload.get("by_member") or {}
    if isinstance(by_member, dict):
        for member_name, events in by_member.items():
            event_list = events or []
            if not event_list:
                member_schedule_lines.append(f"- {member_name}: 신청 일정 0건")
                continue
            compact_events = []
            for event in event_list[:3]:
                compact_events.append(
                    f"{event.get('dateStr', '날짜 미기재')} {event.get('timeRangeStr', '시간 미기재')} {event.get('title', '제목 미기재')}"
                )
            more_count = max(0, len(event_list) - len(compact_events))
            suffix = f" 외 {more_count}건" if more_count else ""
            member_schedule_lines.append(f"- {member_name}: {len(event_list)}건 · {' / '.join(compact_events)}{suffix}")

    lines = [
        "팀 정보",
        "",
        f"- 팀명: {team_name}",
        f"- 팀장: {leader}",
        f"- 팀원: {members_text}",
        f"- 전담 멘토: {mentor}",
        f"- 프로젝트: {project}",
        "",
        "계산 기준",
        "",
        "- 개인 접수내역이나 브라우저 개인 시간표는 사용하지 않았습니다.",
        "- 정규화된 멘토링/특강 신청자 명단에서 팀원 이름이 확인된 일정만 불가 시간으로 처리했습니다.",
        "- 어느 한 명이라도 신청한 멘토링/특강이 있는 시간은 팀 회의 불가 시간으로 계산했습니다.",
    ]
    if member_schedule_lines:
        lines.extend(["", "팀원별 신청 일정 반영", "", *member_schedule_lines])
    elif coverage_lines:
        lines.extend(["", "팀원별 신청 일정 반영", "", *coverage_lines])

    lines.extend(["", "가능 후보"])
    lines.extend(["", *_compact_team_meeting_candidates(free_slots_result)])

    free_slot_ranges = _compact_free_slot_ranges(free_slots_result)
    if free_slot_ranges:
        lines.extend(["", "넓은 가능 구간", "", *free_slot_ranges])

    visual_schedule_block = free_slots_result.get("visual_schedule_block") or _latest_visual_schedule_block(messages)
    if visual_schedule_block:
        lines.extend(["", "주간 캘린더", "", visual_schedule_block.strip()])
    return "\n".join(lines).strip()


def create_agent_graph(api_key: str):
    llm = ChatOpenAI(
        model="solar-pro3",
        api_key=api_key,
        base_url="https://api.upstage.ai/v1",
        temperature=0,
    )
    llm_with_tools = llm.bind_tools(LATEST_TOOLS)

    def classify_intent(state: AgentState):
        user_message = extract_user_message(state["messages"])
        report_status("요청 유형을 분류하고 있어요...")

        intent = fallback_intent(user_message)
        try:
            response = llm.invoke([
                SystemMessage(content=INTENT_CLASSIFICATION_PROMPT),
                HumanMessage(content=user_message),
            ])
            parsed = parse_json_object(response.content)
            intent = normalize_intent(parsed.get("intent") if parsed else None, user_message)
        except Exception:
            intent = fallback_intent(user_message)
        if _is_simple_team_info_query(user_message):
            intent = "team_info"
        elif _target_trainee_info_name_from_query(user_message):
            intent = "trainee_search"
        elif _is_personal_fixed_meeting_recommendation(user_message):
            intent = "lecture_recommendation"
        elif _is_team_meeting_availability_query(user_message):
            intent = "schedule_check"

        report_status(f"처리 유형을 '{intent}' 경로로 분류했어요...")
        return {"intent": intent}

    def out_of_scope_response(state: AgentState):
        report_status("소마 연수 정보 범위를 벗어난 요청으로 판단했어요...")
        return {
            "messages": [
                AIMessage(
                    content=(
                        "저는 소프트웨어 마에스트로 연수 정보(멘토·멘토링·특강·동료 연수생·팀·일정)만 "
                        "도와드릴 수 있어요. 소마 관련해서 무엇을 도와드릴까요?"
                    )
                )
            ]
        }

    def check_data_readiness(state: AgentState):
        from database import db
        from agent_intent import readiness_warning_context

        report_status("필요한 수집 데이터가 준비됐는지 확인하고 있어요...")
        readiness = db.get_data_readiness()
        blocked_reason = readiness_block_reason(state.get("intent", "general"), readiness)
        warning_context = readiness_warning_context(state.get("intent", "general"), readiness)

        if blocked_reason:
            report_status("필수 데이터가 부족해 안내 응답으로 전환하고 있어요...")
        else:
            if warning_context:
                report_status("일부 동기화되지 않은 데이터를 확인했어요...")
            else:
                report_status("필요 데이터 확인을 마쳤어요...")

        return {
            "data_readiness": readiness,
            "blocked_reason": blocked_reason,
            "warning_context": warning_context,
        }

    def data_unavailable_response(state: AgentState):
        reason = state.get("blocked_reason", "필요 데이터가 아직 준비되지 않았습니다.")
        return {
            "messages": [
                AIMessage(
                    content=(
                        f"{reason}\n\n"
                        "확장 프로그램에서 **포털 데이터 동기화**를 먼저 실행한 뒤 다시 질문해 주세요."
                    )
                )
            ]
        }

    def call_model(state: AgentState):
        messages = state["messages"]
        intent = state.get("intent", "general")
        warning_context = state.get("warning_context", "")
        user_message = extract_user_message(messages)
        current_turn = _current_turn_messages(messages)
        is_fixed_meeting_recommendation = _is_personal_fixed_meeting_recommendation(user_message)
        is_team_meeting_availability = _is_team_meeting_availability_query(user_message)
        is_named_trainee_info = _target_trainee_info_name_from_query(user_message) is not None
        report_status("요청 내용을 분석하고 있어요...")

        # 현재 턴에서 get_free_slots 결과가 있을 때만 일정 조율 경로로 보강한다.
        # 이전 대화의 긴 일정 답변이 단순 팀 조회를 오염시키지 않도록 한다.
        has_free_slots_tool = any(
            isinstance(m, ToolMessage) and m.content and '"visual_schedule_block"' in m.content
            for m in current_turn
        )
        if has_free_slots_tool and intent not in ("schedule_check", "lecture_recommendation"):
            intent = "schedule_check"

        instruction_text = build_intent_instruction(intent, state.get("data_readiness"))
        if warning_context:
            instruction_text += f"\n\n## [중요] 데이터 누락 경고 및 가이드\n{warning_context}"
        if is_team_meeting_availability:
            instruction_text += (
                "\n\n## [중요] 팀 회의 가능 시간 계산 범위\n"
                "현재 요청은 팀원 전체 공통 가능 시간 계산입니다. "
                "`get_team_info`로 확인한 소속 팀의 팀장과 팀원 전원을 `get_free_slots(user_names=[...])`에 넣어야 합니다. "
                "`get_free_slots(user_name='me')` 또는 `user_names`가 없는 단일 사용자 계산 결과를 팀 회의 후보로 제시하지 마세요. "
                "개인 접수내역이나 개인 시간표 부족을 이유로 중단하지 마세요. "
                "멘토링/특강 상세 신청자 명단에서 확인된 팀원별 신청 일정만 차단 시간으로 보고, 해당 신청 일정이 0건인 팀원은 빈 일정으로 처리하세요."
            )
        if is_fixed_meeting_recommendation:
            instruction_text += (
                "\n\n## [중요] 개인 일정 기준 고정 회의 제외 특강 추천\n"
                "현재 요청은 팀원 전체 공통 시간 조율이 아닙니다. `get_team_info`를 호출하지 마세요. "
                "멘토링/특강 상세 신청자 명단 기준 본인의 신청 일정, 평일 10:00~12:00 고정 회의 차단 시간, "
                "신청 가능한 특강/멘토링 후보만 사용해 답변하세요. "
                "도구는 `get_participant_registrations(participant_name='me')`, `search_mentorings(status='접수중')`, "
                "`get_free_slots(user_name='me', recurring_busy_blocks=[...])`만 필요합니다."
            )
        if any(
            isinstance(m, ToolMessage) and "team_member_calendar_unavailable" in (m.content or "")
            for m in messages
        ):
            if is_team_meeting_availability:
                instruction_text += (
                    "\n\n## [중요] 과거 방식의 팀원 캘린더 조회 불가 결과 무시\n"
                    "이전 대화나 구버전 도구 결과의 `team_member_calendar_unavailable`을 현재 답변 기준으로 삼지 마세요. "
                    "현재 정책은 개인 일정 데이터가 아니라 멘토링/특강 상세 신청자 명단 기준 신청 일정만 사용해 팀 가용 시간을 계산하는 것입니다."
                )
            else:
                instruction_text += (
                    "\n\n## [중요] 과거 방식의 팀원 캘린더 조회 불가 결과 무시\n"
                    "고정 팀 회의 시간을 제외한 개인 특강 추천 요청에는 팀원 캘린더가 필요하지 않습니다. "
                    "멘토링/특강 상세 신청자 명단 기준 본인의 기존 신청 일정과 질문에 명시된 고정 제외 시간만 사용하세요."
                )
        if any(
            isinstance(m, ToolMessage) and '"availability_scope": "current_user_only"' in (m.content or "")
            for m in messages
        ) and ("팀" in user_message and ("회의" in user_message or "모두" in user_message or "우리" in user_message)):
            instruction_text += (
                "\n\n## [중요] 본인 일정 기준 결과를 팀 전체 결과로 오인 금지\n"
                "`availability_scope=current_user_only`인 빈 시간 결과는 로그인한 본인 일정 기준입니다. "
                "사용자가 팀 회의 가능 시간을 물었다면 팀원 전체 공통 가능 시간으로 확정하지 마세요. "
                "팀원 전체 이름으로 `get_free_slots(user_names=[...])`를 다시 호출해 멘토링/특강 신청 일정 기반으로 계산하세요."
            )

        if messages and isinstance(messages[0], SystemMessage):
            merged_content = messages[0].content + "\n\n" + instruction_text
            model_messages = [SystemMessage(content=merged_content), *messages[1:]]
        else:
            model_messages = [SystemMessage(content=instruction_text), *messages]

        if is_fixed_meeting_recommendation and not any(isinstance(m, AIMessage) and getattr(m, "tool_calls", None) for m in current_turn):
            response = _fixed_meeting_recommendation_tool_message(model_messages)
            report_status("필요한 조회 경로를 선택했어요: get_participant_registrations, search_mentorings, get_free_slots")
            return {"messages": [response], "intent": intent}

        if is_team_meeting_availability and not any(isinstance(m, AIMessage) and getattr(m, "tool_calls", None) for m in current_turn):
            response = _team_info_tool_message(user_message)
            report_status("필요한 조회 경로를 선택했어요: get_team_info")
            return {"messages": [response], "intent": intent}

        if (
            intent == "team_info"
            and _target_trainee_name_from_query(user_message)
            and not any(isinstance(m, AIMessage) and getattr(m, "tool_calls", None) for m in current_turn)
        ):
            response = _team_info_tool_message(user_message)
            report_status("필요한 조회 경로를 선택했어요: get_team_info")
            return {"messages": [response], "intent": intent}

        if is_named_trainee_info and not any(isinstance(m, AIMessage) and getattr(m, "tool_calls", None) for m in current_turn):
            response = _trainee_search_tool_message(user_message)
            report_status("필요한 조회 경로를 선택했어요: search_trainees")
            return {"messages": [response], "intent": "trainee_search"}

        if (
            is_team_meeting_availability
            and _has_tool_call(current_turn, "get_team_info")
            and not _has_tool_call(current_turn, "get_free_slots")
        ):
            response = _team_free_slots_tool_message(model_messages + current_turn)
            report_status("필요한 조회 경로를 선택했어요: get_free_slots")
            return {"messages": [response], "intent": intent}

        if is_team_meeting_availability and _has_tool_call(current_turn, "get_free_slots"):
            response = AIMessage(content=_team_meeting_answer_from_tools(current_turn))
        elif is_named_trainee_info and _has_tool_call(current_turn, "search_trainees"):
            response = AIMessage(content=_trainee_info_answer_from_tools(current_turn, user_message))
        elif is_fixed_meeting_recommendation and (
            (
                _has_tool_call(current_turn, "get_participant_registrations")
                or _has_tool_call(current_turn, "get_user_calendar")
            )
            and _has_tool_call(current_turn, "search_mentorings")
            and _has_tool_call(current_turn, "get_free_slots")
        ):
            response = AIMessage(content=_fixed_recommendation_answer_from_tools(current_turn))
        elif intent == "team_info" and _has_tool_call(current_turn, "get_team_info"):
            team_info_instruction = SystemMessage(
                content=(
                    "현재 질문은 단순 팀 정보 조회입니다. 추가 도구를 호출하지 말고, "
                    "이미 조회된 팀 정보만 사용해 팀명, 팀장, 팀원, 전담 멘토, 프로젝트명을 간결하게 답하세요. "
                    "캘린더, 일정, 가능 시간, 요약/추천 섹션은 출력하지 마세요."
                )
            )
            response = llm.invoke([*model_messages, team_info_instruction])
        else:
            allowed_tools = LATEST_TOOLS
            if intent == "team_info":
                allowed_tools = [tool for tool in LATEST_TOOLS if tool.name == "get_team_info"]
            elif intent == "trainee_search":
                allowed_tools = [tool for tool in LATEST_TOOLS if tool.name == "search_trainees"]
            elif intent == "mentor_recommendation":
                # 멘토 추천은 멘토/연수생 검색 도구만 사용하게 제한해
                # 일정·회의 도구로 새지 않고 빠르게 답변으로 수렴하도록 한다.
                allowed_names = {"search_mentors", "list_facets", "search_trainees", "vector_search_mentorings"}
                allowed_tools = [tool for tool in LATEST_TOOLS if tool.name in allowed_names]
            elif is_fixed_meeting_recommendation:
                allowed_names = {"get_participant_registrations", "get_user_calendar", "search_mentorings", "get_free_slots"}
                called = {
                    tool_call.get("name")
                    for msg in current_turn
                    if isinstance(msg, AIMessage)
                    for tool_call in (getattr(msg, "tool_calls", []) or [])
                }
                if ("get_participant_registrations" in called or "get_user_calendar" in called) and "search_mentorings" in called:
                    allowed_names = {"get_free_slots"}
                allowed_tools = [tool for tool in LATEST_TOOLS if tool.name in allowed_names]
            elif is_team_meeting_availability:
                called = {
                    tool_call.get("name")
                    for msg in current_turn
                    if isinstance(msg, AIMessage)
                    for tool_call in (getattr(msg, "tool_calls", []) or [])
                }
                allowed_names = {"get_team_info"} if "get_team_info" not in called else {"get_team_participant_schedule", "get_free_slots"}
                allowed_tools = [tool for tool in LATEST_TOOLS if tool.name in allowed_names]
            response = llm.bind_tools(allowed_tools).invoke(model_messages)
        if _contains_raw_tool_call_text(response.content):
            if is_fixed_meeting_recommendation:
                has_required_results = (
                    _has_tool_call(current_turn, "get_participant_registrations")
                    and _has_tool_call(current_turn, "search_mentorings")
                    and _has_tool_call(current_turn, "get_free_slots")
                )
                if has_required_results:
                    response = AIMessage(content=_fixed_recommendation_answer_from_tools(current_turn))
                else:
                    response = _fixed_meeting_recommendation_tool_message(model_messages)
            elif is_team_meeting_availability:
                if _has_tool_call(current_turn, "get_team_info"):
                    response = _team_free_slots_tool_message(model_messages + current_turn)
                else:
                    response = _team_info_tool_message(user_message)
            else:
                response = AIMessage(content="요청 처리 중 내부 조회 형식이 응답에 섞였습니다. 다시 질문해 주세요.")

        # 추론 모델이 최종 답변 대신 (1) 사고 과정을 노출하거나 (2) 빈 content 를
        # 반환하는 경우가 간헐적으로 있다. 수집된 도구 결과를 평문 컨텍스트로 추출해
        # '추론 금지·한국어 최종 답변만' 지시로 한 번 더 합성한다.
        _blank_final = not (response.content or "").strip()
        if not response.tool_calls and (_blank_final or _looks_like_reasoning_leak(response.content)):
            tool_blocks = [str(m.content) for m in current_turn if isinstance(m, ToolMessage) and m.content]
            if tool_blocks:
                report_status("답변을 다시 정리하고 있어요...")
                base_system = messages[0].content if messages and isinstance(messages[0], SystemMessage) else ""
                resynth_system = SystemMessage(
                    content=(
                        base_system + "\n\n" + instruction_text + "\n\n"
                        "## [중요] 출력 형식 엄수\n"
                        "사고 과정/추론/영어 메타설명을 절대 출력하지 마세요. "
                        "아래 조회 결과(JSON)만 근거로 사용자 질문에 대한 **최종 한국어 답변만** 작성하세요. "
                        "'We need to', 'The user', 'Let me' 같은 도입부 없이 곧바로 답변 본문으로 시작하세요."
                    )
                )
                resynth_human = HumanMessage(
                    content=f"[질문]\n{user_message}\n\n[조회 결과 — 이 데이터만 사용]\n" + "\n\n---\n\n".join(tool_blocks)
                )
                try:
                    retry = llm.invoke([resynth_system, resynth_human])
                    if (retry.content or "").strip() and not _looks_like_reasoning_leak(retry.content):
                        response = AIMessage(content=retry.content)
                except Exception as resynth_err:
                    print(f"⚠️ [Agent Core] 추론 누출 재합성 실패: {resynth_err}")

        # 재합성까지 실패해 여전히 빈 응답이면, 빈 화면 대신 안내 문구를 내보낸다.
        if not response.tool_calls and not (response.content or "").strip():
            response = AIMessage(
                content="조회는 마쳤는데 답변 정리에 실패했어요. 같은 질문을 한 번만 다시 보내 주시면 정리해 드릴게요."
            )

        if response.tool_calls:
            tool_names = ", ".join(tc["name"] for tc in response.tool_calls)
            report_status(f"필요한 조회 경로를 선택했어요: {tool_names}")
        else:
            report_status("조회 결과를 바탕으로 답변을 정리하고 있어요...")
        return {"messages": [response], "intent": intent}


    def call_tool(state: AgentState):
        last_message = state["messages"][-1]
        user_message = extract_user_message(state["messages"])
        current_turn = _current_turn_messages(state["messages"])
        tool_outputs = []
        errors = []

        for tool_call in last_message.tool_calls:
            tool_name = tool_call["name"]
            tool_args = tool_call["args"]
            if tool_name == "get_free_slots" and _is_team_meeting_availability_query(user_message):
                team_member_names = _team_member_names_from_tool_messages(current_turn)
                if team_member_names:
                    tool_args = dict(tool_args or {})
                    tool_args.pop("user_name", None)
                    tool_args["user_names"] = team_member_names
                    team_name = _team_name_from_tool_messages(current_turn)
                    if team_name:
                        tool_args["team_name"] = team_name
                        tool_args["include_team_shared_mentorings"] = True
            target_tool = next((t for t in LATEST_TOOLS if t.name == tool_name), None)

            if target_tool:
                try:
                    report_status(TOOL_STATUS_LABELS.get(tool_name, f"{tool_name} 실행 중..."))
                    if tool_args:
                        report_status("조회 조건을 정리하고 있어요...")
                    result = target_tool.invoke(tool_args)
                    report_status("조회가 완료됐어요.")
                except Exception as e:
                    error_message = f"{tool_name} 실행 중 에러가 발생했습니다: {str(e)}"
                    errors.append(error_message)
                    result = json.dumps({"error": error_message}, ensure_ascii=False)
                    report_status("조회 중 문제가 발생해 대체 경로를 확인하고 있어요.")
            else:
                error_message = f"알 수 없는 도구: {tool_name}"
                errors.append(error_message)
                result = json.dumps({"error": error_message}, ensure_ascii=False)
                report_status("요청한 처리 경로를 확인할 수 없어 답변을 조정하고 있어요.")

            tool_outputs.append(ToolMessage(content=str(result), tool_call_id=tool_call["id"]))

        return {
            "messages": tool_outputs,
            "tool_rounds": int(state.get("tool_rounds", 0) or 0) + 1,
            "tool_error_count": int(state.get("tool_error_count", 0) or 0) + len(errors),
            "last_tool_error": errors[-1] if errors else "",
        }

    def tool_failure_response(state: AgentState):
        report_status("반복 조회를 멈추고 수집된 데이터로 답변을 정리하고 있어요...")

        # 기존 메시지에서 도구 결과가 있으면 LLM에게 종합 답변을 요청
        messages = state["messages"]
        has_tool_results = any(
            isinstance(m, ToolMessage) and '"error"' not in m.content[:50]
            for m in messages
        )

        if has_tool_results:
            # 유효한 도구 결과가 있으므로 LLM이 종합 답변을 작성하도록 함.
            # 주의: 한도 도달 시점의 히스토리에는 응답되지 않은 tool_calls(AIMessage)나
            # tool_call/tool 메시지 쌍이 섞여 있어, 이를 그대로 재생하면 Upstage API가
            # 거부하거나 빈 content를 반환한다. 따라서 도구 결과를 '평문 컨텍스트'로 추출해
            # 깨끗한 프롬프트(system + human)로 다시 종합 요청한다.
            tool_blocks: list[str] = []
            for m in messages:
                if isinstance(m, ToolMessage) and m.content:
                    tool_blocks.append(str(m.content))
            collected_context = "\n\n---\n\n".join(tool_blocks)

            intent = state.get("intent", "general")
            instruction_text = build_intent_instruction(intent, state.get("data_readiness"))
            user_q = extract_user_message(messages)
            base_system = messages[0].content if messages and isinstance(messages[0], SystemMessage) else ""

            synth_system = SystemMessage(
                content=(
                    base_system + "\n\n" + instruction_text + "\n\n"
                    "## [중요] 도구 호출 한도 도달 — 수집된 결과로 답변 작성\n"
                    "추가 도구 호출은 불가능합니다. 아래 사용자 질문에 대해, 함께 제공된 조회 결과(JSON)만 사용해 "
                    "최대한 완성도 높은 한국어 답변을 작성하세요.\n"
                    "데이터가 부족한 부분은 '현재 수집된 데이터 기준'이라고 밝히되, 가능한 범위에서 구체적으로 답하세요.\n"
                    "절대로 '동기화를 먼저 하세요'만으로 답변을 끝내지 마세요."
                )
            )
            synth_human = HumanMessage(
                content=(
                    f"[질문]\n{user_q}\n\n"
                    f"[지금까지 수집한 조회 결과 — 이 데이터만 사용해 답변]\n{collected_context}"
                )
            )

            try:
                response = llm.invoke([synth_system, synth_human])
                if (response.content or "").strip():
                    return {"messages": [AIMessage(content=response.content)]}
            except Exception as synth_err:
                print(f"⚠️ [Agent Core] 종합 답변 생성 실패: {synth_err}")

        last_error = state.get("last_tool_error") or "필요한 조회를 완료하지 못했습니다."
        return {
            "messages": [
                AIMessage(
                    content=(
                        "요청을 처리하는 중 조회가 반복되어 중단했습니다.\n\n"
                        f"- 마지막 상태: {last_error}\n"
                        "- 이미 수집된 데이터만으로 답변을 완성하지 못했습니다. 질문에 팀원 전체 신청 일정 조율이 필요한지, 또는 본인이 이미 신청한 멘토링/특강과 고정 회의 시간만 제외하면 되는지 조건을 분리해 다시 시도해 주세요."
                    )
                )
            ]
        }

    def route_after_intent(state: AgentState):
        return "out_of_scope" if state.get("intent") == "out_of_scope" else "readiness_node"

    def route_after_readiness(state: AgentState):
        return "blocked" if state.get("blocked_reason") else "agent"

    def should_continue(state: AgentState):
        last_message = state["messages"][-1]
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            # 병렬 호출 1회는 tool_rounds=1입니다. PRD에 맞춰 최대 4회까지만 허용합니다.
            if int(state.get("tool_rounds", 0) or 0) >= 4:
                return "tool_failed"
            if isinstance(last_message, AIMessage) and _has_repeated_tool_call(state["messages"], last_message):
                return "tool_failed"
            if int(state.get("tool_error_count", 0) or 0) >= 3:
                return "tool_failed"
            return "action"
        return END

    def route_after_action(state: AgentState):
        # 도구 실행 완료 후에는 무조건 agent 노드로 복귀하여 데이터 해석 답변 작성 기회 제공
        return "agent"

    workflow = StateGraph(AgentState)
    workflow.add_node("intent_node", classify_intent)
    workflow.add_node("readiness_node", check_data_readiness)
    workflow.add_node("blocked", data_unavailable_response)
    workflow.add_node("agent", call_model)
    workflow.add_node("action", call_tool)
    workflow.add_node("tool_failed", tool_failure_response)
    workflow.add_node("out_of_scope", out_of_scope_response)

    workflow.set_entry_point("intent_node")
    workflow.add_conditional_edges("intent_node", route_after_intent, {
        "out_of_scope": "out_of_scope",
        "readiness_node": "readiness_node",
    })
    workflow.add_edge("out_of_scope", END)
    workflow.add_conditional_edges("readiness_node", route_after_readiness, {
        "blocked": "blocked",
        "agent": "agent",
    })
    workflow.add_edge("blocked", END)
    workflow.add_conditional_edges("agent", should_continue, {
        "action": "action",
        "tool_failed": "tool_failed",
        END: END,
    })
    workflow.add_conditional_edges("action", route_after_action, {
        "agent": "agent",
    })
    workflow.add_edge("tool_failed", END)

    return workflow.compile()


def run_agent(
    user_message: str,
    session_id: str,
    agent_graph,
    on_status_update=None,
) -> tuple[str, list[dict], str]:
    from database import db

    token = status_callback_var.set(on_status_update) if on_status_update else None
    try:
        print(f"\n💬 [Agent Core] 대화 세션 '{session_id}' 실행 시작...")
        if on_status_update:
            on_status_update("이전 대화 기록을 불러오고 있어요...")

        conversation_history = db.load_chat_history(session_id)
        print(f"   └─ SQLite에서 이전 대화 이력 로드 완료 (메시지 {len(conversation_history)}건)")

        if on_status_update:
            on_status_update("사용자 기본 정보를 확인하고 있어요...")

        from datetime import datetime, timedelta
        now = datetime.now()
        weekday_map = {0: "월요일", 1: "화요일", 2: "수요일", 3: "목요일", 4: "금요일", 5: "토요일", 6: "일요일"}
        now_weekday = weekday_map[now.weekday()]
        start_of_week = now - timedelta(days=now.weekday())
        end_of_week = start_of_week + timedelta(days=6)
        
        datetime_prompt = (
            f"\n\n## 현재 날짜 및 시간 컨텍스트\n"
            f"- 현재 시각: {now.strftime('%Y-%m-%d')} ({now_weekday}) {now.strftime('%H:%M')}\n"
            f"- 이번 주 범위: {start_of_week.strftime('%Y-%m-%d')} (월) ~ {end_of_week.strftime('%Y-%m-%d')} (일)\n"
            "이 컨텍스트를 사용하여 '현재', '오늘', '이번 주' 등의 요일 및 날짜를 계산하고 도구 매개변수(start_date, end_date)를 채우세요."
        )

        user_info_prompt = build_user_info_prompt(db.load_user_info())
        messages = [SystemMessage(content=BASE_SYSTEM_PROMPT + user_info_prompt + datetime_prompt)]
        messages.extend(_restore_history_messages(conversation_history))
        messages.append(HumanMessage(content=user_message))
        start_count = len(messages)

        if on_status_update:
            on_status_update("처리 경로를 구성하고 있어요...")
        print("⚙️ [Agent Core] LangGraph 에이전트 추론 엔진 호출...")

        output = agent_graph.invoke({"messages": messages})
        final_messages = output["messages"]
        print(f"   └─ 에이전트 응답 생성 완료 (총 메시지 {len(final_messages)}개)")

        new_messages = final_messages[start_count - 1:]
        _save_new_messages(db, session_id, new_messages)

        assistant_content = _last_assistant_content(final_messages)
        if _is_personal_fixed_meeting_recommendation(user_message):
            visual_schedule_block = _latest_visual_schedule_block(new_messages)
            if visual_schedule_block and "```schedule" not in assistant_content:
                assistant_content = f"{assistant_content.rstrip()}\n\n{visual_schedule_block}"
        workflow_mermaid = build_workflow_mermaid(
            new_messages,
            intent=output.get("intent"),
            data_readiness=output.get("data_readiness"),
            blocked_reason=output.get("blocked_reason"),
        )

        history_out = [_msg_to_dict(m) for m in final_messages if not isinstance(m, SystemMessage)]
        return assistant_content, history_out, workflow_mermaid
    finally:
        if token is not None:
            status_callback_var.reset(token)


def _restore_history_messages(history: list[dict]) -> list[BaseMessage]:
    messages: list[BaseMessage] = []
    for item in history:
        role = item.get("role")
        content = item.get("content", "")
        if role == "user":
            messages.append(HumanMessage(content=content))
        elif role == "assistant":
            if item.get("tool_calls"):
                continue
            if _contains_raw_tool_call_text(content):
                continue
            messages.append(AIMessage(content=content))
    return messages


def _restore_tool_calls(tool_calls: list[dict]) -> list[dict]:
    restored = []
    for tool_call in tool_calls:
        function = tool_call.get("function", {})
        arguments = function.get("arguments", {})
        restored.append({
            "name": function.get("name", ""),
            "args": json.loads(arguments) if isinstance(arguments, str) else arguments,
            "id": tool_call.get("id", ""),
            "type": "tool_call",
        })
    return restored


def _save_new_messages(db, session_id: str, messages: list[BaseMessage]):
    saved_count = 0
    for message in messages:
        row = _db_row_from_message(message)
        if not row:
            continue
        db.save_chat_message(session_id=session_id, **row)
        saved_count += 1
    print(f"💾 [Agent Core] 신규 대화 메시지 {saved_count}건 SQLite 저장 완료.")


def _db_row_from_message(message: BaseMessage) -> dict | None:
    content = message.content or ""
    if isinstance(message, HumanMessage):
        return {"role": "user", "content": content, "tool_calls": None, "tool_call_id": None}
    if isinstance(message, AIMessage):
        tool_calls = _serialize_tool_calls(message.tool_calls) if message.tool_calls else None
        if _contains_raw_tool_call_text(content) and not tool_calls:
            return None
        return {"role": "assistant", "content": content, "tool_calls": tool_calls, "tool_call_id": None}
    if isinstance(message, ToolMessage):
        return {"role": "tool", "content": content, "tool_calls": None, "tool_call_id": message.tool_call_id}
    return None


def _serialize_tool_calls(tool_calls: list[dict]) -> str:
    payload = [
        {
            "id": tc["id"],
            "type": "function",
            "function": {
                "name": tc["name"],
                "arguments": json.dumps(tc["args"], ensure_ascii=False) if isinstance(tc["args"], dict) else tc["args"],
            },
        }
        for tc in tool_calls
    ]
    return json.dumps(payload, ensure_ascii=False)


def _last_assistant_content(messages: list[BaseMessage]) -> str:
    for message in reversed(messages):
        if isinstance(message, AIMessage) and message.content:
            if _contains_raw_tool_call_text(message.content):
                continue
            return message.content
    return ""


def _msg_to_dict(msg: BaseMessage) -> dict:
    if isinstance(msg, HumanMessage):
        return {"role": "user", "content": msg.content}
    if isinstance(msg, AIMessage):
        data = {"role": "assistant", "content": msg.content or ""}
        if msg.tool_calls:
            data["tool_calls"] = json.loads(_serialize_tool_calls(msg.tool_calls))
        return data
    if isinstance(msg, ToolMessage):
        return {"role": "tool", "tool_call_id": msg.tool_call_id, "content": msg.content}
    return {}
