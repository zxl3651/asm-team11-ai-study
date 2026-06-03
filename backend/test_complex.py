import os
import json
from dotenv import load_dotenv

load_dotenv()

from agent import create_agent_graph, run_agent
from database import db

def print_status(msg):
    print(f"[SSE Status] {msg}")

if __name__ == "__main__":
    api_key = os.environ.get("UPSTAGE_API_KEY")
    if not api_key:
        print("ERROR: UPSTAGE_API_KEY not found in environment.")
        exit(1)
        
    graph = create_agent_graph(api_key)
    
    query = "우리 팀의 정기 회의 시간(평일 10:00 ~ 12:00)을 내 일정에서 제외한 뒤, 이번 주 나머지 빈 시간대 중에서 내 수강 이력을 바탕으로 관심사에 부합하는 신청 가능한 특강/멘토링을 골라줘."
    session_id = "test_complex_recommendation_session"
    
    db.clear_chat_history(session_id)
    
    print(f"\n--- Running Agent for query: '{query}' ---")
    try:
        response, history, mermaid = run_agent(
            user_message=query,
            session_id=session_id,
            agent_graph=graph,
            on_status_update=print_status
        )
        print("\n--- Final Response ---")
        print(response)
        
        print("\n--- Message History and Tool Calls ---")
        for h in history:
            role = h.get("role")
            content = h.get("content", "")
            tc = h.get("tool_calls", "")
            print(f"[{role}] {content[:100]}... (tool_calls: {tc})")
            
    except Exception as e:
        print("Exception occurred:")
        import traceback
        traceback.print_exc()
