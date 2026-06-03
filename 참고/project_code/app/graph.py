# ========================================
# Medical QA Agent — LangGraph 워크플로우
# ========================================

from langgraph.graph import StateGraph, START, END
from app.schemas import AgentState
from app.agents.query_analyzer import analyze_query
from app.agents.retrieval import retrieve_context
from app.agents.responder import generate_answer


def route_by_domain(state: AgentState) -> str:
    """도메인 분류 결과에 따라 다음 노드를 결정한다.

    medical → retrieve (벡터 검색 후 답변)
    general / out_of_scope → respond (바로 답변)
    """
    return "retrieve" if state.get("domain", "medical") == "medical" else "respond"


def create_graph():
    """Medical QA 워크플로우 그래프를 생성한다."""
    builder = StateGraph(AgentState)

    # 노드 추가
    builder.add_node("analyze", analyze_query)
    builder.add_node("retrieve", retrieve_context)
    builder.add_node("respond", generate_answer)

    # 엣지 연결
    builder.add_edge(START, "analyze")
    builder.add_conditional_edges(
        "analyze",
        route_by_domain,
        {"retrieve": "retrieve", "respond": "respond"},
    )
    builder.add_edge("retrieve", "respond")
    builder.add_edge("respond", END)

    return builder.compile()
