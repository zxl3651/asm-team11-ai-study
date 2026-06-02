# 소마 메이트 (SoMa Mate)

AIㆍSW 마에스트로 부산 17기 AI 기술교육 11조

소마 연수생이 자연어로 멘토·멘토링·특강·연수생 정보를 탐색할 수 있는 AI 비서 챗봇입니다.  
Chrome 확장 프로그램(사이드패널)으로 동작하며, FastAPI 백엔드에서 Upstage Solar API를 사용한 Agentic 루프로 응답합니다.

---

## 기술 스택

| 영역 | 기술 |
|------|------|
| 백엔드 | Python 3.11+, FastAPI, Upstage Solar API (OpenAI 호환) |
| 프론트엔드 | Chrome Extension (Manifest V3), React 18, TypeScript, Webpack |
| 데이터 수집 | Playwright (Notion 크롤링), LLM 기반 구조화 파싱 |

---

## 프로젝트 구조

```
agentic_workflow/
├── backend/
│   ├── main.py            # FastAPI 서버 진입점
│   ├── agent.py           # Agentic 루프 (LLM 호출 + Tool Calling)
│   ├── tools.py           # 검색 도구 정의 및 실행
│   ├── crawl_notion.py    # 노션 크롤러
│   ├── requirements.txt
│   ├── .env.example       # API 키 설정 예시
│   └── data/
│       ├── mentors.json   # 멘토 데이터 (135명)
│       ├── trainees.json  # 연수생 데이터 (50명)
│       └── mentorings.json # 멘토링/특강 데이터
├── extension/
│   ├── src/
│   │   ├── sidepanel.tsx          # 사이드패널 진입점
│   │   ├── components/
│   │   │   ├── ChatPanel.tsx      # 채팅 UI
│   │   │   └── MessageCard.tsx    # 메시지 카드
│   │   └── background.ts          # 서비스 워커
│   ├── dist/              # 빌드 결과물 (Chrome에 로드)
│   ├── manifest.json
│   └── package.json
└── start.sh               # 백엔드 빠른 시작 스크립트
```

---

## 시작하기

### 사전 준비

- Python 3.11 이상
- Node.js 18 이상
- **Upstage API 키** — [https://console.upstage.ai](https://console.upstage.ai) 에서 발급

---

### 1. 백엔드 설정

```bash
cd backend

# 가상환경 생성 및 활성화
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate

# 의존성 설치
pip install -r requirements.txt

# 환경변수 설정
cp .env.example .env
```

`.env` 파일을 열어 API 키를 입력합니다:

```
UPSTAGE_API_KEY=여기에_실제_키_입력
```

### 2. 백엔드 실행

```bash
# venv 활성화된 상태에서
cd backend
python main.py
```

서버가 `http://localhost:8000` 에서 실행됩니다.  
API 문서는 `http://localhost:8000/docs` 에서 확인 가능합니다.

---

### 3. Chrome 확장 프로그램 로드

빌드 결과물(`extension/dist/`)이 이미 포함되어 있으므로 별도 빌드 없이 바로 로드할 수 있습니다.

1. Chrome 주소창에 `chrome://extensions` 입력
2. 우측 상단 **개발자 모드** 켜기
3. **압축해제된 확장 프로그램을 로드합니다** 클릭
4. `extension/dist/` 폴더 선택

이후 Chrome 우측 상단 확장 아이콘 → **소마 메이트** → 사이드패널 열기로 사용합니다.

---

### 4. (선택) 확장 프로그램 소스 수정 후 재빌드

```bash
cd extension
npm install
npm run build    # 프로덕션 빌드
# 또는
npm run dev      # 파일 변경 감지 자동 빌드
```

빌드 후 `chrome://extensions` 에서 새로고침 버튼을 눌러야 변경사항이 반영됩니다.

---

## API 엔드포인트

| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `/health` | 서버 상태 확인 |
| POST | `/chat` | AI 채팅 (Agentic 루프) |
| DELETE | `/chat/{session_id}` | 대화 세션 초기화 |
| POST | `/mentors/search` | 멘토 직접 검색 |
| POST | `/mentorings/search` | 멘토링/특강 직접 검색 |

**채팅 요청 예시:**
```json
POST /chat
{
  "message": "Python 잘하는 창업 멘토 추천해줘",
  "session_id": "user_001"
}
```

---

## Agentic Workflow 동작 방식

```
사용자 메시지
     ↓
[LLM] 어떤 도구가 필요한지 판단
     ↓
[Tool] search_mentors / search_mentorings / search_trainees 실행
     ↓
[LLM] 검색 결과를 바탕으로 자연어 응답 생성
     ↓ (필요시 최대 5회 반복)
최종 답변 반환
```

도구 3가지: `search_mentors`, `search_mentorings`, `search_trainees`

---

## 데이터 재크롤링 (선택)

노션 페이지에서 최신 데이터를 다시 수집할 때:

```bash
cd backend
source venv/bin/activate

# Playwright 브라우저 설치 (최초 1회)
playwright install chromium

# 크롤링 실행
python crawl_notion.py mentors    # 멘토만
python crawl_notion.py trainees   # 연수생만
python crawl_notion.py all        # 전체
```

> 크롤링 중 중단되어도 `*_progress.json` 파일로 이어서 재개됩니다.

---

## 문제 해결

**포트 충돌 오류 (Address already in use)**
```bash
lsof -ti :8000 | xargs kill -9
```

**Playwright 브라우저 없음 오류**
```bash
playwright install chromium
```

**UPSTAGE_API_KEY 미설정 오류**  
`backend/.env` 파일에 키가 올바르게 입력되었는지 확인하세요.
