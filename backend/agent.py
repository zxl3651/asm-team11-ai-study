import json
from openai import OpenAI
from tools import TOOL_DEFINITIONS, execute_tool

SYSTEM_PROMPT = """당신은 소프트웨어 마에스트로(소마) 연수생 전용 정보 탐색 AI 비서 '소마 메이트'입니다.

## 역할
연수생이 자연어로 질문하면 멘토, 멘토링, 특강 정보를 찾아 정리해 답해줍니다.
먼저 소마 연수를 경험한 선배처럼 친근하되, 실무적이고 간결하게 답변합니다.

## 답변 원칙
1. 검색 결과에 없는 정보는 절대 만들어내지 마세요. 없으면 "해당 조건의 정보를 찾지 못했습니다"라고 하세요.
2. 멘토/멘토링을 추천할 때는 왜 추천하는지 이유(매칭 포인트)를 함께 설명하세요.
3. 신청이 필요한 경우 신청 링크를 안내하세요. 직접 신청은 절대 하지 마세요.
4. 남은 자리, 마감일 등 중요한 정보는 강조해서 알려주세요.
5. 답변은 마크다운 형식으로 정리해 가독성을 높이세요.

## 제공 가능한 정보
- 엑스퍼트(소마 선배 연수생) 프로필 및 추천 — 기술 스택, 분야, 자기소개 기반
- 멘토 프로필 및 추천 — 스택, 목표, 관심 분야 기반
- 연수생 프로필 및 검색 — 역할, 기술스택, 팀 여부 기반

## 엑스퍼트란?
소마를 먼저 경험한 선배 연수생으로, 팀 매칭·멘토 매칭·기획심의·중간평가 등 연수 과정 전반에 걸쳐 실질적인 조언을 해줍니다.

## 제공 불가능한 정보
- 개인 연락처, 이메일
- 소마 포털 로그인 정보
"""


def create_client(api_key: str) -> OpenAI:
    return OpenAI(
        api_key=api_key,
        base_url="https://api.upstage.ai/v1",
    )


def run_agent(
    user_message: str,
    conversation_history: list[dict],
    client: OpenAI,
) -> tuple[str, list[dict]]:
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(conversation_history)
    messages.append({"role": "user", "content": user_message})

    for _ in range(5):
        response = client.chat.completions.create(
            model="solar-pro",
            messages=messages,
            tools=TOOL_DEFINITIONS,
            tool_choice="auto",
        )
        msg = response.choices[0].message

        messages.append(_msg_to_dict(msg))

        if not msg.tool_calls:
            return msg.content, _strip_system(messages)

        for tc in msg.tool_calls:
            args = json.loads(tc.function.arguments)
            result = execute_tool(tc.function.name, args)
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result,
            })

    return msg.content or "", _strip_system(messages)


def _msg_to_dict(msg) -> dict:
    d = {"role": msg.role}
    if msg.content is not None:
        d["content"] = msg.content
    if msg.tool_calls:
        d["tool_calls"] = [
            {
                "id": tc.id,
                "type": tc.type,
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                },
            }
            for tc in msg.tool_calls
        ]
    return d


def _strip_system(messages: list[dict]) -> list[dict]:
    return [m for m in messages if m.get("role") != "system"]
