# 소마 메이트 (SoMa Mate) 🎓

> 소프트웨어 마에스트로 부산 연수생을 위한 에이전트형 AI 멘토·멘토링 탐색 크롬 확장 프로그램

## 📋 주요 기능

### 🧑‍🏫 멘토 검색 및 추천
- 기술 스택, 목표(취업/창업), 관심 분야 기반 멘토 매칭
- "Spring 잘 아는 멘토 추천해줘"와 같은 자연어 질문 지원

### 📚 멘토링·특강 및 팀매칭 현황 조회
- 소마 홈페이지 실시간 정보를 크롤링하여 데이터 제공
- 분야별, 일정별 필터링, 팀 모집 현황 및 빈 포지션 확인

### 🤖 에이전트형 AI 워크플로우
1. **사용자 질문 접수** — 자연어 질문 파악
2. **도구 선택 및 실행** — LLM이 필요한 도구(`search_mentors`, `search_trainees`, `request_client_fetch` 등) 호출
3. **클라이언트 사이드 크롤링** — 실시간 데이터가 필요한 경우 확장 프로그램의 세션을 통해 소마 홈페이지 크롤링 (로그인 필수)
4. **결과 종합 및 검증** — 검색/크롤링 결과를 종합하여 마크다운 형태로 자연스러운 답변 생성

## 🚀 설치 및 실행 방법

### 1. 백엔드 설정

터미널을 열고 다음 명령어들을 순서대로 입력하여 환경을 설정합니다:

```bash
cd backend

# 가상환경 생성 및 활성화
python -m venv venv
# Windows (PowerShell):
.\venv\Scripts\activate
# Mac/Linux:
# source venv/bin/activate

# 의존성 설치
pip install -r requirements.txt

# 환경변수 설정 파일 복사
cp .env.example .env
```

`.env` 파일을 열어 발급받은 API 키를 직접 입력합니다:

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

### 3. 크롬에 확장 프로그램 로드
1. Chrome에서 `chrome://extensions` 접속
2. 우측 상단 **개발자 모드** 활성화
3. **압축해제된 확장 프로그램을 로드합니다** 클릭
4. 프로젝트 폴더 내의 `extension` 폴더 선택

### 3. 사용하기 (중요)
1. **[중요]** 팀매칭, 멘토링 등의 실시간 데이터를 조회하기 위해서는 브라우저가 **소마 홈페이지(https://swmaestro.ai)에 로그인된 상태**여야 합니다.
2. 소마 부산 홈페이지에서 확장 프로그램 아이콘 우클릭 → **사이드 패널에서 열기** 선택 (또는 자동 활성화)
3. 채팅창에 자연어로 질문 입력!

## 💡 사용 예시

| 질문 | 기능 |
|------|------|
| "Spring 잘 아는 멘토 추천해줘" | 멘토 검색 (노션 데이터 기반) |
| "프론트엔드 연수생 찾아줘" | 연수생 검색 (노션 데이터 기반) |
| "이번 달 특강 뭐 있어?" | 특강 실시간 조회 (소마 홈페이지 크롤링) |
| "프론트 구하는 팀 있어?" | 팀매칭 실시간 조회 (소마 홈페이지 크롤링) |

## 🏗️ 기술 스택

- **프론트엔드**: Chrome Extension (Manifest V3), Vanilla JS, CSS
- **백엔드**: Python, FastAPI
- **AI**: Upstage Solar API (`solar-pro`)
- **디자인**: 다크/라이트 모드, 심플하고 깔끔한 마크다운 UI

## 📁 프로젝트 구조

```text
soma-mate/
├── backend/                # Python FastAPI 서버 & 에이전트 로직
│   ├── main.py             # FastAPI 엔드포인트
│   ├── agent.py            # LLM 에이전트 로직
│   ├── tools.py            # 에이전트 도구 (검색, 크롤링 URL 매핑)
│   ├── crawl_notion.py     # 노션 크롤러 (멘토/연수생 데이터 사전 수집용)
│   └── data/               # 멘토, 연수생 JSON 데이터
├── extension/              # Chrome Extension 프론트엔드
│   ├── manifest.json       # 확장 프로그램 설정
│   ├── background.js       # Service Worker (이벤트 감지)
│   ├── sidepanel.html      # 사이드 패널 HTML
│   ├── sidepanel.css       # 사이드 패널 스타일
│   └── sidepanel.js        # UI 로직 및 백엔드 연동
└── start.sh                # 백엔드 서버 실행 쉘 스크립트 (Mac/Linux용)
```

## 👥 팀원

이성현, 김민수, 김수민, 한우진, 송수민
