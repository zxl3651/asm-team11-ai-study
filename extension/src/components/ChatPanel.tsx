import React, { useCallback, useEffect, useRef, useState } from "react";
import { Message, MessageCard } from "./MessageCard";

const API_BASE = "http://localhost:8000";

const QUICK_QUESTIONS = [
  "Spring 잘 아는 멘토 추천해줘",
  "클라우드 관련 접수중인 것 뭐 있어?",
  "창업 도움받을 수 있는 멘토 알려줘",
  "지금 신청 가능한 특강 알려줘",
];

function generateId(): string {
  return Math.random().toString(36).substring(2, 9);
}

function generateSessionId(): string {
  return `session_${Date.now()}_${Math.random().toString(36).substring(2, 6)}`;
}

export const ChatPanel: React.FC = () => {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: "welcome",
      role: "assistant",
      content:
        "안녕하세요! 소마 메이트입니다 👋\n\n저는 소마 연수생을 위한 AI 비서예요. 멘토 추천, 멘토링/특강 정보를 자연어로 물어보세요!\n\n**예시 질문:**\n- \"React랑 Node 잘 아는 창업 경험 있는 멘토 추천해줘\"\n- \"클라우드 관련 지금 신청할 수 있는 거 뭐 있어?\"\n- \"ML 멘토링 알려줘\"",
      timestamp: new Date(),
    },
  ]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [sessionId] = useState<string>(generateSessionId);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, scrollToBottom]);

  const sendMessage = useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      if (!trimmed || isLoading) return;

      const userMsg: Message = {
        id: generateId(),
        role: "user",
        content: trimmed,
        timestamp: new Date(),
      };

      setMessages((prev) => [...prev, userMsg]);
      setInput("");
      setIsLoading(true);

      try {
        const res = await fetch(`${API_BASE}/chat`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ message: trimmed, session_id: sessionId }),
        });

        if (!res.ok) {
          throw new Error(`서버 오류: ${res.status}`);
        }

        const data = await res.json();
        const assistantMsg: Message = {
          id: generateId(),
          role: "assistant",
          content: data.response,
          timestamp: new Date(),
        };
        setMessages((prev) => [...prev, assistantMsg]);
      } catch (err) {
        const errorMsg: Message = {
          id: generateId(),
          role: "system",
          content:
            "⚠️ 서버에 연결할 수 없어요. 백엔드 서버가 실행 중인지 확인해주세요.\n\n`cd backend && python main.py`",
          timestamp: new Date(),
        };
        setMessages((prev) => [...prev, errorMsg]);
      } finally {
        setIsLoading(false);
        inputRef.current?.focus();
      }
    },
    [isLoading, sessionId]
  );

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage(input);
    }
  };

  const clearChat = async () => {
    await fetch(`${API_BASE}/chat/${sessionId}`, { method: "DELETE" }).catch(() => {});
    setMessages([
      {
        id: "welcome-new",
        role: "assistant",
        content: "대화가 초기화되었어요! 새로운 질문을 해주세요 😊",
        timestamp: new Date(),
      },
    ]);
  };

  return (
    <div className="chat-panel">
      <header className="chat-header">
        <div className="header-left">
          <span className="logo">🎓</span>
          <div>
            <h1>소마 메이트</h1>
            <p>소프트웨어 마에스트로 AI 비서</p>
          </div>
        </div>
        <button className="clear-btn" onClick={clearChat} title="대화 초기화">
          🔄
        </button>
      </header>

      <div className="messages-container">
        {messages.map((msg) => (
          <MessageCard key={msg.id} message={msg} />
        ))}
        {isLoading && (
          <div className="loading-indicator">
            <div className="avatar">
              <span>🤖</span>
            </div>
            <div className="loading-dots">
              <span></span>
              <span></span>
              <span></span>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {messages.length <= 2 && (
        <div className="quick-questions">
          {QUICK_QUESTIONS.map((q) => (
            <button key={q} className="quick-btn" onClick={() => sendMessage(q)}>
              {q}
            </button>
          ))}
        </div>
      )}

      <div className="input-area">
        <textarea
          ref={inputRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="멘토나 멘토링에 대해 물어보세요... (Enter로 전송)"
          rows={2}
          disabled={isLoading}
        />
        <button
          className="send-btn"
          onClick={() => sendMessage(input)}
          disabled={!input.trim() || isLoading}
        >
          ▶
        </button>
      </div>
    </div>
  );
};
