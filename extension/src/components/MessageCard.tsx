import React from "react";
import ReactMarkdown from "react-markdown";
import { Bot, User, AlertCircle } from "lucide-react";

export type MessageRole = "user" | "assistant" | "system";

export interface Message {
  id: string;
  role: MessageRole;
  content: string;
  timestamp: Date;
  agentFlowSteps?: string[];
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
        <div className="avatar assistant">
          <Bot size={16} />
        </div>
      )}
      <div className="message-bubble">
        {isSystem ? (
          <div style={{ display: "flex", gap: "8px", alignItems: "flex-start" }}>
            <AlertCircle size={16} style={{ flexShrink: 0, marginTop: "2px" }} />
            <div style={{ flex: 1 }}>
              <ReactMarkdown>{message.content}</ReactMarkdown>
            </div>
          </div>
        ) : isUser ? (
          <p>{message.content}</p>
        ) : (
          <>
            {message.agentFlowSteps && message.agentFlowSteps.length > 0 && (
              <details className="agent-flow-details" open>
                <summary className="agent-flow-summary">
                  <span>⚙️ Agent Flow ({message.agentFlowSteps.length} steps)</span>
                </summary>
                <ul className="agent-flow-list">
                  {message.agentFlowSteps.map((step, idx) => (
                    <li key={idx} className="agent-flow-step">
                      <span className="step-num">{idx + 1}</span>
                      <span className="step-text">{step}</span>
                    </li>
                  ))}
                </ul>
              </details>
            )}
            <ReactMarkdown>{message.content}</ReactMarkdown>
          </>
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
          <User size={16} />
        </div>
      )}
    </div>
  );
};
