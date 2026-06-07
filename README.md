# asm-team11-ai-study-Public

AIㆍSW 마에스트로 부산 17기 AI 기술교육 11조

---

# 🤝 소마 메이트 (SoMa Mate)

소프트웨어 마에스트로(SWM) 연수생 전용 **AI 정보 탐색 크롬 확장**.
소마 포털 위에 뜨는 채팅 위젯에 자연어로 물어보면, 멘토·동료 연수생·팀매칭·특강·일정 정보를 찾아 근거와 함께 답하고 **처리 과정과 일정을 시각화**합니다.

> 예) *"React 쓰는 풀스택 멘토 추천해줘"* · *"김민수 연수생은 어느 팀이야?"* · *"접수중 AI 특강 있어?"* · *"우리 팀 전원이 2시간 회의할 수 있는 시간 찾아줘"*

## ✨ 기능
- 🧑‍🏫 **멘토 추천** — 스택·분야·멘토유형·창업경험 교차검색, 일치 근거 포함
- 👥 **동료 연수생 찾기** — 스택·팀원 모집 여부 기반
- 🤝 **팀매칭 현황** — 임의 연수생/팀명으로 소속 팀·매칭 멘토 조회
- 📅 **접수중 특강·멘토링** — 남은 자리·일정, 과거/중복/충돌 일정 자동 제외 (요청 기간에 접수중이 없으면 가까운 일정으로 확장 추천)
- 🗓 **팀 회의 시간 찾기** — 팀원 전원의 멘토링/특강 신청 일정을 반영한 공통 가용 시간
- 📊 **시각화 탭** — 주간 일정 캘린더 + 에이전트 처리 흐름(mermaid)을 채팅과 분리된 화면으로
- ⚡ **실시간 처리 표시** — SSE 스트리밍으로 조회 단계가 진행되는 모습을 그대로 노출
- 🛡 **범위 제한 + 프롬프트 우회 방어** — 소마 정보 외 질문 거절, 지시 무시·탈옥 시도 차단

## 🏗 아키텍처
```
[크롬 확장]  swmaestro.ai / swmaestro.org 위 FAB 채팅 위젯 (React+TS+Vite, Shadow DOM)
     │  ① "포털 데이터 동기화" 버튼 → 로그인 세션으로 포털 페이지를 파싱해 백엔드에 전송 (POST /sync)
     │  ② 사용자 질문 전송 (POST /chat, SSE 스트리밍)
     ▼
[백엔드]  FastAPI + LangGraph 에이전트 + Upstage Solar(solar-pro3)
     - 그래프: 인텐트 분류 → 데이터 준비 확인 → 도구 호출 루프 → 답변 합성
     - 저장소: SQLite(정규화 truth source) + ChromaDB(벡터 RAG)
     - 응답: Server-Sent Events 로 처리 단계(status) + 최종 답변(complete) 스트리밍
```

## 🧠 Agentic Workflow — LLM이 스스로 판단하는 도구 루프

흐름을 코드로 못박지 않고 **Solar LLM이 매 턴 "다음에 무엇을 할지"를 결정**하는 LangGraph 상태 그래프다. (`backend/agent.py`)

```
질문 → [intent_node]  요청을 7개 처리 경로 중 하나로 분류 (범위 밖이면 out_of_scope → 즉시 거절)
     → [readiness_node]  필요한 동기화 데이터가 준비됐는지 확인 (없으면 안내)
     → [agent]  Solar가 필요한 도구를 (병렬로) 호출 / 또는 최종 답변 작성
     → [action]  도구 실행 → 결과를 대화에 추가 → 다시 agent 로
     → (수렴) 수집한 결과만 근거로 최종 한국어 답변
```

### LLM이 스스로 내리는 판단
1. **경로 분류** — schedule_check / lecture_recommendation / mentor_recommendation / team_info / trainee_search / personal_info / general, 그리고 범위 밖이면 out_of_scope
2. **도구 선택·병렬 호출** — 한 질문에 여러 도구가 필요하면 첫 턴에 묶어서 호출
3. **검색 전 탐색** — 표기가 헷갈리면(`Next.js` ≈ `NextJs`) `list_facets`로 실제 값을 먼저 확인
4. **재시도(Reflect)** — 0건이면 조건 완화, 과다하면 조건 추가. 반복 한도 도달 시 수집 결과만으로 답변 합성

### 신뢰성 가드
- **근거 우선** — 날짜·시간·이름·팀은 도구 결과의 구조화 필드만 사용. 벡터 검색은 후보 탐색 보조용
- **추론 누출·빈 응답 복구** — 추론 모델이 사고 과정을 노출하거나 빈 응답을 반환하면 감지해 수집 결과로 깨끗하게 재합성(그래도 실패 시 안내 문구로 폴백, 빈 화면 방지)
- **범위/보안 가드** — 소마 포털 정보 외 질문 거절, "이전 지시 무시"·시스템 프롬프트 노출 요구·탈옥 시도 차단, 도구 결과 속 명령형 문장도 데이터로만 취급

### 에이전트 도구
| 도구 | 용도 | 데이터 소스 |
|---|---|---|
| `search_mentors` / `list_facets` | 멘토 교차검색 / 실제 facet 값 확인 | 정적 JSON (`data/mentors.json`) |
| `search_trainees` | 동료 연수생 탐색 | 정적 JSON (`data/trainees.json`) |
| `search_mentorings` / `vector_search_mentorings` | 특강·멘토링 검색 / 의미 검색 | SQLite + ChromaDB |
| `get_team_info` | 연수생/팀명 기준 팀 매칭 조회 | SQLite |
| `get_participant_registrations` | 참여자 신청 특강/멘토링 | SQLite |
| `get_team_participant_schedule` / `get_free_slots` | 팀원별 일정 / 공통 빈 시간 | SQLite |
| `get_user_calendar` | 사용자 월간 일정 | SQLite |

## 📂 구조
```
extension/                      크롬 확장 (MV3)
  src/content/
    index.tsx                   Shadow DOM 마운트
    Widget.tsx                  FAB 위젯 (드래그·리사이즈, 채팅/시각화 탭, SSE, 동기화 UI)
    sync.ts                     포털 페이지 파싱 → POST /sync (수동 동기화)
    components/
      ScheduleCalendar.tsx      ```schedule 코드블록 → 주간 캘린더 렌더
      WorkflowDiagram.tsx       mermaid 처리 흐름 렌더 (pan/zoom)
  src/lib/
    api.ts                      /chat SSE 스트림 소비
    parserUtils.ts              포털 HTML 파서 (팀/일정/멘토링)
backend/
  main.py                       FastAPI 앱 (/chat, /sync, ...)
  agent.py                      LangGraph 에이전트 그래프
  agent_prompts.py              시스템 프롬프트 + 인텐트별 정책 + 범위/보안 가드
  agent_intent.py               인텐트 분류·정규화·데이터 준비 판정
  tools.py / mentor_tools.py    에이전트 도구
  database.py                   SQLite 정규화 저장소
  vector_store.py               ChromaDB 벡터 RAG
  workflow_trace.py             처리 흐름 mermaid 생성
  data_validation.py            수집 데이터 품질 검증
  crawl_notion.py               멘토 Notion 크롤 (정적 데이터 갱신)
  data/                         mentors.json(227) · trainees.json(150)  ※ soma.db 는 런타임 생성
start.sh                        백엔드 실행 스크립트 (venv·의존성 자동)
```

## 🔄 데이터 파이프라인 (2가지)
| 레인 | 데이터 | 출처 | 방식 |
|---|---|---|---|
| **정적** | 멘토·연수생 | 공개 Notion | `crawl_notion.py`로 크롤 → JSON 저장 (공유, 가끔 갱신) |
| **실시간** | 특강·멘토링·팀매칭·일정 | 로그인 필요 SWM 포털 | 확장이 세션으로 파싱 → `POST /sync` → SQLite 정규화 + ChromaDB 인덱싱 |

> 로그인 필요 데이터는 서버가 직접 못 긁으므로, 확장이 사용자 세션(`credentials: include`)으로 읽어 전달한다.
> 동기화로 생성되는 `soma.db`·`chroma_data/` 는 개인정보를 포함하므로 저장소에 커밋하지 않는다.

## 🌐 백엔드 API
| 메서드·경로 | 설명 |
|---|---|
| `POST /chat` | 질문 처리 (SSE: `status` 단계 → `complete` 최종답변 + workflow mermaid) |
| `DELETE /chat/{session_id}` | 대화 세션 초기화 |
| `POST /sync` | 파싱된 포털 데이터 저장 (SQLite 정규화 + 벡터 인덱싱) |
| `DELETE /sync` | 동기화 데이터 초기화 |
| `GET /sync/status` · `GET /health` | 동기화 현황 / 헬스체크 |

## 🚀 실행
**백엔드** (Python 3.9 ~ 3.13)
```bash
./start.sh            # venv 생성·의존성 설치·서버 기동 자동 (http://localhost:8000)
# 또는 수동:
cd backend && python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # UPSTAGE_API_KEY 입력
python main.py
```
**확장**
```bash
cd extension && npm install && npm run build
# chrome://extensions → 개발자 모드 → "압축해제된 확장 프로그램을 로드" → extension/dist 폴더
```
이후 소마 포털(swmaestro.ai/org)에 **로그인**한 상태에서 우하단 위젯 → **포털 데이터 동기화** → 질문.

## 🛠 기술 스택
React · TypeScript · Vite · FastAPI · LangChain/LangGraph · Upstage Solar(`solar-pro3`) · SQLite · ChromaDB · mermaid
