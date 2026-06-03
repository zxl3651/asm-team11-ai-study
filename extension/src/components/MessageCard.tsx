import React from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Bot, User, AlertCircle, GitBranch } from "lucide-react";
import { ScheduleCalendar } from "./ScheduleCalendar";

export type MessageRole = "user" | "assistant" | "system";

export interface Message {
  id: string;
  role: MessageRole;
  content: string;
  timestamp: Date;
  workflowMermaid?: string;
  processingSteps?: string[];
}

interface MessageCardProps {
  message: Message;
  onShowTrace?: (message: Message) => void;
}

// Custom code block renderer: intercept ```schedule blocks
const markdownComponents = {
  code({
    className,
    children,
    ...props
  }: React.HTMLAttributes<HTMLElement> & { children?: React.ReactNode }) {
    const match = /language-(\w+)/.exec(className || "");
    const lang = match ? match[1] : null;

    if (lang === "schedule") {
      const content = String(children).replace(/\n$/, "");
      return <ScheduleCalendar content={content} />;
    }

    // Default inline/block code rendering
    if (lang) {
      return (
        <code className={className} {...props}>
          {children}
        </code>
      );
    }
    return (
      <code className={className} {...props}>
        {children}
      </code>
    );
  },
  // Ensure fenced code blocks with language are rendered via pre > code
  pre({ children, ...props }: React.HTMLAttributes<HTMLPreElement>) {
    const isSchedule = React.isValidElement(children) &&
      typeof children.props === "object" &&
      children.props !== null &&
      (children.props.className === "language-schedule" ||
       String((children.props as any).className).includes("language-schedule"));

    if (isSchedule) {
      return <>{children}</>;
    }
    return <pre {...props}>{children}</pre>;
  },
};

export const MessageCard: React.FC<MessageCardProps> = ({ message, onShowTrace }) => {
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
              <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
                {message.content}
              </ReactMarkdown>
            </div>
          </div>
        ) : isUser ? (
          <p>{message.content}</p>
        ) : (
          <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
            {message.content}
          </ReactMarkdown>
        )}
        <span className="timestamp">
          {message.timestamp.toLocaleTimeString("ko-KR", {
            hour: "2-digit",
            minute: "2-digit",
          })}
        </span>
        {!isUser && !isSystem && (
          <div className="message-actions">
            {onShowTrace && (message.processingSteps?.length || message.workflowMermaid) && (
              <button className="message-action-btn" onClick={() => onShowTrace(message)}>
                <GitBranch size={13} />
                <span>처리 흐름 한눈에 보기</span>
              </button>
            )}
          </div>
        )}
      </div>
      {isUser && (
        <div className="avatar user-avatar">
          <User size={16} />
        </div>
      )}
    </div>
  );
};
