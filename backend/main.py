import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from agent import create_client, run_agent
from tools import search_mentors, search_experts, search_trainees

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.client = create_client(api_key=os.environ["UPSTAGE_API_KEY"])
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


class ChatResponse(BaseModel):
    response: str
    session_id: str


class MentorSearchRequest(BaseModel):
    stacks: list[str] | None = None
    goals: list[str] | None = None
    domains: list[str] | None = None
    available_only: bool = True


class ExpertSearchRequest(BaseModel):
    stacks: list[str] | None = None
    domains: list[str] | None = None
    keyword: str | None = None


class TraineeSearchRequest(BaseModel):
    roles: list[str] | None = None
    stacks: list[str] | None = None
    team_status: str | None = None


@app.get("/health")
async def health():
    return {"status": "ok", "service": "SoMa Mate API"}


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    try:
        sessions = app.state.sessions
        history = sessions.get(req.session_id, [])

        response_text, updated_history = run_agent(
            user_message=req.message,
            conversation_history=history,
            client=app.state.client,
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


@app.post("/experts/search")
async def expert_search(req: ExpertSearchRequest):
    return search_experts(
        stacks=req.stacks,
        domains=req.domains,
        keyword=req.keyword,
    )


@app.post("/mentors/search")
async def mentor_search(req: MentorSearchRequest):
    return search_mentors(
        stacks=req.stacks,
        goals=req.goals,
        domains=req.domains,
        available_only=req.available_only,
    )


@app.post("/trainees/search")
async def trainee_search(req: TraineeSearchRequest):
    return search_trainees(
        roles=req.roles,
        stacks=req.stacks,
        team_status=req.team_status,
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
