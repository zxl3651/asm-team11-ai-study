"""소마 부산 공개 Notion 연수생(멘티) 리스트 → backend/app/data/trainees.json 크롤러.

공개 Notion 페이지(asm-busan.notion.site/mentee-list)에 임베드된 연수생
데이터베이스를 Notion 비공식 공개 API(queryCollection)로 인증 없이 긁어와
백엔드가 읽는 trainees.json 형태로 저장한다.

⚠️ 개인정보 보호: 이름·기술스택·이메일·팀상태만 수집한다.
   전화번호 / 카카오톡 / MBTI / 거주지 등은 **수집하지 않는다.**

사용법:
    cd backend && python scripts/crawl_notion_mentees.py
"""

import json
import re
from pathlib import Path

import requests

# ── 대상 Notion DB 좌표 (브라우저 네트워크/페이지 데이터로 확인) ──
COLLECTION_ID = "33da01ba-dc21-80aa-ae52-000be696d518"
VIEW_ID = "33da01ba-dc21-80d0-bd03-000cd17634ca"
SPACE_ID = "a0da01ba-dc21-8135-b752-0003feda4ae6"
QUERY_URL = "https://asm-busan.notion.site/api/v3/queryCollection?src=initial_load"

# ── 속성 ID → 의미 매핑 (스키마 조회로 확인) ──
PROP_STACK = "O`di"  # 기술 스택 (콤마구분)
PROP_EMAIL = "Qg{|"  # Email
# 수집 제외(개인정보): 전화번호 "jX_>", 카카오톡 "<voX", MBTI "bn_S", 거주지 "KIis"
# 팀 구성여부("찾은 팀원" qK}w)는 오래된 정보라 폐기 → 팀매칭 페이지(team.do)가 정확.

OUT_PATH = Path(__file__).resolve().parent.parent / "app" / "data" / "trainees.json"


def fetch_rows() -> list[dict]:
    """연수생 DB 의 모든 행(page 블록 value)을 가져온다."""
    body = {
        "source": {"type": "collection", "id": COLLECTION_ID, "spaceId": SPACE_ID},
        "collectionView": {"id": VIEW_ID, "spaceId": SPACE_ID},
        "loader": {
            "type": "reducer",
            "reducers": {"collection_group_results": {"type": "results", "limit": 500}},
            "searchQuery": "",
            "userTimeZone": "Asia/Seoul",
        },
    }
    res = requests.post(
        QUERY_URL,
        json=body,
        headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"},
        timeout=30,
    )
    res.raise_for_status()
    blocks = res.json().get("recordMap", {}).get("block", {})
    rows = []
    for b in blocks.values():
        # Notion 응답은 value.value 로 이중 중첩돼 있다.
        val = b.get("value", {}).get("value", {})
        if val.get("type") == "page":
            rows.append(val)
    return rows


def _text(row: dict, prop_id: str) -> str:
    """Notion 속성(중첩 배열)을 평탄한 문자열로."""
    segs = row.get("properties", {}).get(prop_id, [])
    return " ".join(seg[0] for seg in segs if seg).strip()


def _split(value: str) -> list[str]:
    """'A,B / C' → ['A','B','C'] (콤마/슬래시 분해, 공백제거, 중복제거)."""
    parts = re.split(r"[,/]", value)
    seen, out = set(), []
    for p in (x.strip() for x in parts):
        if p and p not in seen:
            seen.add(p)
            out.append(p)
    return out


def _clean_name(raw: str) -> str:
    """이모지·장식문자를 떼고 이름만 남긴다."""
    name = re.sub(r"[^\w가-힣 ]", " ", raw)
    return re.sub(r"\s+", " ", name).strip()


def build_trainee(row: dict) -> dict:
    return {
        "id": "t_" + row["id"][:8],
        "name": _clean_name(_text(row, "title")),
        "stacks": _split(_text(row, PROP_STACK)),
        "email": _text(row, PROP_EMAIL),  # 수집하는 유일한 개인정보
    }


def main() -> None:
    rows = fetch_rows()
    trainees = []
    for r in rows:
        if not _text(r, "title").strip():  # 빈/템플릿 행 skip
            continue
        t = build_trainee(r)
        if t["name"]:
            trainees.append(t)

    OUT_PATH.write_text(
        json.dumps(trainees, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"저장 완료: {len(trainees)}명 → {OUT_PATH}")


if __name__ == "__main__":
    main()
