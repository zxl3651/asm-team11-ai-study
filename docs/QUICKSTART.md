# 소마 메이트 — 로컬 실행 가이드

## 1. 백엔드 (FastAPI + Upstage Solar)

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 환경변수 설정
cp .env.example .env
# .env 를 열어 UPSTAGE_API_KEY 를 본인 키로 채운다

# 서버 실행 (http://localhost:8000)
uvicorn app.main:app --reload
```

확인:
```bash
curl http://localhost:8000/health
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"Spring 잘하고 창업 경험 있는 멘토 추천해줘"}'
```

## 2. 크롬 확장 (React + TS + Vite)

```bash
cd extension
npm install
npm run build      # dist/ 생성 (개발 중엔 npm run dev 로 watch)
```

크롬에 로드:
1. `chrome://extensions` 접속 → 우측 상단 **개발자 모드** 켜기
2. **압축해제된 확장 프로그램을 로드** → `extension/dist` 폴더 선택
3. 툴바의 확장 아이콘 클릭 → 사이드패널 채팅 열림

> ⚠️ 아이콘 PNG(icon16/48/128)는 아직 없음. 임시로 `public/icons/`에 넣거나
> manifest 의 `icons`/`action` 항목을 비워도 동작한다.

## 데이터 갱신 (Notion 크롤링)
소마 공개 Notion DB를 긁어 `app/data/*.json`을 새로 채운다. 각각 독립 실행.
```bash
cd backend && source .venv/bin/activate
python scripts/crawl_notion_mentors.py   # 멘토  → mentors.json  ("저장 완료: N명")
python scripts/crawl_notion_mentees.py   # 연수생 → trainees.json ("저장 완료: N명")
```
- 멘토: `swmaestromain.notion.site` 공개 멘토 DB
- 연수생: `asm-busan.notion.site/mentee-list` (⚠️ 개인정보는 이메일만 수집, 전화번호·MBTI·거주지 등 제외)

백엔드는 매 요청마다 JSON을 읽으므로 재시작 불필요.

### 특강/멘토링·팀매칭 (실시간, 크롤 스크립트 없음)
**로그인 필요** 데이터라 정적 크롤이 불가하다. 확장이 세션으로 파싱해 백엔드에 올린다:
- `src/content/sessions.ts` → 접수중 특강/멘토링(`mentoLec/list.do`)
- `src/content/teams.ts` → 팀매칭 현황(`myTeam/team.do`, 전체 팀·멤버·멘토)
- 위젯 마운트 시 둘 다 파싱 → `POST /api/context {sessions, teams}` → 백엔드 캐시
- `search_sessions`·`search_teams` 도구가 캐시 조회. 연수생 팀 구성여부도 팀매칭 캐시로 판별
  (노션의 옛 "찾은 팀원" 정보는 폐기)

## Upstage API 키 발급
1. https://console.upstage.ai 로그인
2. 좌측 **API Keys** → **Create new key**
3. 발급된 `up_...` 키를 `backend/.env` 의 `UPSTAGE_API_KEY` 에 붙여넣기

모델은 `solar-pro2`(기본). OpenAI SDK 와 100% 호환이라
`base_url=https://api.upstage.ai/v1` 만 바꿔주면 그대로 쓸 수 있다.
