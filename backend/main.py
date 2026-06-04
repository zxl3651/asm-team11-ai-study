import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from agent import create_client, run_agent
from tools import search_mentors

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
    cards: list[dict] = []
    action: dict | None = None


class ChatCallbackRequest(BaseModel):
    session_id: str
    tool_call_id: str
    html_content: str





@app.get("/health")
async def health():
    return {"status": "ok", "service": "SoMa Mate API"}


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    try:
        sessions = app.state.sessions
        history = sessions.get(req.session_id, [])

        response_text, updated_history, cards, action = run_agent(
            user_message=req.message,
            conversation_history=history,
            client=app.state.client,
        )

        sessions[req.session_id] = updated_history[-20:]

        return ChatResponse(response=response_text, session_id=req.session_id, cards=cards, action=action)

    except KeyError:
        raise HTTPException(status_code=500, detail="UPSTAGE_API_KEY가 설정되지 않았습니다.")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AI API 오류: {str(e)}")


@app.post("/chat/callback", response_model=ChatResponse)
async def chat_callback(req: ChatCallbackRequest):
    try:
        sessions = app.state.sessions
        history = sessions.get(req.session_id, [])

        response_text, updated_history, cards, action = run_agent(
            user_message=None,
            conversation_history=history,
            client=app.state.client,
            tool_result={
                "tool_call_id": req.tool_call_id,
                "content": req.html_content[:30000] # HTML length limit
            }
        )

        sessions[req.session_id] = updated_history[-20:]

        return ChatResponse(response=response_text, session_id=req.session_id, cards=cards, action=action)

    except KeyError:
        raise HTTPException(status_code=500, detail="UPSTAGE_API_KEY가 설정되지 않았습니다.")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AI API 오류: {str(e)}")


@app.delete("/chat/{session_id}")
async def clear_session(session_id: str):
    app.state.sessions.pop(session_id, None)
    return {"message": f"세션 '{session_id}' 초기화 완료"}



if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
