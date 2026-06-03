"""에이전트 루프 (Intent → Plan → Act → Synthesize).

Upstage Solar 의 function calling 으로 도구를 자율 호출하고,
도구 결과를 종합해 근거와 함께 자연어로 답한다.
"""

import json

from app.agent.llm import MODEL, client
from app.agent.tools import TOOL_IMPL, TOOL_SCHEMAS

SYSTEM_PROMPT = """너는 '소마 메이트' — 소프트웨어 마에스트로 연수생 전용 정보 탐색 도우미다.
먼저 연수를 경험한 선배처럼 간결하고 실무적으로 답한다.

규칙:
- 멘토/멘토링/특강을 찾을 때는 반드시 제공된 도구를 호출해 실제 데이터를 근거로 답한다.
- 도구 결과에 없는 멘토·일정은 절대 지어내지 말고 '정보 없음'이라고 명확히 말한다.
- 답변은 '추천 + 이유(근거 항목)' 형식으로 정리한다.
- 도구를 호출할 때, 사용자가 명시하지 않은 조건(파라미터)은 절대 임의로 채우지 말고 비워 둔다. 검색을 과하게 좁히지 않는다. (예: 사용자가 스택만 말했으면 field 는 비운다)
- 멘토링 신청·팀 합류 같은 실제 액션은 직접 실행하지 말고 apply_url 링크 안내까지만 한다.
"""

MAX_STEPS = 5


def run_agent(user_message: str, history: list[dict] | None = None) -> str:
    """한 번의 사용자 메시지에 대해 에이전트 루프를 돌려 최종 답변 문자열을 반환."""
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": user_message})

    for _ in range(MAX_STEPS):
        resp = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=TOOL_SCHEMAS,
            tool_choice="auto",
            temperature=0.3,
        )
        msg = resp.choices[0].message

        # 도구 호출이 없으면 최종 답변
        if not msg.tool_calls:
            return msg.content or ""

        # 도구 호출을 실행하고 결과를 messages 에 다시 넣는다 (다단계 추론)
        messages.append(msg.model_dump(exclude_none=True))
        for call in msg.tool_calls:
            fn = TOOL_IMPL.get(call.function.name)
            args = json.loads(call.function.arguments or "{}")
            result = fn(**args) if fn else {"error": "unknown tool"}
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": json.dumps(result, ensure_ascii=False),
                }
            )

    return "죄송해요, 답을 정리하지 못했어요. 질문을 조금 더 구체적으로 해주실래요?"
