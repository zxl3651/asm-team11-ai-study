"""세션 컨텍스트 캐시.

특강·멘토링·팀매칭 같은 '로그인 필요' 데이터는 서버가 직접 못 긁는다.
확장(콘텐츠 스크립트)이 사용자 세션으로 파싱해 POST /api/context 로 보내주면
여기 메모리에 캐시해 두고, 도구(search_sessions / search_teams 등)가 읽는다.

⚠️ MVP 로컬용 단일 스냅샷 캐시(전역). 다중 사용자 운영 시엔 신원별 키 필요.
"""

_store: dict[str, list[dict]] = {"sessions": [], "teams": []}


def set_sessions(items: list[dict]) -> None:
    _store["sessions"] = items or []


def get_sessions() -> list[dict]:
    return _store["sessions"]


def set_teams(items: list[dict]) -> None:
    _store["teams"] = items or []


def get_teams() -> list[dict]:
    return _store["teams"]
