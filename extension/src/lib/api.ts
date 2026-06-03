// 백엔드(문지기 서버) 호출 래퍼.
const BASE_URL = "http://localhost:8000";

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export async function sendChat(
  message: string,
  history: ChatMessage[]
): Promise<string> {
  const res = await fetch(`${BASE_URL}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, history }),
  });
  if (!res.ok) throw new Error(`서버 오류: ${res.status}`);
  const data = (await res.json()) as { answer: string };
  return data.answer;
}
