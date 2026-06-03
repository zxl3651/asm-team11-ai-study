"""소마 공개 Notion 멘토 DB → backend/app/data/mentors.json 크롤러.

공개 Notion 페이지(swmaestromain.notion.site/AI-SW-...)에 임베드된 멘토
데이터베이스를 Notion 비공식 공개 API(queryCollection)로 인증 없이 긁어와
백엔드가 읽는 mentors.json 형태로 저장한다.

사용법:
    cd backend && python scripts/crawl_notion_mentors.py
"""

import json
import re
from pathlib import Path

import requests

# ── 대상 Notion DB 좌표 (탐색으로 확인) ──
COLLECTION_ID = "83991e40-1fdf-82a0-bdee-077e4547668a"
VIEW_ID = "ffb91e40-1fdf-8289-a3da-088ea5cf25e5"
QUERY_URL = "https://www.notion.so/api/v3/queryCollection?src=initial_load"

# ── 속성 ID → 의미 매핑 (행 샘플로 추론, 해당 DB 내 안정적) ──
PROP_TYPE = "EK^G"  # 멘토 유형 (기술멘토/비기술멘토/국내/해외, 다중)
PROP_STACK = "YGYH"  # 기술 스택 (콤마구분)
PROP_FIELD = "`RTz"  # 전문/관심 분야 (콤마구분)
PROP_FIELD2 = "G_]r"  # 멘토링 가능 분야 (보조)
PROP_BIO_A = "STkj"  # 취미/소개
PROP_BIO_B = "BoSk"  # 취미/소개
PROP_KAKAO = "x\\mM"  # 카카오 오픈채팅 링크
PROP_GITHUB = "IeFR"  # github

OUT_PATH = Path(__file__).resolve().parent.parent / "app" / "data" / "mentors.json"


def fetch_rows() -> list[dict]:
    """멘토 DB 의 모든 행(page 블록 value)을 가져온다."""
    body = {
        "collection": {"id": COLLECTION_ID},
        "collectionView": {"id": VIEW_ID},
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
    """이모지·장식문자를 떼고 '홍길동 멘토' 형태만 남긴다."""
    # 한글/영문/숫자/공백만 유지
    name = re.sub(r"[^\w가-힣 ]", " ", raw)
    name = re.sub(r"\s+", " ", name).strip()
    return name


def build_mentor(row: dict) -> dict:
    fields = _split(_text(row, PROP_FIELD)) + _split(_text(row, PROP_FIELD2))
    fields = list(dict.fromkeys(fields))  # dedup, 순서유지
    types = _split(_text(row, PROP_TYPE))
    bio = _text(row, PROP_BIO_A) or _text(row, PROP_BIO_B)
    kakao = _text(row, PROP_KAKAO)
    github = _text(row, PROP_GITHUB)

    return {
        "id": "m_" + row["id"][:8],
        "name": _clean_name(_text(row, "title")),
        "stacks": _split(_text(row, PROP_STACK)),
        "fields": fields,
        "types": types,
        "startup_experience": any("창업" in t for t in types + fields),
        "bio": bio,
        "github": github,
        "apply_url": kakao or github,  # 컨택 수단 (카카오 우선)
    }


def main() -> None:
    rows = fetch_rows()
    mentors = []
    for r in rows:
        if not _text(r, "title").strip():  # 빈/템플릿 행 skip
            continue
        m = build_mentor(r)
        if m["name"]:
            mentors.append(m)

    OUT_PATH.write_text(
        json.dumps(mentors, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"저장 완료: {len(mentors)}명 → {OUT_PATH}")


if __name__ == "__main__":
    main()
