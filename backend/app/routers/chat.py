from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.agent.loop import run_agent

router = APIRouter(prefix="/api", tags=["chat"])


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
    # 문지기: 소마 로그인으로 확인된 신원이 없으면 거절한다.
    # (확장 content script 가 swmaestro.ai 로그인 확인 후 'NN기 연수생'을 보낸다)
    if "연수생" not in req.soma_user:
        raise HTTPException(status_code=401, detail="소마 연수생 로그인이 필요합니다.")

    history = [m.model_dump() for m in req.history]
    answer = run_agent(req.message, history)
    return ChatResponse(answer=answer)
