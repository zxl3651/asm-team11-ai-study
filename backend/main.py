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
from tools import search_mentors, search_mentorings

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


class PortalSyncRequest(BaseModel):
    user_calendar: list[dict] | None = None
    available_mentorings: list[dict] | None = None
    team_info: list[dict] | None = None
    user_info: dict | None = None


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
    status: str = "전체"


@app.get("/health")
async def health():
    return {"status": "ok", "service": "SoMa Mate API"}


@app.get("/sync/status")
async def sync_status():
    from database import db

    return {
        "status": "ok",
        "readiness": db.get_data_readiness(),
        "sync_run": db.get_sync_run_stats(),
        "mentorings": db.get_mentoring_stats(),
        "participant_registrations": db.get_participant_registration_stats(),
        "user_calendar": db.get_user_calendar_stats(),
    }


def _sync_portal_data(req: PortalSyncRequest | ChatRequest, status_callback=None) -> dict:
    from database import db

    def report(msg: str):
        if status_callback:
            status_callback(msg)

    changed_sections: list[str] = []
    counts: dict[str, int] = {}
    details: dict[str, dict] = {}

    if req.user_calendar is not None:
        counts["user_calendar"] = len(req.user_calendar)
        calendar_owner = (req.user_info or {}).get("name") if req.user_info else None
        if not calendar_owner:
            current_user_info = db.load_user_info()
            calendar_owner = current_user_info.get("name") if current_user_info else None
        report(f"Sync: 레거시 일정 데이터 {len(req.user_calendar)}건 저장 중...")
        db.save_user_calendar(req.user_calendar, owner_name=calendar_owner)
        details["user_calendar"] = db.get_user_calendar_stats()
        changed_sections.append("user_calendar")
        report("Sync: 레거시 일정 데이터 저장 완료")

    if req.available_mentorings is not None:
        counts["available_mentorings"] = len(req.available_mentorings)
        report(f"Sync: 특강/멘토링 {len(req.available_mentorings)}건 DB 저장 중...")
        db.save_mentorings(req.available_mentorings)
        details["available_mentorings"] = db.get_mentoring_stats()
        details["participant_registrations"] = db.get_participant_registration_stats()
        details["sync_run"] = db.get_sync_run_stats()
        report("Sync: 특강/멘토링 벡터 인덱싱 중...")
        try:
            from vector_store import sync_mentorings_to_vector_db
            details["vector_store"] = sync_mentorings_to_vector_db(db.load_mentorings())
            db.update_vector_document_count(int(details["vector_store"].get("collection_count", 0) or 0))
            details["sync_run"] = db.get_sync_run_stats()
        except Exception as vector_err:
            details["vector_store"] = {
                "status": "error",
                "message": str(vector_err),
            }
            report(f"Sync: 벡터 인덱싱 실패 - {vector_err}")
        changed_sections.append("available_mentorings")
        report("Sync: 특강/멘토링 저장 및 벡터 인덱싱 완료")

    if req.team_info is not None:
        counts["team_info"] = len(req.team_info)
        report(f"Sync: 팀 매칭 정보 {len(req.team_info)}건 저장 중...")
        db.save_team_info(req.team_info)
        changed_sections.append("team_info")
        report("Sync: 팀 매칭 정보 저장 완료")

    if req.user_info is not None:
        counts["user_info"] = 1 if req.user_info else 0
        report("Sync: 사용자 기본 정보 저장 중...")
        db.save_user_info(req.user_info)
        changed_sections.append("user_info")
        report("Sync: 사용자 기본 정보 저장 완료")

    return {
        "status": "ok",
        "changed_sections": changed_sections,
        "counts": counts,
        "details": details,
    }


@app.post("/sync")
async def sync_portal_data(req: PortalSyncRequest):
    return await asyncio.to_thread(_sync_portal_data, req)


@app.delete("/sync")
async def clear_synced_portal_data():
    from database import db

    def clear_all():
        db.clear_all_portal_data()
        from vector_store import sync_mentorings_to_vector_db
        sync_mentorings_to_vector_db([])

    await asyncio.to_thread(clear_all)
    return {"status": "ok", "message": "동기화된 포털 데이터를 모두 삭제했습니다."}


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
            if any(field is not None for field in (req.user_calendar, req.available_mentorings, req.team_info, req.user_info)):
                _sync_portal_data(req, sync_status_callback)

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
