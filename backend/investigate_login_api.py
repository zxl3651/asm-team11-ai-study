import asyncio
import json
from pathlib import Path

from playwright.async_api import async_playwright


CAPTURE_FILE = Path(__file__).parent / "login_capture.json"


async def capture_login_flow(url: str):
    events = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()

        page.on("request", lambda req: events.append({
            "type": "request",
            "method": req.method,
            "url": req.url,
            "headers": dict(req.headers),
            "postData": req.post_data or None,
        }))

        page.on("response", lambda res: events.append({
            "type": "response",
            "status": res.status,
            "url": res.url,
            "headers": dict(res.headers),
        }))

        print("브라우저가 열립니다. 로그인 페이지로 이동합니다...")
        await page.goto(url)
        print("로그인 후, 완료되면 터미널에서 Enter를 눌러 캡처를 종료하세요.")
        input()

        await browser.close()

    with open(CAPTURE_FILE, "w", encoding="utf-8") as f:
        json.dump(events, f, ensure_ascii=False, indent=2)

    print(f"캡처 저장 완료: {CAPTURE_FILE}")


def main():
    # 접근하려는 페이지 (회원 전용 목록)
    url = "https://swmaestro.ai/busan/sw/mypage/mentoLec/list.do?menuNo=200046"
    asyncio.run(capture_login_flow(url))


if __name__ == "__main__":
    main()
