"""
노션 공개 갤러리 페이지 크롤러 + LLM 구조화
사용법:
  python crawl_notion.py mentors   -> 멘토 크롤링
  python crawl_notion.py trainees  -> 연수생 크롤링
  python crawl_notion.py all       -> 모두 크롤링
"""

import asyncio
import json
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI
from playwright.async_api import async_playwright

load_dotenv()

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)

MENTOR_URL = "https://swmaestromain.notion.site/AI-SW-32b91e401fdf8026a911df1dc614d5a4"
TRAINEE_URL = "https://asm-busan.notion.site/mentee-list?v=33da01badc2180d0bd03000cd17634ca"

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

MENTOR_PROMPT = """노션 멘토 페이지 텍스트에서 아래 JSON 형식으로 정보를 추출해줘.
- 없는 정보는 빈 문자열("") 또는 빈 배열([])로 채워.
- available은 항상 true로 설정해.
- goals는 "취업", "창업" 중 해당하는 것만 배열에 포함 (기술분야, 멘토 구분에서 추론).
- domains는 기술분야/전문분야 값들을 배열로 (예: ["창업", "AI 기획", "투자유치"]).
- stacks는 주개발언어/기술스택 값들을 배열로 (예: ["Python", "React", "AWS"]).
- mentor_type: "기술" 또는 "비기술" (멘토 구분에서 추출).
- is_busan: 부산팀 전담 가능여부가 "부산가능"이면 true, 아니면 false.
- bio: 자기소개 + 제공 가능한 멘토링 내용을 3-5줄로 요약.

JSON만 출력 (마크다운 없이):
{
  "name": "이름",
  "mentor_type": "기술 또는 비기술",
  "is_busan": false,
  "stacks": [],
  "domains": [],
  "goals": [],
  "bio": "",
  "available": true
}"""

TRAINEE_PROMPT = """노션 연수생 페이지 텍스트에서 아래 JSON 형식으로 정보를 추출해줘.
- 없는 정보는 빈 문자열("") 또는 빈 배열([])로 채워.
- stacks는 기술 스택/관심사 값들을 배열로 (예: ["Python", "FastAPI", "AWS"]).
- roles는 역할 배열 (예: ["백엔드", "AI"]).
- bio: 자기소개를 2-3줄로 요약. 없으면 빈 문자열.
- team_status: 팀원 모집 중이면 "팀없음", 팀 있으면 "팀있음" (0명이면 팀없음).

JSON만 출력 (마크다운 없이):
{
  "name": "이름",
  "roles": [],
  "stacks": [],
  "bio": "",
  "team_status": "팀없음"
}"""


def get_client() -> OpenAI:
    return OpenAI(
        api_key=os.environ["UPSTAGE_API_KEY"],
        base_url="https://api.upstage.ai/v1",
    )


async def get_page_text(url: str, wait_ms: int = 7000) -> str:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(user_agent=UA)
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(wait_ms)
            return await page.inner_text("body")
        except Exception as e:
            return f"ERROR: {e}"
        finally:
            await browser.close()


async def get_individual_links(parent_url: str) -> list[dict]:
    """갤러리 부모 페이지에서 개별 페이지 링크 추출."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(user_agent=UA)
        try:
            await page.goto(parent_url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(6000)

            raw_links = await page.evaluate("""
                () => Array.from(document.querySelectorAll('a')).map(a => ({
                    href: a.href,
                    text: a.innerText.trim()
                }))
            """)

            parent_base = parent_url.split("?")[0]
            seen = set()
            result = []

            for link in raw_links:
                href = link["href"]
                text = link["text"]

                if not text or len(text) < 2:
                    continue
                # notion 도메인 포함 링크만
                if "notion.site" not in href and "notion.so" not in href:
                    continue
                # 부모 URL(리스트/갤러리뷰) 제외
                href_base = href.split("?")[0]
                if href_base == parent_base:
                    continue
                # 앵커 링크 제외
                if "#main" in href or "Skip to" in text:
                    continue
                # 갤러리 뷰(v=...) 링크 제외 (pvs 없는 경우)
                if "?v=" in href and "pvs" not in href:
                    continue
                # Notion 마케팅 링크 제외
                if "notion.com" in href or "notion.so/product" in href:
                    continue

                if href not in seen:
                    seen.add(href)
                    result.append({"href": href, "text": text})

            return result
        finally:
            await browser.close()


def parse_with_llm(client: OpenAI, raw_text: str, prompt: str) -> dict | None:
    full_prompt = f"{prompt}\n\n페이지 텍스트:\n---\n{raw_text[:4000]}\n---"
    response = client.chat.completions.create(
        model="solar-pro3",
        messages=[{"role": "user", "content": full_prompt}],
        temperature=0,
    )
    raw = response.choices[0].message.content.strip()

    match = re.search(r"```(?:json)?\s*([\s\S]+?)```", raw)
    if match:
        raw = match.group(1).strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        print(f"    ⚠️  JSON 파싱 실패: {raw[:100]}")
        return None


def load_progress(path: Path) -> list:
    if path.exists():
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return []


def save_progress(path: Path, data: list):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


async def crawl(data_type: str):
    client = get_client()
    url = MENTOR_URL if data_type == "mentors" else TRAINEE_URL
    prompt = MENTOR_PROMPT if data_type == "mentors" else TRAINEE_PROMPT
    id_prefix = "M" if data_type == "mentors" else "T"
    progress_file = DATA_DIR / f"{data_type}_progress.json"
    out_file = DATA_DIR / f"{data_type}.json"
    label = "멘토" if data_type == "mentors" else "연수생"

    print(f"🔍 {label} 목록 페이지 분석 중...")
    links = await get_individual_links(url)
    print(f"📄 개별 {label} 페이지 발견: {len(links)}개")

    results = load_progress(progress_file)
    done_hrefs = {r["profile_url"] for r in results}
    pending = [l for l in links if l["href"] not in done_hrefs]
    print(f"✅ 이미 완료: {len(results)}개 | 남은 것: {len(pending)}개\n")

    for i, link in enumerate(pending, start=len(results) + 1):
        name_hint = link["text"].split("\n")[0][:30]
        print(f"  [{i}/{len(links)}] {name_hint} 크롤링...")

        text = await get_page_text(link["href"])
        if text.startswith("ERROR") or len(text) < 50:
            print(f"    ❌ 페이지 로드 실패")
            continue

        parsed = parse_with_llm(client, text, prompt)
        if not parsed:
            continue

        parsed["id"] = f"{id_prefix}{i:03d}"
        parsed["profile_url"] = link["href"]
        results.append(parsed)
        save_progress(progress_file, results)

        if data_type == "mentors":
            print(f"    ✅ {parsed.get('name', '?')} | 스택: {parsed.get('stacks', [])[:3]} | 분야: {parsed.get('domains', [])[:3]}")
        else:
            print(f"    ✅ {parsed.get('name', '?')} | 역할: {parsed.get('roles', [])}")

        await asyncio.sleep(0.5)

    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n🎉 {label} 저장 완료: {out_file} ({len(results)}명)")
    progress_file.unlink(missing_ok=True)


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ("mentors", "trainees", "all"):
        print("사용법: python crawl_notion.py [mentors|trainees|all]")
        sys.exit(1)

    mode = sys.argv[1]
    if mode in ("mentors", "all"):
        asyncio.run(crawl("mentors"))
    if mode in ("trainees", "all"):
        asyncio.run(crawl("trainees"))


if __name__ == "__main__":
    main()
