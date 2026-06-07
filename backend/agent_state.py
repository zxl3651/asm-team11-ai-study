from typing import Annotated, Sequence, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict, total=False):
    messages: Annotated[Sequence[BaseMessage], add_messages]
    intent: str
    data_readiness: dict
    blocked_reason: str
    warning_context: str
    tool_rounds: int
    tool_error_count: int
    last_tool_error: str


TOOL_STATUS_LABELS = {
    "search_mentors": "멘토 정보를 조회하고 있어요...",
    "search_mentorings": "멘토링/특강 후보를 조회하고 있어요...",
    "vector_search_mentorings": "벡터 검색으로 유사한 멘토링/특강을 찾고 있어요...",
    "search_trainees": "연수생 정보를 조회하고 있어요...",
    "get_participant_registrations": "참여자별 신청 내역을 확인하고 있어요...",
    "get_team_participant_schedule": "팀원별 신청 일정을 확인하고 있어요...",
    "get_user_calendar": "참여자 신청 일정을 확인하고 있어요...",
    "get_team_info": "소속 팀 정보를 확인하고 있어요...",
    "get_free_slots": "일정표에서 빈 시간대를 계산하고 있어요...",
}
