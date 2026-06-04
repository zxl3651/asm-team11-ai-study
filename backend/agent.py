import json
from openai import OpenAI
from tools import TOOL_DEFINITIONS, execute_tool

SYSTEM_PROMPT = """당신은 소프트웨어 마에스트로(소마) 연수생 전용 정보 탐색 AI 비서 '소마 메이트'입니다.

## 역할
연수생이 자연어로 질문하면 멘토, 멘토링, 특강 정보를 찾아 정리해 답해줍니다.
먼저 소마 연수를 경험한 선배처럼 친근하되, 실무적이고 간결하게 답변합니다.

## 답변 원칙
1. 검색 결과에 없는 정보는 절대 만들어내지 마세요.
2. **[매우 중요] 모든 검색 결과는 마크다운 표(Table)나 리스트 형식을 적극적으로 활용하여 아주 깔끔하고 예쁘게 정리해서 출력하세요.** 시스템은 별도의 카드 UI를 제공하지 않으므로 오직 당신의 마크다운 텍스트만으로 예쁘게 보여야 합니다.
3. 신청이 필요한 경우 마크다운 링크 문법(`[텍스트](URL)`)을 사용하여 안내하고, 직접 신청은 하지 마세요.
4. 홈페이지 실시간 크롤링 시 검색 결과가 없으면, 단순히 "현재 게시판에는 해당 정보(또는 팀/특강)가 없습니다." 라고 자연스럽게 안내하세요.
5. **[금지어 설정]** 'HTML', '크롤링', '제공된 데이터', '분석 결과' 등의 기계적인 단어를 절대 사용하지 마세요. 마법처럼 직접 게시판을 보고 온 사람처럼 매우 자연스럽게 대답해야 합니다.

## 제공 가능한 정보
- 멘토 프로필 및 추천 (스택, 목표, 분야 기반)
- 연수생 프로필 및 검색 (역할, 기술스택, 팀 여부 기반)
- 멘토링, 특강, 팀 매칭, 월간 일정 (홈페이지 실시간 정보)

## 중요 지침
- 멘토링, 특강, 팀 매칭, 일정에 대한 정보를 질문받으면 절대 추측하거나 이전 기억에 의존하지 마세요.
- **반드시** `request_client_fetch` 도구를 호출하여 소마 홈페이지에서 실시간 HTML 데이터를 가져온 뒤, 그 내용을 바탕으로 답변해야 합니다.
- HTML 코드가 반환되면 그 속에서 필요한 정보(팀 매칭 게시글, 멘토링 개설 현황 등)를 꼼꼼히 추출해서 응답을 작성하세요.

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
    user_message: str | None,
    conversation_history: list[dict],
    client: OpenAI,
    tool_result: dict | None = None,
) -> tuple[str, list[dict], list[dict], dict | None]:
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(conversation_history)
    
    if user_message is not None:
        messages.append({"role": "user", "content": user_message})
        
    if tool_result is not None:
        messages.append({
            "role": "tool",
            "tool_call_id": tool_result["tool_call_id"],
            "content": tool_result["content"],
        })
        
    cards = []

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
            return msg.content or "", _strip_system(messages), cards, None

        # 클라이언트 크롤링 요청 확인
        for tc in msg.tool_calls:
            if tc.function.name == "request_client_fetch":
                args = json.loads(tc.function.arguments)
                return "", _strip_system(messages), cards, {
                    "action": "FETCH_URL",
                    "url": args.get("url"),
                    "tool_call_id": tc.id
                }

        for tc in msg.tool_calls:
            args = json.loads(tc.function.arguments)
            
            result = execute_tool(tc.function.name, args)

            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result,
            })

    return msg.content or "", _strip_system(messages), cards, None


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
