import React from "react";
import ReactMarkdown from "react-markdown";

export type MessageRole = "user" | "assistant" | "system";

export interface Message {
  id: string;
  role: MessageRole;
  content: string;
  timestamp: Date;
}

interface MessageCardProps {
  message: Message;
}

export const MessageCard: React.FC<MessageCardProps> = ({ message }) => {
  const isUser = message.role === "user";
  const isSystem = message.role === "system";

  return (
    <div className={`message-card ${isUser ? "user" : isSystem ? "system" : "assistant"}`}>
      {!isUser && !isSystem && (
        <div className="avatar">
          <span>🤖</span>
        </div>
      )}
      <div className="message-bubble">
        {isUser ? (
          <p>{message.content}</p>
        ) : (
          <ReactMarkdown>{message.content}</ReactMarkdown>
        )}
        <span className="timestamp">
          {message.timestamp.toLocaleTimeString("ko-KR", {
            hour: "2-digit",
            minute: "2-digit",
          })}
        </span>
      </div>
      {isUser && (
        <div className="avatar user-avatar">
          <span>👤</span>
        </div>
      )}
    </div>
  );
};
