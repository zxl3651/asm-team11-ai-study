"""Upstage Solar 클라이언트 (OpenAI 호환).

Upstage는 OpenAI SDK를 그대로 쓸 수 있다. base_url 과 api_key 만 바꿔주면 된다.
"""

from openai import OpenAI

from app.config import UPSTAGE_API_KEY, UPSTAGE_BASE_URL, UPSTAGE_MODEL

client = OpenAI(
    api_key=UPSTAGE_API_KEY,
    base_url=UPSTAGE_BASE_URL,
)

MODEL = UPSTAGE_MODEL
