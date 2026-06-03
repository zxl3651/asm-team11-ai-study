from fastapi import APIRouter
from pydantic import BaseModel

from app.agent.loop import run_agent

router = APIRouter(prefix="/api", tags=["chat"])


class Message(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str
    history: list[Message] = []


class ChatResponse(BaseModel):
    answer: str


@router.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    history = [m.model_dump() for m in req.history]
    answer = run_agent(req.message, history)
    return ChatResponse(answer=answer)
