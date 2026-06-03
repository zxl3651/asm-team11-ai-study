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
        from database import db
        
        # 프론트엔드에서 실시간 스케줄을 보내왔다면 SQLite DB 갱신
        if req.user_calendar is not None:
            try:
                db.save_user_calendar(req.user_calendar)
            except Exception as e:
                print(f"⚠️ 캘린더 DB 저장 실패: {str(e)}")

        # 프론트엔드에서 실시간 특강 목록을 보내왔다면 SQLite DB 및 ChromaDB 갱신
        if req.available_mentorings is not None:
            try:
                db.save_mentorings(req.available_mentorings)
                # ChromaDB 벡터 스토어 동기화
                from vector_store import sync_mentorings_to_vector_db
                sync_mentorings_to_vector_db(req.available_mentorings)
            except Exception as e:
                print(f"⚠️ 실시간 특강 DB/벡터 저장 실패: {str(e)}")

        # 프론트엔드에서 팀 정보를 보내왔다면 SQLite DB 갱신
        if req.team_info is not None:
            try:
                db.save_team_info(req.team_info)
            except Exception as e:
                print(f"⚠️ 팀 정보 DB 저장 실패: {str(e)}")

        response_text, updated_history = run_agent(
            user_message=req.message,
            session_id=req.session_id,
            agent_graph=app.state.agent,
        )

        return ChatResponse(response=response_text, session_id=req.session_id)

    except KeyError:
        raise HTTPException(status_code=500, detail="UPSTAGE_API_KEY가 설정되지 않았습니다.")
    except Exception as e:
        raise HTTPException(status_code=520, detail=f"AI API 오류: {str(e)}")


@app.delete("/chat/{session_id}")
async def clear_session(session_id: str):
    from database import db
    db.clear_chat_history(session_id)
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

