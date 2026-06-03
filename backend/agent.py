import json

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
    has_personal_scope = any(keyword in text for keyword in ["내 일정", "나의 일정", "내 수강", "수강 이력"])
    has_fixed_meeting = "정기 회의" in text or ("회의" in text and "제외" in text)
    has_recommendation = any(keyword in text for keyword in ["특강", "멘토링", "추천", "골라"])
    return has_personal_scope and has_fixed_meeting and has_recommendation


def _is_team_meeting_availability_query(user_message: str) -> bool:
    text = user_message.strip().lower()
    if (
        any(keyword in text for keyword in ["내 일정", "나의 일정", "내 수강", "수강 이력"])
        and any(keyword in text for keyword in ["특강", "멘토링", "추천", "골라"])
        and ("정기 회의" in text or ("회의" in text and "제외" in text))
    ):
        return False
    has_team_scope = any(keyword in text for keyword in ["우리 팀", "팀 정보를", "팀 정보", "팀원"])
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


def _team_meeting_unavailable_answer(messages: list[BaseMessage]) -> str | None:
    payloads = _json_tool_payloads(messages)
    free_slots_result = next(
        (payload for payload in reversed(payloads) if payload.get("error") == "team_member_calendar_unavailable"),
        None,
    )
    if not free_slots_result:
        return None

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
    missing_names = free_slots_result.get("missing_user_names") or []
    missing_text = ", ".join(missing_names) if missing_names else "확인 불가"

    return (
        "팀 정보\n\n"
        f"- 팀명: {team_name}\n"
        f"- 팀장: {leader}\n"
        f"- 팀원: {members_text}\n"
        f"- 전담 멘토: {mentor}\n"
        f"- 프로젝트: {project}\n\n"
        "팀 전체 공통 회의 가능 시간은 확정할 수 없습니다.\n\n"
        f"누락된 팀원 일정: {missing_text}\n\n"
        "원인: 현재 저장된 멘토링/특강 상세 데이터에서 해당 팀원의 신청자 명단 기반 일정을 찾지 못했습니다. "
        "상세 페이지에 신청자 명단이 수집되어 있어야 팀원별 특강/멘토링 일정을 만들 수 있습니다.\n\n"
        "이 상태에서는 김민수 일정만으로 팀 회의 시간을 대체 계산하지 않습니다. "
        "정확한 팀 전체 후보를 계산하려면 멘토링/특강 상세의 신청자 명단이 포함되도록 다시 동기화하거나, 팀원 일정이 포함된 공유 캘린더/공식 API가 필요합니다."
    )


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
        elif _is_personal_fixed_meeting_recommendation(user_message):
            intent = "lecture_recommendation"
        elif _is_team_meeting_availability_query(user_message):
            intent = "schedule_check"

        report_status(f"처리 유형을 '{intent}' 경로로 분류했어요...")
        return {"intent": intent}

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
                "팀원 중 일부의 개인 일정 데이터가 없으면 후보 시간대를 계산하지 말고, 누락된 팀원 이름과 함께 확정 불가라고 답하세요."
            )
        if is_fixed_meeting_recommendation:
            instruction_text += (
                "\n\n## [중요] 개인 일정 기준 고정 회의 제외 특강 추천\n"
                "현재 요청은 팀원 전체 공통 시간 조율이 아닙니다. `get_team_info`를 호출하지 마세요. "
                "로그인한 본인의 개인 일정, 평일 10:00~12:00 고정 회의 차단 시간, "
                "신청 가능한 특강/멘토링 후보만 사용해 답변하세요. "
                "도구는 `get_user_calendar(user_name='me')`, `search_mentorings(status='접수중')`, "
                "`get_free_slots(user_name='me', recurring_busy_blocks=[...])`만 필요합니다."
            )
        if any(
            isinstance(m, ToolMessage) and "team_member_calendar_unavailable" in (m.content or "")
            for m in messages
        ):
            if is_team_meeting_availability:
                instruction_text += (
                    "\n\n## [중요] 팀원 캘린더 조회 불가\n"
                    "팀원 개인 일정 데이터가 없어 팀 전체 공통 시간 계산은 불가능합니다. "
                    "같은 팀원 캘린더 조회나 `get_free_slots` 반복 호출을 중단하세요. "
                    "본인 일정 기준 후보, 특강 목록 기반 후보, 예시 후보를 출력하지 말고 확정 불가 사유만 설명하세요. "
                    "원인은 동기화된 멘토링/특강 상세 페이지의 신청자 명단(participantNames)에서 해당 팀원의 일정을 찾지 못했기 때문입니다."
                )
            else:
                instruction_text += (
                    "\n\n## [중요] 팀원 캘린더 조회 불가\n"
                    "팀원 개인 일정 데이터가 없어 팀 전체 공통 시간 계산은 불가능합니다. "
                    "같은 팀원 캘린더 조회나 `get_free_slots` 반복 호출을 중단하고, "
                    "현재 확보된 본인 일정/특강 목록/질문에 명시된 고정 제외 시간만으로 답변하세요. "
                    "고정 팀 회의 시간을 제외한 개인 특강 추천 요청이라면 팀원 캘린더가 필요하지 않다고 판단하세요."
                )
        if any(
            isinstance(m, ToolMessage) and '"availability_scope": "current_user_only"' in (m.content or "")
            for m in messages
        ) and ("팀" in user_message and ("회의" in user_message or "모두" in user_message or "우리" in user_message)):
            instruction_text += (
                "\n\n## [중요] 본인 일정 기준 결과를 팀 전체 결과로 오인 금지\n"
                "`availability_scope=current_user_only`인 빈 시간 결과는 로그인한 본인 일정 기준입니다. "
                "사용자가 팀 회의 가능 시간을 물었다면 팀원 전체 공통 가능 시간으로 확정하지 마세요. "
                "팀원별 캘린더 데이터가 없으면 확정 불가라고 밝히고, 본인 일정 기준 후보도 출력하지 마세요. "
                "캘린더 시각화도 출력하지 마세요."
            )

        if messages and isinstance(messages[0], SystemMessage):
            merged_content = messages[0].content + "\n\n" + instruction_text
            model_messages = [SystemMessage(content=merged_content), *messages[1:]]
        else:
            model_messages = [SystemMessage(content=instruction_text), *messages]

        if is_team_meeting_availability and _has_tool_call(current_turn, "get_free_slots"):
            unavailable_answer = _team_meeting_unavailable_answer(current_turn)
            if unavailable_answer:
                response = AIMessage(content=unavailable_answer)
                report_status("팀원 일정 데이터 누락으로 확정 불가 답변을 작성했어요...")
                return {"messages": [response], "intent": intent}
            final_instruction = SystemMessage(
                content=(
                    "팀 회의 가능 시간 계산을 위한 조회가 끝났습니다. 추가 도구를 호출하지 말고 최종 답변을 작성하세요. "
                    "`get_free_slots`가 `team_member_calendar_unavailable`을 반환했다면 후보 시간대를 나열하지 말고, "
                    "팀 정보와 누락된 팀원 일정 데이터 때문에 팀 전체 공통 가능 시간을 확정할 수 없다고 답하세요. "
                    "`availability_scope=team`이고 `meeting_windows`가 있을 때만 팀 전체 2시간 후보를 모두 나열하세요. "
                    "`availability_scope=team_shared_mentorings_only`이면 팀 공통 멘토링/특강 일정 기준 후보로 나열하되, "
                    "`scope_warning`과 `missing_user_names`를 함께 밝혀 개인 일정이 없는 팀원의 개별 일정은 미반영이라고 설명하세요. "
                    "본인 일정 기준 참고 후보도 출력하지 마세요."
                )
            )
            response = llm.invoke([*model_messages, final_instruction])
        elif is_fixed_meeting_recommendation and all(
            _has_tool_call(current_turn, tool_name)
            for tool_name in ("get_user_calendar", "search_mentorings", "get_free_slots")
        ):
            final_instruction = SystemMessage(
                content=(
                    "필요한 조회가 모두 끝났습니다. 추가 도구를 호출하지 말고 최종 답변을 작성하세요. "
                    "팀원 전체 일정 조율이 아니므로 팀원 일정 부족을 이유로 중단하지 마세요. "
                    "평일 10:00~12:00는 고정 회의로 제외하고, 본인 기존 일정과 겹치지 않으며 "
                    "접수중인 특강/멘토링만 5~7개 이내로 추천하세요. "
                    "추천마다 시간, 제목, 멘토/작성자, 남은 자리 또는 정원 정보, 추천 근거를 짧게 쓰세요."
                )
            )
            response = llm.invoke([*model_messages, final_instruction])
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
            elif is_fixed_meeting_recommendation:
                allowed_names = {"get_user_calendar", "search_mentorings", "get_free_slots"}
                called = {
                    tool_call.get("name")
                    for msg in current_turn
                    if isinstance(msg, AIMessage)
                    for tool_call in (getattr(msg, "tool_calls", []) or [])
                }
                if "get_user_calendar" in called and "search_mentorings" in called:
                    allowed_names = {"get_free_slots"}
                allowed_tools = [tool for tool in LATEST_TOOLS if tool.name in allowed_names]
            elif is_team_meeting_availability:
                called = {
                    tool_call.get("name")
                    for msg in current_turn
                    if isinstance(msg, AIMessage)
                    for tool_call in (getattr(msg, "tool_calls", []) or [])
                }
                allowed_names = {"get_team_info"} if "get_team_info" not in called else {"get_free_slots"}
                allowed_tools = [tool for tool in LATEST_TOOLS if tool.name in allowed_names]
            response = llm.bind_tools(allowed_tools).invoke(model_messages)
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
            # 유효한 도구 결과가 있으므로 LLM이 종합 답변을 작성하도록 함
            intent = state.get("intent", "general")
            instruction_text = build_intent_instruction(intent, state.get("data_readiness"))
            fallback_instruction = SystemMessage(
                content=(
                    instruction_text + "\n\n"
                    "## [중요] 도구 호출 한도 도달\n"
                    "추가 도구 호출이 불가능합니다. 지금까지 수집된 도구 결과만으로 최대한 완성도 높은 답변을 작성하세요.\n"
                    "데이터가 부족한 부분은 '현재 수집된 데이터 기준'이라고 밝히되, 가능한 범위에서 구체적으로 답변하세요.\n"
                    "절대로 '동기화를 먼저 하세요'만으로 답변을 끝내지 마세요."
                )
            )
            if messages and isinstance(messages[0], SystemMessage):
                model_messages = [messages[0], fallback_instruction, *messages[1:]]
            else:
                model_messages = [fallback_instruction, *messages]

            try:
                response = llm.invoke(model_messages)
                return {"messages": [response]}
            except Exception:
                pass  # LLM 호출 실패 시 아래 기본 응답으로 fallback

        last_error = state.get("last_tool_error") or "필요한 조회를 완료하지 못했습니다."
        return {
            "messages": [
                AIMessage(
                    content=(
                        "요청을 처리하는 중 조회가 반복되어 중단했습니다.\n\n"
                        f"- 마지막 상태: {last_error}\n"
                        "- 이미 수집된 데이터만으로 답변을 완성하지 못했습니다. 질문에 팀원 전체 일정 조율이 필요한지, 또는 내 일정에서 고정 회의 시간만 제외하면 되는지 조건을 분리해 다시 시도해 주세요."
                    )
                )
            ]
        }

    def route_after_readiness(state: AgentState):
        return "blocked" if state.get("blocked_reason") else "agent"

    def should_continue(state: AgentState):
        last_message = state["messages"][-1]
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            # 병렬 호출 1회는 tool_rounds=1이므로 5회까지 허용하면 충분한 여유
            if int(state.get("tool_rounds", 0) or 0) >= 5:
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

    workflow.set_entry_point("intent_node")
    workflow.add_edge("intent_node", "readiness_node")
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
