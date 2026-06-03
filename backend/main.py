import os
import json
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from agent import create_agent_graph, run_agent
from tools import search_mentors, search_mentorings, USER_CALENDAR_FILE, REALTIME_MENTORINGS_FILE, DATA_DIR

TEAM_INFO_FILE = DATA_DIR / "team_info.json"

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # LangGraph 기반 에이전트 생성
    app.state.agent = create_agent_graph(api_key=os.environ["UPSTAGE_API_KEY"])
    app.state.sessions: dict[str, list[dict]] = {}
    yield


app = FastAPI(title="SoMa Mate API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"
    user_calendar: list[dict] | None = None  # 프론트엔드에서 수집한 실시간 일정표 데이터
    available_mentorings: list[dict] | None = None  # 프론트엔드가 수집한 개설 특강 목록
    team_info: list[dict] | None = None  # 프론트엔드가 수집한 팀매칭 정보


class ChatResponse(BaseModel):
    response: str
    session_id: str


class MentorSearchRequest(BaseModel):
    stacks: list[str] | None = None
    goals: list[str] | None = None
    domains: list[str] | None = None
    available_only: bool = True


class MentoringSearchRequest(BaseModel):
    content_type: str | None = None
    domains: list[str] | None = None
    stacks: list[str] | None = None
    goals: list[str] | None = None
    status: str = "접수중"


@app.get("/health")
async def health():
    return {"status": "ok", "service": "SoMa Mate API"}


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    try:
        # 프론트엔드에서 실시간 스케줄을 보내왔다면 user_calendar.json 갱신
        if req.user_calendar is not None:
            try:
                with open(USER_CALENDAR_FILE, "w", encoding="utf-8") as f:
                    json.dump(req.user_calendar, f, ensure_ascii=False, indent=2)
            except Exception as e:
                print(f"⚠️ 캘린더 캐시 파일 쓰기 실패: {str(e)}")

        # 프론트엔드에서 실시간 특강 목록을 보내왔다면 mentorings_realtime.json 갱신
        if req.available_mentorings is not None:
            try:
                with open(REALTIME_MENTORINGS_FILE, "w", encoding="utf-8") as f:
                    json.dump(req.available_mentorings, f, ensure_ascii=False, indent=2)
            except Exception as e:
                print(f"⚠️ 실시간 특강 캐시 파일 쓰기 실패: {str(e)}")

        # 프론트엔드에서 팀 정보를 보내왔다면 team_info.json 갱신
        if req.team_info is not None:
            try:
                with open(TEAM_INFO_FILE, "w", encoding="utf-8") as f:
                    json.dump(req.team_info, f, ensure_ascii=False, indent=2)
            except Exception as e:
                print(f"⚠️ 팀 정보 캐시 파일 쓰기 실패: {str(e)}")

        sessions = app.state.sessions
        history = sessions.get(req.session_id, [])

        response_text, updated_history = run_agent(
            user_message=req.message,
            conversation_history=history,
            agent_graph=app.state.agent,
        )

        sessions[req.session_id] = updated_history[-20:]

        return ChatResponse(response=response_text, session_id=req.session_id)

    except KeyError:
        raise HTTPException(status_code=500, detail="UPSTAGE_API_KEY가 설정되지 않았습니다.")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AI API 오류: {str(e)}")


@app.delete("/chat/{session_id}")
async def clear_session(session_id: str):
    app.state.sessions.pop(session_id, None)
    return {"message": f"세션 '{session_id}' 초기화 완료"}


@app.post("/mentors/search")
async def mentor_search(req: MentorSearchRequest):
    return search_mentors(
        stacks=req.stacks,
        goals=req.goals,
        domains=req.domains,
        available_only=req.available_only,
    )


@app.post("/mentorings/search")
async def mentoring_search(req: MentoringSearchRequest):
    status = req.status if req.status != "전체" else None
    return search_mentorings(
        content_type=req.content_type,
        domains=req.domains,
        stacks=req.stacks,
        goals=req.goals,
        status=status,
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)

