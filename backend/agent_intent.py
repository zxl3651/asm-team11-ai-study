import json
import re
from typing import Sequence

from langchain_core.messages import BaseMessage, HumanMessage


VALID_INTENTS = {
    "schedule_check",
    "lecture_recommendation",
    "mentor_recommendation",
    "team_info",
    "trainee_search",
    "personal_info",
    "general",
    "out_of_scope",
}


def extract_user_message(messages: Sequence[BaseMessage]) -> str:
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            return msg.content
    return ""


def parse_json_object(text: str) -> dict | None:
    match = re.search(r"\{[\s\S]*\}", text or "")
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def fallback_intent(user_message: str) -> str:
    text = user_message.lower()
    if any(keyword in text for keyword in ["겹치", "시간", "일정", "스케줄", "신청해도", "제외", "피해서", "빈 시간", "가능한 시간"]):
        return "schedule_check"
    if any(keyword in text for keyword in ["이력", "수강", "참여", "관심사"]) and any(keyword in text for keyword in ["특강", "멘토링", "추천"]):
        return "lecture_recommendation"
    if any(keyword in text for keyword in ["특강", "멘토링", "추천"]):
        return "lecture_recommendation"
    if "멘토" in text:
        return "mentor_recommendation"
    if any(keyword in text for keyword in ["연수생", "동료", "구하는"]):
        return "trainee_search"
    if any(keyword in text for keyword in ["팀", "팀원", "프로젝트"]):
        return "team_info"
    if any(keyword in text for keyword in ["나", "내 ", "내가", "기본정보"]):
        return "personal_info"
    return "general"


def normalize_intent(value: str | None, user_message: str) -> str:
    if value in VALID_INTENTS:
        return value
    return fallback_intent(user_message)


def readiness_block_reason(intent: str, readiness: dict) -> str:
    def total_count(name: str) -> int:
        data = readiness.get(name, {})
        return int(data.get("total", 0) or 0)

    # 1. 스케줄 조율인데 멘토링/특강 데이터가 전혀 없는 경우
    if intent == "schedule_check" and total_count("mentorings") == 0:
        return "멘토링/특강 목록 데이터가 없어 일정 분석을 진행할 수 없습니다."

    # 2. 특강 추천인데 특강 데이터가 전혀 없는 경우
    if intent == "lecture_recommendation" and total_count("mentorings") == 0:
        return "멘토링/특강 목록 데이터가 없어 추천을 진행할 수 없습니다."

    # 3. 팀 정보 조회인데 팀 정보가 아예 없는 경우
    if intent == "team_info" and total_count("team_info") == 0:
        return "소속 팀 매칭 정보가 없어 팀 관련 답변을 진행할 수 없습니다."

    # 4. 개인정보 조회인데 개인정보가 아예 없는 경우
    if intent == "personal_info" and total_count("user_info") == 0:
        return "사용자 기본정보가 없어 '나'에 대한 답변을 진행할 수 없습니다."

    return ""


def readiness_warning_context(intent: str, readiness: dict) -> str:
    def total_count(name: str) -> int:
        data = readiness.get(name, {})
        return int(data.get("total", 0) or 0)

    warnings = []
    if intent == "schedule_check":
        if total_count("mentorings") == 0:
            warnings.append(
                "포털로부터 특강/멘토링 목록 데이터가 아직 동기화되지 않았습니다. "
                "따라서 빈 회의 시간대는 추천해 줄 수 있으나, 특강 목록과의 겹침 확인이나 특강 추천을 제공할 수 없습니다. "
                "답변 시 '현재 특강/멘토링 목록이 동기화되지 않아 겹침 여부를 확인할 수 없습니다.'라는 안내 문구를 꼭 포함하세요."
            )
    elif intent == "lecture_recommendation":
        # 개인 수강 이력(개인 접수 이력)을 수집하지 않는 대신, 기술 스택 기반 매칭 안내
        warnings.append(
            "사용자의 기본정보에 있는 기술 스택(예: Python, React 등)과 질문 키워드를 활용하여 "
            "특강 제목/설명과 매칭시키고, 관심사에 부합하는 후보를 능동적으로 추천하세요."
        )
            
    return "\n".join(warnings) if warnings else ""

