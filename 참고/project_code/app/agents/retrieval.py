from app.schemas import AgentState
from app.vector_store import search_documents


def retrieve_context(state: AgentState) -> dict:
    """질문과 키워드를 결합하여 ChromaDB에서 관련 문서를 검색한다."""
    query = state["query"]
    keywords = state.get("query_analysis", {}).get("keywords", [])
    # 키워드를 쿼리에 붙여서 검색 정확도를 높인다
    search_query = f"{query} {' '.join(keywords)}" if keywords else query
    return {"search_results": search_documents(query=search_query, n_results=3)}
