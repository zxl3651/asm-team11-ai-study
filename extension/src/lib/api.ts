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
