import os
import json
import asyncio
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
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
    user_info: dict | None = None  # 프론트엔드가 수집한 기본 정보 (이름, 기술스택 등)


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


@app.post("/chat")
async def chat(req: ChatRequest):
    queue = asyncio.Queue()
    loop = asyncio.get_running_loop()

    def sync_status_callback(msg: str):
        # 비동기 이벤트 루프를 사용하여 다른 스레드에서 생성된 상태 메시지를 큐에 추가
        loop.call_soon_threadsafe(queue.put_nowait, {"type": "status", "message": msg})

    async def event_generator():
        # contextvars에 콜백 등록
        from tools import status_callback_var
        from database import db
        token = status_callback_var.set(sync_status_callback)

        try:
            # 1. 캘린더 데이터 동기화
            if req.user_calendar is not None:
                sync_status_callback(f"📅 Sync: 개인 일정표 {len(req.user_calendar)}건 저장 중...")
                db.save_user_calendar(req.user_calendar)
                sync_status_callback("✅ Sync: 개인 일정표 저장 완료")

            # 2. 특강/멘토링 및 RAG 벡터 인덱싱
            if req.available_mentorings is not None:
                sync_status_callback(f"📚 Sync: 특강/멘토링 {len(req.available_mentorings)}건 DB 저장 중...")
                db.save_mentorings(req.available_mentorings)
                sync_status_callback("🧬 Sync: 특강/멘토링 벡터 인덱싱 중...")
                from vector_store import sync_mentorings_to_vector_db
                sync_mentorings_to_vector_db(db.load_mentorings())
                sync_status_callback("✅ Sync: 특강/멘토링 저장 및 벡터 인덱싱 완료")

            # 3. 팀 매칭 정보 동기화
            if req.team_info is not None:
                sync_status_callback(f"👥 Sync: 팀 매칭 정보 {len(req.team_info)}건 저장 중...")
                db.save_team_info(req.team_info)
                sync_status_callback("✅ Sync: 팀 매칭 정보 저장 완료")

            # 4. 사용자 기본 정보 동기화
            if req.user_info is not None:
                sync_status_callback("🙋 Sync: 사용자 기본 정보 저장 중...")
                db.save_user_info(req.user_info)
                sync_status_callback("✅ Sync: 사용자 기본 정보 저장 완료")

            # 에이전트 실행 코드를 별도 스레드에서 구동 (LangChain 블로킹 방지)
            async def run_agent_task():
                # run_in_executor를 통해 동기 함수를 비동기 컨텍스트에서 안전하게 실행
                loop = asyncio.get_running_loop()
                return await loop.run_in_executor(
                    None,
                    run_agent,
                    req.message,
                    req.session_id,
                    app.state.agent,
                    sync_status_callback
                )

            # 에이전트 구동 태스크 생성
            agent_future = asyncio.create_task(run_agent_task())

            # 에이전트가 처리하는 동안 큐의 진행 상태 메시지를 계속 전송
            while not agent_future.done():
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=0.1)
                    yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"
                except asyncio.TimeoutError:
                    continue

            # 에이전트 결과 획득 및 최종 완료 이벤트 전송
            response_text, _, workflow_mermaid = await agent_future
            final_data = {
                "type": "complete",
                "response": response_text,
                "workflow_mermaid": workflow_mermaid,
            }
            yield f"data: {json.dumps(final_data, ensure_ascii=False)}\n\n"

        except Exception as e:
            err_data = {"type": "error", "message": f"AI 처리 중 오류가 발생했습니다: {str(e)}"}
            yield f"data: {json.dumps(err_data, ensure_ascii=False)}\n\n"
        finally:
            status_callback_var.reset(token)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


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
