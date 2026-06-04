# asm-team11-ai-study-Public

AIㆍSW 마에스트로 부산 17기 AI 기술교육 11조

---

# 🤝 소마 메이트 (SoMa Mate)

소프트웨어 마에스트로(SWM) 연수생 전용 **AI 정보 탐색 크롬 확장**.
자연어로 물어보면 멘토·동료 연수생·팀매칭·특강 정보를 찾아 근거와 함께 답합니다.

> 예) *"Next.js 쓰는 풀스택 멘토 추천해줘"* · *"백엔드인데 팀 못 구한 연수생 찾아줘"* · *"강자은 어느 팀이야?"* · *"접수중 AI 특강 있어?"*

## ✨ 기능
- 🧑‍🏫 **멘토 추천** — 스택·분야·창업경험 기반, 추천 이유(근거) 포함
- 👥 **동료 연수생 찾기** — 같은 스택·팀원 모집 여부
- 🤝 **팀매칭 현황** — 누가 어느 팀, 팀별 매칭 멘토
- 📅 **접수중 특강·멘토링** — 남은 자리·일정

## 🏗 아키텍처
```
[크롬 확장]  swmaestro.ai 위 FAB 채팅 위젯 (React+TS+Vite, Shadow DOM)
     │  ① 위젯 마운트 시 로그인필요 데이터를 세션으로 파싱해 백엔드에 전송
     │  ② 사용자 질문 전송
     ▼
[백엔드]  FastAPI + Upstage Solar 에이전트
     - 에이전트 루프: LLM이 도구를 자율 호출 (Intent→Explore→Search→Reflect→Synthesize)
     - 도구: search_mentors / search_trainees / search_teams / search_sessions / list_facets
```

## 🧠 Agentic Workflow — LLM이 스스로 판단하는 방식

이 에이전트는 흐름을 코드로 못박지 않는다. **Solar LLM이 매 턴 "다음에 무엇을 할지" 스스로 결정**하는 도구 호출 루프다. (`backend/app/agent/loop.py`)

```
사용자 질문 + SYSTEM_PROMPT + 대화기록
      │
      ▼  최대 6턴 반복 (MAX_STEPS), temperature 0.1
  Solar 호출 (tools=5개 스키마, tool_choice="auto")
      │
      ├─ tool_calls 있음 → 도구 실행 → 결과를 대화에 추가 → 다시 위로
      └─ tool_calls 없음 → 그게 최종 답변, 반환
```

`tool_choice="auto"` 가 분기의 핵심 — "도구를 더 부를지 / 이제 답할지"를 LLM이 매번 판단한다.

### LLM이 스스로 내리는 판단
1. **어떤 도구를 쓸지 (라우팅)** — 멘토 질문이면 `search_mentors`, 동료면 `search_trainees`, 팀이면 `search_teams`, 특강이면 `search_sessions`
2. **검색 전 탐색이 필요한지** — 표기가 헷갈리면(`Next.js` ≈ `NextJs`) `list_facets` 로 실제 데이터 값을 먼저 확인한 뒤 정확히 검색
3. **결과를 보고 재시도할지 (Reflect)** — 0건이면 조건을 완화해 재검색, 너무 많으면 조건을 더해 좁힘

### 행동 지침 (`SYSTEM_PROMPT`)
- **★절대규칙★** — 멘토/연수생/팀/특강 질문에는 *예외 없이 먼저 도구를 호출*한다. 일반 지식으로 목록·이름을 지어내는 것은 금지. 도구가 0건을 반환하면 "없음"이라고만 답한다. (LLM 환각 방지)
- **5단계 절차** — 분해(Decompose) → 탐색(Explore) → 검색(Search) → 반성·재시도(Reflect) → 종합(Synthesize)

### 동작 예시
```
Q. "나는 Next.js 쓰는데 맞는 풀스택 멘토 있을까?"

[턴1] LLM: list_facets("stacks","fields")   ← '풀스택'은 분야, 'Next.js'는 'NextJs'로 저장됨을 확인
[턴2] LLM: search_mentors(stack="NextJs", field="풀스택")  ← 분해한 두 조건 교차검색
[턴3] LLM: 도구 호출 없음 → "김재훈 멘토 추천 + 근거(NextJs·풀스택 일치) + 신청 링크"
```
같은 질문이라도 결과가 0건이면 LLM이 조건을 완화해 재검색하는 등 **상황에 따라 경로가 달라진다.**

## 📂 구조
```
extension/                 크롬 확장 (MV3)
  src/content/
    index.tsx              Shadow DOM 마운트
    Widget.tsx             FAB 위젯 (드래그·리사이즈·대화기록·온보딩)
    sessions.ts            접수중 특강/멘토링 실시간 파싱
    teams.ts               팀매칭 현황 실시간 파싱
    auth.ts                (로그인 게이팅 — 현재 보류)
  src/lib/api.ts           백엔드 호출
backend/
  app/
    main.py                FastAPI 앱
    routers/chat.py        POST /api/chat, POST /api/context
    agent/loop.py          에이전트 루프 + 시스템 프롬프트
    agent/tools.py         5개 도구
    context_store.py       실시간 데이터(특강·팀) 메모리 캐시
    data/                  mentors.json(227) · trainees.json(150)
  scripts/
    crawl_notion_mentors.py    멘토 재크롤
    crawl_notion_mentees.py    연수생 재크롤 (이메일만, 개인정보 최소)
docs/QUICKSTART.md         로컬 실행 가이드
```

## 🔄 데이터 파이프라인 (2가지)
| 레인 | 데이터 | 출처 | 방식 |
|---|---|---|---|
| **정적** | 멘토·연수생 | 공개 Notion | `scripts/`로 크롤 → JSON 저장 (공유, 가끔 갱신) |
| **실시간** | 특강·팀매칭 | 로그인 필요 SWM 포털 | 확장이 세션으로 파싱 → `/api/context` → 백엔드 캐시 |

> 로그인 필요 데이터는 서버가 직접 못 긁으므로, 확장이 사용자 세션으로 읽어 전달한다.
> 개인정보는 **연수생 이메일만** 수집하며 전화번호·MBTI 등은 제외한다.

## 🚀 실행
**백엔드**
```bash
cd backend && python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # UPSTAGE_API_KEY 입력
uvicorn app.main:app --reload
```
**확장**
```bash
cd extension && npm install && npm run build
# chrome://extensions → 개발자 모드 → dist 폴더 로드
```
자세한 내용은 [docs/QUICKSTART.md](docs/QUICKSTART.md).

## 🛠 기술 스택
React · TypeScript · Vite · FastAPI · Upstage Solar(`solar-pro2`, OpenAI 호환)
