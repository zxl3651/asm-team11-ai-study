import logging

from langchain_core.messages import SystemMessage, HumanMessage
from app.schemas import AgentState, QueryAnalysis
from app.core.llm import get_llm
from app.prompts.templates import QUERY_ANALYZER_SYSTEM

logger = logging.getLogger(__name__)


def analyze_query(state: AgentState) -> dict:
    """사용자 질문을 분석하여 domain, keywords, intent를 추출한다."""
    llm = get_llm(temperature=0.0)
    query = state["query"]

    try:
        structured_llm = llm.with_structured_output(QueryAnalysis)
        analysis = structured_llm.invoke([
            SystemMessage(content=QUERY_ANALYZER_SYSTEM),
            HumanMessage(content=query),
        ])
        return {
            "query_analysis": analysis.model_dump(),
            "domain": analysis.domain,
            "messages": [HumanMessage(content=query)],
        }
    except Exception as e:
        # structured output 파싱 실패 시 기본값으로 fallback
        logger.warning("Query analysis failed: %s", e)
        return {
            "query_analysis": {"keywords": [], "domain": "medical", "intent": query, "status": "success"},
            "domain": "medical",
            "messages": [HumanMessage(content=query)],
        }
