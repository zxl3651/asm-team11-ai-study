import tempfile
import unittest
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from langchain_core.messages import AIMessage, ToolMessage

from database import SomaDB
from agent import (
    _is_team_meeting_availability_query,
    _target_trainee_info_name_from_query,
    _target_trainee_name_from_query,
    _team_meeting_answer_from_tools,
    _trainee_search_tool_message,
    _team_info_tool_message,
)
from agent_prompts import BASE_SYSTEM_PROMPT, INTENT_TOOL_POLICY
from tools import search_trainees
from workflow_trace import build_workflow_mermaid


class NormalizedScheduleDBTest(unittest.TestCase):
    def make_db(self) -> SomaDB:
        tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(tmp_dir.cleanup)
        return SomaDB(Path(tmp_dir.name) / "soma.db")

    def test_save_mentorings_normalizes_participant_registrations(self):
        db = self.make_db()

        db.save_mentorings([
            {
                "id": "100",
                "type": "lecture",
                "title": "대규모 서비스에도 느리지 않는 DB 만들기",
                "author": "강성욱",
                "dateStr": "2026.06.06 (토)",
                "timeRangeStr": "19:00 ~ 22:00",
                "status": "접수중",
                "location": "온라인(webex)",
                "deliveryMethod": "온라인",
                "participantNames": ["김민수", "강자은", "로그아웃"],
            }
        ])

        stats = db.get_participant_registration_stats()
        self.assertEqual(stats["participant_count"], 2)
        self.assertEqual(stats["registration_link_count"], 2)
        self.assertEqual(stats["by_participant"], {"강자은": 1, "김민수": 1})

        registrations = db.load_participant_registrations("김민수")
        self.assertEqual(len(registrations), 1)
        self.assertEqual(registrations[0]["id"], "100")
        self.assertEqual(registrations[0]["mentoringId"], "100")
        self.assertEqual(registrations[0]["ownerName"], "김민수")
        self.assertEqual(registrations[0]["startAt"], "2026-06-06T19:00:00")
        self.assertEqual(registrations[0]["endAt"], "2026-06-06T22:00:00")

    def test_save_team_info_normalizes_team_members(self):
        db = self.make_db()

        db.save_user_info({
            "name": "김민수",
            "email": "kms@example.com",
            "role": "연수생",
            "techStacks": ["Backend"],
        })
        db.save_team_info([
            {
                "teamName": "고래",
                "leader": "강자은",
                "members": ["강자은", "김민수", "장선우"],
                "mentorName": "한기용",
                "projectName": "미기재",
            }
        ])

        team = db.load_current_user_team()
        self.assertIsNotNone(team)
        self.assertEqual(team["teamName"], "고래")
        self.assertEqual(team["members"], ["강자은", "김민수", "장선우"])
        self.assertEqual(db.load_team_members("고래"), ["강자은", "김민수", "장선우"])

    def test_prompt_contract_matches_prd_schedule_and_recommendation_policy(self):
        self.assertIn("팀 정보` → `계산 기준` → `팀원별 신청 일정 반영` → `가능 후보` → `주간 캘린더", BASE_SYSTEM_PROMPT)
        self.assertIn("특강/멘토링 추천: `제외 기준` → `추천 후보` → `추천 근거`", BASE_SYSTEM_PROMPT)
        self.assertIn("일정 조율의 truth source는 SQLite 정규화 테이블", BASE_SYSTEM_PROMPT)
        self.assertIn("get_team_participant_schedule", INTENT_TOOL_POLICY["schedule_check"])
        self.assertIn("`user_names`에 팀원 전체", INTENT_TOOL_POLICY["schedule_check"])

    def test_workflow_trace_reflects_prd_tool_paths(self):
        messages = [
            AIMessage(
                content="",
                tool_calls=[
                    {"name": "get_team_info", "args": {}, "id": "call_team", "type": "tool_call"},
                    {"name": "get_team_participant_schedule", "args": {}, "id": "call_team_schedule", "type": "tool_call"},
                    {"name": "get_free_slots", "args": {}, "id": "call_slots", "type": "tool_call"},
                    {"name": "search_mentorings", "args": {}, "id": "call_search", "type": "tool_call"},
                    {"name": "vector_search_mentorings", "args": {}, "id": "call_vector", "type": "tool_call"},
                ],
            )
        ]

        mermaid = build_workflow_mermaid(messages, intent="schedule_check")

        self.assertIn("정규화 신청자 연결", mermaid)
        self.assertIn("팀원별 신청 일정", mermaid)
        self.assertIn("공통 빈 시간 계산", mermaid)
        self.assertIn("벡터 후보 탐색", mermaid)
        self.assertIn("리랭킹", mermaid)
        self.assertIn("get_team_participant_schedule -> get_free_slots", mermaid)

    def test_named_trainee_team_meeting_query_uses_team_schedule_path(self):
        query = "김민수 연수생의 팀에 대해서 이번주 특강/멘토링 일정을 제외하고, 2시간 회의 가능 시간을 알려줘."

        self.assertEqual(_target_trainee_name_from_query(query), "김민수")
        self.assertTrue(_is_team_meeting_availability_query(query))

        message = _team_info_tool_message(query)
        self.assertEqual(len(message.tool_calls), 1)
        self.assertEqual(message.tool_calls[0]["name"], "get_team_info")
        self.assertEqual(message.tool_calls[0]["args"], {"trainee_name": "김민수"})

    def test_named_trainee_info_query_uses_search_trainees(self):
        query = "김민수 연수생의 정보를 알려줘."

        self.assertEqual(_target_trainee_info_name_from_query(query), "김민수")

        message = _trainee_search_tool_message(query)
        self.assertEqual(len(message.tool_calls), 1)
        self.assertEqual(message.tool_calls[0]["name"], "search_trainees")
        self.assertEqual(message.tool_calls[0]["args"], {"name": "김민수"})

        result = search_trainees(name="김민수")
        self.assertGreaterEqual(result["total"], 1)
        self.assertEqual(result["trainees"][0]["name"], "김민수")

    def test_named_trainee_team_info_query_uses_get_team_info_not_search_trainees(self):
        query = "김민수 연수생의 팀 정보를 알려줘."

        self.assertEqual(_target_trainee_name_from_query(query), "김민수")
        self.assertIsNone(_target_trainee_info_name_from_query(query))

        message = _team_info_tool_message(query)
        self.assertEqual(len(message.tool_calls), 1)
        self.assertEqual(message.tool_calls[0]["name"], "get_team_info")
        self.assertEqual(message.tool_calls[0]["args"], {"trainee_name": "김민수"})

    def test_team_meeting_answer_summarizes_many_candidates(self):
        windows = [
            {"date": "2026-06-01", "weekday": "월요일", "start": "09:00", "end": "11:00"},
            {"date": "2026-06-01", "weekday": "월요일", "start": "09:30", "end": "11:30"},
            {"date": "2026-06-02", "weekday": "화요일", "start": "09:00", "end": "11:00"},
            {"date": "2026-06-03", "weekday": "수요일", "start": "09:00", "end": "11:00"},
            {"date": "2026-06-04", "weekday": "목요일", "start": "09:00", "end": "11:00"},
            {"date": "2026-06-05", "weekday": "금요일", "start": "09:00", "end": "11:00"},
            {"date": "2026-06-06", "weekday": "토요일", "start": "09:00", "end": "11:00"},
        ]
        messages = [
            ToolMessage(
                content=json.dumps({
                    "team_info": [{
                        "teamName": "부경북",
                        "leader": "한우진",
                        "members": ["한우진", "문성수", "원지섭"],
                    }]
                }, ensure_ascii=False),
                tool_call_id="team",
            ),
            ToolMessage(
                content=json.dumps({
                    "members": ["한우진", "문성수", "원지섭"],
                    "by_member": {
                        "한우진": [],
                        "문성수": [],
                        "원지섭": [],
                    },
                }, ensure_ascii=False),
                tool_call_id="schedule",
            ),
            ToolMessage(
                content=json.dumps({
                    "meeting_windows": windows,
                    "schedule": [{
                        "date": "2026-06-01",
                        "weekday": "월요일",
                        "free_slots": [{"start": "09:00", "end": "20:00"}],
                    }],
                    "visual_schedule_block": "```schedule\nHEADER: 월(06/01)\n09:00: 가능\n```",
                }, ensure_ascii=False),
                tool_call_id="free",
            ),
        ]

        answer = _team_meeting_answer_from_tools(messages)

        self.assertIn("등 총 7개 후보가 있습니다.", answer)
        self.assertIn("전체 가능/불가 구간은 아래 주간 캘린더에서 확인하세요.", answer)
        self.assertIn("넓은 가능 구간", answer)
        self.assertIn("```schedule", answer)
        self.assertNotIn("- 월요일(2026-06-01): 09:30~11:30", answer)


if __name__ == "__main__":
    unittest.main()
