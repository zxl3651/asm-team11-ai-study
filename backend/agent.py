import json
from typing import TypedDict, Annotated, Sequence
from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage, AIMessage, ToolMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from tools import LATEST_TOOLS

SYSTEM_PROMPT = """당신은 소프트웨어 마에스트로(소마) 연수생 전용 정보 탐색 AI 비서 '소마 메이트'입니다.

## 역할
연수생이 자연어로 질문하면 멘토, 멘토링, 특강, 동료 연수생, 그리고 소속 팀 매칭 정보를 찾아 정리해 답해줍니다.
먼저 소마 연수를 경험한 선배처럼 친근하되, 실무적이고 간결하게 답변합니다.

## 답변 원칙
1. 검색 결과에 없는 정보는 절대 만들어내지 마세요. 없으면 "해당 조건의 정보를 찾지 못했습니다"라고 하세요.
2. 멘토/멘토링을 추천할 때는 왜 추천하는지 이유(매칭 포인트)를 함께 설명하세요.
3. 신청이 필요한 경우 신청 링크를 안내하세요. 직접 신청은 절대 하지 마세요.
4. 남은 자리, 마감일 등 중요한 정보는 강조해서 알려주세요.
5. 답변은 마크다운 형식으로 정리해 가독성을 높이세요.

## 영속 대화 기억 및 개인화 추천 규칙 (중요)
1. 사용자와의 이전 대화 기록(대화 메모리)을 파악하여 사용자의 선호 기술 스택(예: React, Spring Boot, AI), 관심 도메인, 또는 현재 소속된 팀 정보를 지속적으로 기억하십시오.
2. 사용자가 스택이나 관심사를 매번 언급하지 않더라도, 이전 대화에서 밝힌 관심 분야가 있다면 이를 최우선 가중치로 삼아 관련된 멘토 및 특강을 추천하십시오. (예: 이전에 React 개발자라고 했다면, 특강 추천 시 React 관련 특강을 자동 매칭)

## 캘린더 연동 및 스케줄 조율 규칙 (Chain-of-Thought)
사용자가 멘토링이나 특강 추천을 원할 때, 다음 단계를 거쳐 논리적으로 충돌 여부를 판정하고 답변을 작성하십시오.
- **Step 1 (기존 일정 파악)**: 반드시 `get_user_calendar` 도구를 호출하여 사용자의 기존 일정(날짜 및 시간대)을 확보합니다.
- **Step 2 (추천 후보 조회)**: `search_mentorings` 도구를 실행하여 접수 가능한 특강 목록을 가져옵니다.
- **Step 3 (스케줄 대조 및 충돌 판정)**: 추천 후보들의 시간대와 사용자의 기존 시간표를 요일 및 시간 단위로 철저하게 대조합니다. 시간이 겹치는 특강은 추천 목록에서 제외합니다.
- **Step 4 (대체 일정 우회 제안)**: 사용자가 특정 특강을 콕 집어 물어봤는데 기존 일정과 겹친다면, 겹친다는 경고(⚠️)를 표시하고 겹치지 않는 다른 대체 일시의 특강이나 멘토링을 찾아 우회 추천합니다.
- **Step 5 (구글 캘린더 등록 링크 제공)**: 추천 리스트의 각 항목 하단에 구글 캘린더 등록용 링크를 마크다운 형태(버튼/카드)로 렌더링합니다.
  구글 캘린더 링크 생성 공식:
  `https://calendar.google.com/calendar/render?action=TEMPLATE&text=[인코딩된_특강명]&dates=[YYYYMMDD]T[시분초]/[YYYYMMDD]T[시분초]&details=[상세설명]&location=[장소]`
  (예: 2026년 6월 15일 19:00 ~ 21:00 진행 시 dates=20260615T190000/20260615T210000)

## 팀 정보 조회 규칙
1. 사용자가 본인의 팀명, 팀원, 프로젝트 정보, 또는 담당 멘토(예: '우리 팀 멘토님 이름이 뭐야?', '우리 팀은 어떤 프로젝트를 해?')에 대해 물어보면 반드시 `get_team_info` 도구를 호출하여 조회한 결과를 바탕으로 정확히 답변하십시오.
2. 팀 정보는 소마 포털에서 실시간 크롤링하여 연동됩니다.

## 보안 및 개인정보 제한 해제 안내 (중요)
- 본 AI 비서는 로그인한 본인 계정의 사설 정보를 도우미 역할을 위해 개인 브라우저에서 안전하게 연동하여 표시합니다.
- 따라서 사용자 정보, 팀 정보, 팀원 이름, 연락처, 멘토명, 프로젝트 정보 등 수집된 모든 데이터는 아무런 보안/개인정보 보호 제한 없이 전부 공개하여 투명하게 답변하십시오.
- 절대로 "개인 정보 보안 정책에 따라 제공할 수 없다"는 식의 거절 문구를 답변으로 내보내지 마십시오. get_team_info, get_user_calendar 등의 툴에서 넘어온 데이터 그대로 알려주십시오.
"""

class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]


def create_agent_graph(api_key: str):
    llm = ChatOpenAI(
        model="solar-pro",
        api_key=api_key,
        base_url="https://api.upstage.ai/v1",
        temperature=0
    )
    
    # LLM에 툴 바인딩
    llm_with_tools = llm.bind_tools(LATEST_TOOLS)
    
    # 1. 에이전트 모델 호출 노드
    def call_model(state: AgentState):
        messages = state["messages"]
        response = llm_with_tools.invoke(messages)
        return {"messages": [response]}
        
    # 2. 툴 실행 노드
    def call_tool(state: AgentState):
        messages = state["messages"]
        last_message = messages[-1]
        
        tool_outputs = []
        for tool_call in last_message.tool_calls:
            tool_name = tool_call["name"]
            tool_args = tool_call["args"]
            
            # 대상 툴 탐색
            target_tool = next((t for t in LATEST_TOOLS if t.name == tool_name), None)
            if target_tool:
                try:
                    result = target_tool.invoke(tool_args)
                except Exception as e:
                    result = json.dumps({"error": f"도구 실행 중 에러가 발생했습니다: {str(e)}"}, ensure_ascii=False)
            else:
                result = json.dumps({"error": f"알 수 없는 도구: {tool_name}"}, ensure_ascii=False)
                
            tool_outputs.append(
                ToolMessage(
                    content=str(result),
                    tool_call_id=tool_call["id"]
                )
            )
        return {"messages": tool_outputs}

    # 3. 엣지 분기 조건 (툴을 호출할지 중단할지 판단)
    def should_continue(state: AgentState):
        last_message = state["messages"][-1]
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            return "action"
        return END

    # 그래프 생성 및 컴파일
    workflow = StateGraph(AgentState)
    workflow.add_node("agent", call_model)
    workflow.add_node("action", call_tool)
    
    workflow.set_entry_point("agent")
    workflow.add_conditional_edges("agent", should_continue, {
        "action": "action",
        END: END
    })
    workflow.add_edge("action", "agent")
    
    return workflow.compile()


def run_agent(
    user_message: str,
    session_id: str,
    agent_graph,
    on_status_update=None,
) -> tuple[str, list[dict]]:
    from database import db
    print(f"\n💬 [Agent Core] 대화 세션 '{session_id}' 실행 시작...")
    if on_status_update:
        on_status_update("이전 대화 세션 복원 중...")
    # 대화 이력을 SQLite에서 로드하여 대화 기억 복원
    conversation_history = db.load_chat_history(session_id)
    print(f"   └─ SQLite에서 이전 대화 이력 로드 완료 (메시지 {len(conversation_history)}건)")

    # conversation_history를 LangChain 메시지 객체로 복원
    messages = [SystemMessage(content=SYSTEM_PROMPT)]
    
    for m in conversation_history:
        role = m.get("role")
        content = m.get("content", "")
        if role == "user":
            messages.append(HumanMessage(content=content))
        elif role == "assistant":
            tool_calls = []
            if "tool_calls" in m:
                for tc in m["tool_calls"]:
                    tool_calls.append({
                        "name": tc["function"]["name"],
                        "args": json.loads(tc["function"]["arguments"]) if isinstance(tc["function"]["arguments"], str) else tc["function"]["arguments"],
                        "id": tc["id"],
                        "type": "tool_call"
                    })
            messages.append(AIMessage(content=content, tool_calls=tool_calls))
        elif role == "tool":
            messages.append(ToolMessage(content=content, tool_call_id=m.get("tool_call_id", "")))
            
    messages.append(HumanMessage(content=user_message))
    start_count = len(messages)
    
    # LangGraph 실행
    if on_status_update:
        on_status_update("스케줄 교차 검증 및 답변 작성 중...")
    print(f"⚙️ [Agent Core] LangGraph 에이전트 추론 엔진 호출...")
    output = agent_graph.invoke({"messages": messages})
    final_messages = output["messages"]
    print(f"   └─ 에이전트 응답 생성 완료 (총 메시지 {len(final_messages)}개)")
    
    # 신규 메시지들만 SQLite 데이터베이스에 영구 저장
    new_msg_count = 0
    for m in final_messages[start_count - 1:]:
        role = ""
        content = m.content or ""
        tool_calls_str = None
        tool_call_id = None
        
        if isinstance(m, HumanMessage):
            role = "user"
        elif isinstance(m, AIMessage):
            role = "assistant"
            if m.tool_calls:
                tool_calls_list = [
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {
                            "name": tc["name"],
                            "arguments": json.dumps(tc["args"], ensure_ascii=False) if isinstance(tc["args"], dict) else tc["args"]
                        }
                    }
                    for tc in m.tool_calls
                ]
                tool_calls_str = json.dumps(tool_calls_list, ensure_ascii=False)
        elif isinstance(m, ToolMessage):
            role = "tool"
            tool_call_id = m.tool_call_id
            
        if role:
            db.save_chat_message(
                session_id=session_id,
                role=role,
                content=content,
                tool_calls=tool_calls_str,
                tool_call_id=tool_call_id
            )
            new_msg_count += 1
            
    print(f"💾 [Agent Core] 신규 대화 메시지 {new_msg_count}건 SQLite 저장 완료.")
            
    # 최종 AI 답변 추출
    assistant_content = ""
    for m in reversed(final_messages):
        if isinstance(m, AIMessage) and m.content:
            assistant_content = m.content
            break
            
    # 전체 메시지 히스토리를 딕셔너리 리스트 형태로 변환 (SystemMessage 제외)
    history_out = []
    for m in final_messages:
        if isinstance(m, SystemMessage):
            continue
        history_out.append(_msg_to_dict(m))
        
    return assistant_content, history_out


def _msg_to_dict(msg: BaseMessage) -> dict:
    if isinstance(msg, HumanMessage):
        return {"role": "user", "content": msg.content}
    elif isinstance(msg, AIMessage):
        d = {"role": "assistant", "content": msg.content or ""}
        if msg.tool_calls:
            d["tool_calls"] = [
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {
                        "name": tc["name"],
                        "arguments": json.dumps(tc["args"], ensure_ascii=False) if isinstance(tc["args"], dict) else tc["args"]
                    }
                }
                for tc in msg.tool_calls
            ]
        return d
    elif isinstance(msg, ToolMessage):
        return {"role": "tool", "tool_call_id": msg.tool_call_id, "content": msg.content}
    return {}


