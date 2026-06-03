import json

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph

from agent_intent import extract_user_message, fallback_intent, normalize_intent, parse_json_object, readiness_block_reason
from agent_prompts import BASE_SYSTEM_PROMPT, INTENT_CLASSIFICATION_PROMPT, build_intent_instruction, build_user_info_prompt
from agent_state import AgentState, TOOL_STATUS_LABELS
from tools import LATEST_TOOLS, report_status, status_callback_var
from workflow_trace import build_workflow_mermaid


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
        report_status("요청 내용을 분석하고 있어요...")

        # 만약 도구 호출 결과 중에 get_free_slots가 포함되어 있다면, intent를 schedule_check로 동적으로 간주하여 관련 프롬프트를 보강
        has_free_slots_tool = any(
            isinstance(m, ToolMessage) and m.content and '"visual_schedule_block"' in m.content
            for m in messages
        )
        if has_free_slots_tool and intent not in ("schedule_check", "lecture_recommendation"):
            intent = "schedule_check"

        instruction_text = build_intent_instruction(intent, state.get("data_readiness"))
        if warning_context:
            instruction_text += f"\n\n## [중요] 데이터 누락 경고 및 가이드\n{warning_context}"

        if messages and isinstance(messages[0], SystemMessage):
            merged_content = messages[0].content + "\n\n" + instruction_text
            model_messages = [SystemMessage(content=merged_content), *messages[1:]]
        else:
            model_messages = [SystemMessage(content=instruction_text), *messages]

        response = llm_with_tools.invoke(model_messages)
        if response.tool_calls:
            tool_names = ", ".join(tc["name"] for tc in response.tool_calls)
            report_status(f"필요한 조회 경로를 선택했어요: {tool_names}")
        else:
            report_status("조회 결과를 바탕으로 답변을 정리하고 있어요...")
        return {"messages": [response], "intent": intent}


    def call_tool(state: AgentState):
        last_message = state["messages"][-1]
        tool_outputs = []
        errors = []

        for tool_call in last_message.tool_calls:
            tool_name = tool_call["name"]
            tool_args = tool_call["args"]
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
                        "요청을 처리하는 중 조회 한도에 도달했습니다.\n\n"
                        f"- 마지막 상태: {last_error}\n"
                        "- 포털 데이터 동기화 후 다시 시도해 주세요."
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
