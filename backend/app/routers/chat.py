from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.agent.loop import run_agent
from app import context_store

router = APIRouter(prefix="/api", tags=["chat"])


class ContextRequest(BaseModel):
    # 확장이 사용자 세션으로 파싱해 보낸 '로그인 필요' 데이터
    sessions: list[dict] | None = None
    teams: list[dict] | None = None


@router.post("/context")
def update_context(req: ContextRequest) -> dict:
    """확장이 보낸 접수중 특강/멘토링·팀매칭 스냅샷을 캐시한다."""
    if req.sessions is not None:
        context_store.set_sessions(req.sessions)
    if req.teams is not None:
        context_store.set_teams(req.teams)
    return {
        "ok": True,
        "sessions": len(context_store.get_sessions()),
        "teams": len(context_store.get_teams()),
    }


class Message(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str
    history: list[Message] = []
    soma_user: str = ""  # 소마 로그인으로 확인된 신원 (예: "17기 연수생")


class ChatResponse(BaseModel):
    answer: str


@router.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    # [보류] 로그인 게이팅 — 인증 기준 재설계 전까지 비활성화.
    # 정식 인증(백엔드 검증 + JWT)으로 다시 켤 예정. 그때까지 누구나 호출 가능.
    # if "연수생" not in req.soma_user:
    #     raise HTTPException(status_code=401, detail="소마 연수생 로그인이 필요합니다.")

    history = [m.model_dump() for m in req.history]
    answer = run_agent(req.message, history)
    return ChatResponse(answer=answer)
