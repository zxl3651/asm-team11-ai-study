# 소마 포털 실시간 크롤링 구현 계획

> **기본 방향**: Mock 데이터를 최소화하고, 확장 프로그램의 Content Script가 소마 포털 DOM에서 실시간으로 데이터를 파싱하여 사용한다.  
> **참고1, 2, 3**: 실제 데이터가 아닌 **DOM 구조(테이블/셀렉터/클래스명)의 참고 자료**이며, 실제 크롤링 시 그 시점의 동적 데이터가 파싱된다.

---

## 1. 크롤링 대상 및 DOM 구조 분석

### 1-1. 멘토링/특강 게시판 (참고1 기반)

- **URL 패턴**: `/busan/sw/mypage/mentoLec/list.do?menuNo=200046`
- **테이블 셀렉터**: `#listFrm > div.boardlist.mt50 > table > tbody > tr`
- **각 행(tr)에서 추출할 필드**:

| td 인덱스 | 클래스/셀렉터 | 추출 데이터 | 비고 |
|-----------|-------------|-----------|------|
| 1 | `td:nth-child(1)` (pc_only) | NO | 번호 |
| 2 | `td.tit` → 내부 `a` 태그 | 제목 + 상세 URL | `[자유 멘토링]` / `[멘토 특강]`으로 type 분류 |
| 2 | `td.tit` → `.ab` div | 상태 | `[접수중]` 또는 `[마감]` |
| 3 | `td:nth-child(3)` (pc_only) | 접수기간 | `2026-06-01 ~ 2026-06-29` 형태 |
| 4 | `td:nth-child(4)` (pc_only) | 진행날짜 + 시간 | `2026-06-29(월)\n 19:30  ~ 21:00` → dateStr, timeRangeStr 분리 |
| 5 | `td:nth-child(5)` (pc_only) | 모집인원 | `현재/최대` 형태 (예: `5/5`) |
| 6 | `td:nth-child(6)` (pc_only) | 개설 승인 | `OK` 또는 `-` |
| 7 | `td:nth-child(7)` (pc_only) | 접수 상태 | `[접수중]` / `[마감]` |
| 8 | `td:nth-child(8)` (pc_only) | 작성자(멘토명) | 텍스트 |
| 9 | `td:nth-child(9)` (pc_only) | 등록일 | `2026-06-01` 형태 |

- **추가 데이터: 캘린더 내 일정 (`resultList` JavaScript 배열)**
  - 참고1의 `contentsInit()` 함수 내부에 `resultList.push({...})` 형태로 현재 달의 일정이 인라인 삽입됨
  - 페이지의 `<script>` 태그에서 정규표현식으로 `resultList` 배열을 추출
  - 각 항목: `subjectTitle`, `subject`, `date`, `url`, `category` (`MRC010`=자유멘토링, `MRC020`=멘토특강), `categoryNm`

### 1-2. 팀매칭 현황 (참고2 기반)

- **URL 패턴**: `/busan/sw/mypage/myTeam/team.do?menuNo=200093`
- **테이블 셀렉터**: `table.tbl-st1_sui.t.team > tbody > tr`
- **각 행에서 추출할 필드**:

| td 인덱스 | 추출 데이터 | 비고 |
|-----------|-----------|------|
| 1 | NO | 번호 |
| 2 | 팀명 | `td.popuser > strong > a` 텍스트 |
| 3 | 팀장 | `td.pc_only > strong > a` 텍스트 |
| 4 | 팀원 목록 | `td.popuser` 내 `strong > a` 텍스트들 (복수) |
| 5 | 멘토명 | `td.popuser` 내 `strong > a` 텍스트 |
| 6 | 프로젝트 명 | (비어있을 수 있음) |
| 7 | ICT기술분류(대) | (비어있을 수 있음) |
| 8 | ICT기술분류(중) | (비어있을 수 있음) |

### 1-3. 월간일정 (참고3 기반)

- **URL 패턴**: `/busan/sw/mypage/schedule/list.do?menuNo=200043`
- **데이터 소스**: 페이지의 `<script>` 태그 내에 `resultList` JavaScript 배열로 일정이 인라인 삽입됨
- **추출 방법**: `document.querySelectorAll('script')`에서 `resultList`를 포함하는 스크립트를 찾아 정규표현식으로 파싱
- **각 항목**: `subjectTitle`, `date`, `url`, `category`, `categoryNm`, `time` 등

---

## 2. 데이터 흐름 아키텍처

```
소마 포털 (사용자 브라우저)
    ↓ [Content Script: somaParser.ts]
    ↓ DOM 파싱 (현재 페이지 URL에 따라 적절한 파서 실행)
    ↓
chrome.storage.local
    ├── "parsedMentorings"   : 멘토링/특강 목록 배열
    ├── "parsedTeamInfo"     : 팀 매칭 정보 배열
    ├── "parsedSchedule"     : 월간 일정 배열 (캘린더 resultList)
    └── "parseTimestamp"     : 마지막 수집 시각
    ↓ [Side Panel: ChatPanel.tsx]
    ↓ chrome.storage.local에서 로드 + 메시지 전송 시 함께 전달
    ↓
Backend (FastAPI)
    ↓ /chat 엔드포인트에서 수신 → mentorings_realtime.json 갱신
    ↓
LangGraph Agent
    ↓ search_mentorings 등 도구 호출 시 실시간 파싱 데이터 우선 사용
    ↓
사용자에게 응답
```

---

## 3. 파일별 수정 계획

### 3-1. [신규] `extension/src/somaParser.ts` — Content Script

소마 포털 페이지 로드 시 자동 실행되는 Content Script.  
현재 URL 경로에 따라 적절한 파서를 호출하고, 결과를 `chrome.storage.local`에 저장한다.

```typescript
// 핵심 구조 (의사 코드)

// 1. URL 기반 분기
const path = window.location.pathname;

if (path.includes("mentoLec/list.do")) {
  // 멘토링/특강 게시판 파싱
  const mentorings = parseMentoringListPage(document);
  const calendarItems = parseCalendarResultList(document);
  chrome.storage.local.set({
    parsedMentorings: mentorings,
    parsedSchedule: calendarItems,
    parseTimestamp: Date.now()
  });
}

if (path.includes("myTeam/team.do")) {
  // 팀매칭 정보 파싱
  const teams = parseTeamPage(document);
  chrome.storage.local.set({
    parsedTeamInfo: teams,
    parseTimestamp: Date.now()
  });
}

if (path.includes("schedule/list.do")) {
  // 월간일정 파싱
  const schedule = parseMonthlySchedule(document);
  chrome.storage.local.set({
    parsedSchedule: schedule,
    parseTimestamp: Date.now()
  });
}

// 파싱 완료 알림
chrome.runtime.sendMessage({ type: "PARSE_COMPLETE", url: path });
```

**파서 함수 세부:**

- `parseMentoringListPage(doc)`:
  - `soma-calendar`의 `parseLectureListRow()` 로직 참고
  - `#listFrm > div.boardlist.mt50 > table > tbody > tr` 순회
  - 각 `tr`에서 `td` 순서대로 데이터 추출
  - 제목에서 `[자유 멘토링]` / `[멘토 특강]` 패턴으로 type 분류
  - 진행날짜/시간 분리: `td:nth-child(4)` 텍스트를 `\n`으로 split → dateStr, timeRangeStr
  - 모집인원: `td:nth-child(5)` 텍스트에서 `현재/최대` 파싱

- `parseCalendarResultList(doc)`:
  - `<script>` 태그들을 순회하며 `resultList.push` 패턴이 있는 스크립트 텍스트를 찾음
  - 정규표현식으로 각 `push({...})` 내부의 JSON 객체를 추출
  - `subjectTitle`, `date`, `url`, `category`, `categoryNm` 반환

- `parseTeamPage(doc)`:
  - `table.tbl-st1_sui.t.team > tbody > tr` 순회
  - 각 `tr`에서 팀명, 팀장, 팀원(복수 `a` 태그), 멘토명 추출

- `parseMonthlySchedule(doc)`:
  - 참고3과 동일한 `resultList` 파싱 로직

### 3-2. [수정] `extension/manifest.json`

```json
{
  "permissions": ["sidePanel", "storage", "activeTab"],
  "host_permissions": [
    "http://localhost:8000/*",
    "https://www.swmaestro.ai/*",
    "https://swmaestro.org/*"
  ],
  "content_scripts": [{
    "matches": [
      "https://www.swmaestro.ai/busan/sw/mypage/*",
      "https://www.swmaestro.ai/sw/mypage/*"
    ],
    "js": ["somaParser.js"],
    "run_at": "document_idle"
  }]
}
```

### 3-3. [수정] `extension/src/background.ts`

```typescript
// 기존 코드 유지 +

// Content Script로부터 파싱 완료 메시지 수신
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === "PARSE_COMPLETE") {
    console.log(`[SoMa Mate] 데이터 수집 완료: ${message.url}`);
    // Side Panel에 알림 전달 (필요 시)
  }
});
```

### 3-4. [수정] `extension/src/components/ChatPanel.tsx`

- `getMockMentorings()` → 제거, `chrome.storage.local.get(["parsedMentorings"])` 사용
- `getMockCalendar()` → 제거, `chrome.storage.local.get(["parsedSchedule"])` 사용
- fallback: 파싱 데이터가 없으면 빈 배열 + "소마 포털에서 데이터를 수집해주세요" 안내
- 캘린더 상태바에 마지막 동기화 시각 표시

### 3-5. [수정] `extension/webpack.config.js`

`somaParser` 엔트리 포인트 추가:

```javascript
entry: {
  sidepanel: "./src/sidepanel.tsx",
  background: "./src/background.ts",
  somaParser: "./src/somaParser.ts"  // Content Script 추가
},
```

### 3-6. [수정] `backend/tools.py`

- `_load_mentorings()`: 실시간 파싱 데이터(`mentorings_realtime.json`)의 필드 구조 확장 처리
  - 프론트에서 보내는 파싱 데이터 필드: `title`, `type`, `dateStr`, `timeRangeStr`, `status`, `author`, `currentParticipants`, `maxParticipants`, `registrationPeriod`, `url`
  - 기존 Mock 멘토링 데이터의 필드(`stacks`, `domain`, `goals` 등)가 없을 수 있으므로 fallback 처리
- 멘토(`mentors.json`) / 연수생(`trainees.json`) Mock 데이터는 **기존 그대로 유지**

### 3-7. [수정] `backend/main.py`

- `/chat` 엔드포인트의 `ChatRequest`에 `team_info` 필드 추가 (선택적)
- `available_mentorings` 수신 시 파싱 데이터의 새로운 구조 처리

---

## 4. Mock 데이터 정책

| 데이터 | 소스 | 비고 |
|--------|------|------|
| 멘토 정보 | `backend/data/mentors.json` (Mock 유지) | 포털에서 멘토 목록 크롤링 가능하지만 우선 Mock |
| 연수생 정보 | `backend/data/trainees.json` (Mock 유지) | 포털의 팀원 정보로 보강 가능 |
| 멘토링/특강 목록 | **실시간 크롤링** → `mentorings_realtime.json` | Content Script 파싱 데이터 우선 |
| 사용자 일정 | **실시간 크롤링** → `user_calendar.json` | 월간일정/캘린더 파싱 데이터 |
| 팀 정보 | **실시간 크롤링** → ChatRequest로 전달 | 팀매칭 페이지 파싱 |

---

## 5. 구현 순서

1. `somaParser.ts` Content Script 구현 (3개 파서 함수)
2. `webpack.config.js`에 엔트리 추가 + `manifest.json` 수정
3. `background.ts` 메시지 리스너 추가
4. `ChatPanel.tsx` Mock 제거 → `chrome.storage.local` 연동
5. `backend/tools.py` 실시간 데이터 구조 확장
6. `backend/main.py` `team_info` 필드 추가
7. 빌드 + 테스트

---

## 6. 검증 방법

- 확장 프로그램을 크롬에 로드 → 소마 포털 멘토링 게시판 접속 → DevTools Console에서 `chrome.storage.local.get(null, console.log)` 으로 파싱 데이터 확인
- Side Panel에서 "접수중인 특강 알려줘" 질문 → 실시간 데이터 기반 응답 확인
