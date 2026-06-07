// 백엔드(에이전트 서버) 호출 래퍼. minsu 방식(SSE 스트리밍)으로 동작한다.
const BASE_URL = "http://localhost:8000";

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  workflowMermaid?: string;
  processingSteps?: string[];
}

export interface ChatStreamHandlers {
  onStatus?: (message: string) => void; // 처리 과정 단계(실시간)
  onComplete: (payload: { response: string; workflowMermaid?: string }) => void;
  onError?: (message: string) => void;
}

/**
 * /chat SSE 스트림을 소비한다.
 *  - type:"status"   → 처리 단계 메시지 (onStatus)
 *  - type:"complete" → 최종 답변 + 워크플로우 mermaid (onComplete)
 *  - type:"error"    → 오류 (onError)
 */
export async function streamChat(
  message: string,
  sessionId: string,
  handlers: ChatStreamHandlers
): Promise<void> {
  const res = await fetch(`${BASE_URL}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, session_id: sessionId }),
  });
  if (!res.ok || !res.body) {
    handlers.onError?.(`서버 오류: ${res.status}`);
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  // eslint-disable-next-line no-constant-condition
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";
    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed.startsWith("data: ")) continue;
      const json = trimmed.slice(6);
      try {
        const data = JSON.parse(json);
        if (data.type === "status") {
          handlers.onStatus?.(data.message);
        } else if (data.type === "complete") {
          handlers.onComplete({
            response: data.response,
            workflowMermaid: data.workflow_mermaid || undefined,
          });
        } else if (data.type === "error") {
          handlers.onError?.(data.message || "AI 처리 중 오류가 발생했습니다.");
        }
      } catch {
        /* 부분 청크 무시 */
      }
    }
  }
}
