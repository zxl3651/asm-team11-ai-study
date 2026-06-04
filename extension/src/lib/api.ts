// 백엔드(문지기 서버) 호출 래퍼.
const BASE_URL = "http://localhost:8000";

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export async function sendChat(
  message: string,
  history: ChatMessage[],
  somaUser: string
): Promise<string> {
  const res = await fetch(`${BASE_URL}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    // 소마 로그인으로 확인된 신원(soma_user)을 본문에 함께 보냄. 백엔드 '문지기'가 검사.
    body: JSON.stringify({ message, history, soma_user: somaUser }),
  });
  if (!res.ok) throw new Error(`서버 오류: ${res.status}`);
  const data = (await res.json()) as { answer: string };
  return data.answer;
}

// 확장이 세션으로 파싱한 '로그인 필요' 데이터(특강/멘토링·팀매칭)를 백엔드 캐시에 올린다.
export async function postContext(payload: {
  sessions?: unknown[];
  teams?: unknown[];
}): Promise<void> {
  await fetch(`${BASE_URL}/api/context`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}
