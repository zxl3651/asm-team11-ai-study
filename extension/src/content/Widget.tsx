import { useEffect, useRef, useState } from "react";

import { ChatMessage, sendChat } from "../lib/api";
import { AuthResult, checkAuth } from "./auth";

export function Widget() {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [auth, setAuth] = useState<AuthResult | null>(null); // null = 확인 중
  const rootRef = useRef<HTMLDivElement>(null);
  const bodyRef = useRef<HTMLDivElement>(null);

  // 패널을 처음 열 때 로그인 여부 확인 (한 번만)
  useEffect(() => {
    if (open && auth === null) {
      checkAuth().then(setAuth);
    }
  }, [open, auth]);

  // 바깥 클릭 / Esc 로 닫기
  useEffect(() => {
    if (!open) return;
    function onDown(e: MouseEvent) {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  // 새 메시지 오면 맨 아래로 스크롤
  useEffect(() => {
    bodyRef.current?.scrollTo({ top: bodyRef.current.scrollHeight });
  }, [messages, loading, open]);

  async function handleSend() {
    const text = input.trim();
    if (!text || loading || !auth?.loggedIn) return;
    const history = messages;
    const next: ChatMessage[] = [...history, { role: "user", content: text }];
    setMessages(next);
    setInput("");
    setLoading(true);
    try {
      const answer = await sendChat(text, history, auth.cohort);
      setMessages([...next, { role: "assistant", content: answer }]);
    } catch (e) {
      setMessages([...next, { role: "assistant", content: `오류가 발생했어요: ${String(e)}` }]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div ref={rootRef} style={{ all: "initial", fontFamily: "system-ui, sans-serif" }}>
      {/* 채팅 패널 (말풍선) */}
      {open && (
        <div
          style={{
            position: "fixed",
            right: 24,
            bottom: 92,
            width: 360,
            height: 480,
            background: "#fff",
            borderRadius: 16,
            boxShadow: "0 12px 40px rgba(0,0,0,0.18)",
            display: "flex",
            flexDirection: "column",
            overflow: "hidden",
            zIndex: 2147483647,
          }}
        >
          <div style={{ padding: "12px 16px", background: "#2563eb", color: "#fff", fontWeight: 600, fontSize: 15 }}>
            🤝 소마 메이트
            {auth?.loggedIn && (
              <span style={{ float: "right", fontWeight: 400, fontSize: 12, opacity: 0.85 }}>{auth.cohort}</span>
            )}
          </div>

          {/* 로그인 확인 중 / 비로그인 / 정상 채팅 분기 */}
          {auth === null ? (
            <div style={{ flex: 1, display: "grid", placeItems: "center", color: "#94a3b8", fontSize: 13 }}>
              소마 로그인 확인 중…
            </div>
          ) : !auth.loggedIn ? (
            <div style={{ flex: 1, display: "grid", placeItems: "center", padding: 24, textAlign: "center", color: "#475569", fontSize: 13.5, lineHeight: 1.6 }}>
              🔒 소마 연수생만 이용할 수 있어요.
              <br />
              소마 포털에 로그인한 뒤 페이지를 새로고침해 주세요.
            </div>
          ) : (
            <>
              <div ref={bodyRef} style={{ flex: 1, overflowY: "auto", padding: 14, display: "flex", flexDirection: "column", gap: 8 }}>
                {messages.length === 0 && (
                  <p style={{ color: "#94a3b8", fontSize: 13, margin: 0 }}>
                    스택과 목표를 알려주세요.
                    <br />
                    예) "Spring 잘하고 창업 경험 있는 멘토 추천해줘"
                  </p>
                )}
                {messages.map((m, i) => (
                  <div
                    key={i}
                    style={{
                      alignSelf: m.role === "user" ? "flex-end" : "flex-start",
                      background: m.role === "user" ? "#2563eb" : "#f1f5f9",
                      color: m.role === "user" ? "#fff" : "#0f172a",
                      padding: "8px 12px",
                      borderRadius: 12,
                      maxWidth: "85%",
                      whiteSpace: "pre-wrap",
                      fontSize: 13.5,
                      lineHeight: 1.5,
                    }}
                  >
                    {m.content}
                  </div>
                ))}
                {loading && <div style={{ color: "#94a3b8", fontSize: 13 }}>생각 중…</div>}
              </div>

              <div style={{ display: "flex", gap: 8, padding: 12, borderTop: "1px solid #eef2f7" }}>
                <input
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleSend()}
                  placeholder="질문을 입력하세요"
                  autoFocus
                  style={{ flex: 1, padding: "9px 11px", borderRadius: 10, border: "1px solid #cbd5e1", fontSize: 13.5, outline: "none" }}
                />
                <button
                  onClick={handleSend}
                  disabled={loading}
                  style={{ padding: "0 14px", borderRadius: 10, border: "none", background: "#2563eb", color: "#fff", cursor: "pointer", fontSize: 13.5 }}
                >
                  전송
                </button>
              </div>
            </>
          )}
        </div>
      )}

      {/* 우측 하단 떠있는 버튼 (FAB) */}
      <button
        onClick={() => setOpen((v) => !v)}
        aria-label="소마 메이트 열기"
        style={{
          position: "fixed",
          right: 24,
          bottom: 24,
          width: 56,
          height: 56,
          borderRadius: "50%",
          border: "none",
          background: "#2563eb",
          color: "#fff",
          fontSize: 24,
          cursor: "pointer",
          boxShadow: "0 6px 20px rgba(37,99,235,0.5)",
          zIndex: 2147483647,
        }}
      >
        {open ? "✕" : "🤝"}
      </button>
    </div>
  );
}
