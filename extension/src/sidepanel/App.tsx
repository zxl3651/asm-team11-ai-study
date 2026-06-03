import { useState } from "react";

import { ChatMessage, sendChat } from "../lib/api";

export function App() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSend() {
    const text = input.trim();
    if (!text || loading) return;

    const history = messages;
    const next: ChatMessage[] = [...history, { role: "user", content: text }];
    setMessages(next);
    setInput("");
    setLoading(true);

    try {
      const answer = await sendChat(text, history);
      setMessages([...next, { role: "assistant", content: answer }]);
    } catch (e) {
      setMessages([
        ...next,
        { role: "assistant", content: `오류가 발생했어요: ${String(e)}` },
      ]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100vh", fontFamily: "system-ui" }}>
      <header style={{ padding: "12px 16px", borderBottom: "1px solid #eee", fontWeight: 600 }}>
        🤝 소마 메이트
      </header>

      <main style={{ flex: 1, overflowY: "auto", padding: 16, display: "flex", flexDirection: "column", gap: 10 }}>
        {messages.length === 0 && (
          <p style={{ color: "#888", fontSize: 14 }}>
            스택과 목표를 알려주세요. 예) "Spring 잘하고 창업 경험 있는 멘토 추천해줘"
          </p>
        )}
        {messages.map((m, i) => (
          <div
            key={i}
            style={{
              alignSelf: m.role === "user" ? "flex-end" : "flex-start",
              background: m.role === "user" ? "#2563eb" : "#f1f5f9",
              color: m.role === "user" ? "#fff" : "#111",
              padding: "8px 12px",
              borderRadius: 12,
              maxWidth: "85%",
              whiteSpace: "pre-wrap",
              fontSize: 14,
            }}
          >
            {m.content}
          </div>
        ))}
        {loading && <div style={{ color: "#888", fontSize: 13 }}>생각 중…</div>}
      </main>

      <footer style={{ display: "flex", gap: 8, padding: 12, borderTop: "1px solid #eee" }}>
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleSend()}
          placeholder="질문을 입력하세요"
          style={{ flex: 1, padding: "8px 10px", borderRadius: 8, border: "1px solid #ccc", fontSize: 14 }}
        />
        <button
          onClick={handleSend}
          disabled={loading}
          style={{ padding: "8px 14px", borderRadius: 8, border: "none", background: "#2563eb", color: "#fff", cursor: "pointer" }}
        >
          전송
        </button>
      </footer>
    </div>
  );
}
