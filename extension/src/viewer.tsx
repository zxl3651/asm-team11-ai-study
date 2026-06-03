import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { GitBranch, ListChecks } from "lucide-react";
import { WorkflowDiagram } from "./components/WorkflowDiagram";
import "./styles.css";

type ViewerPayload =
  | {
      type: "trace";
      title: string;
      description: string;
      workflowMermaid: string;
      processingSteps: string[];
      createdAt: number;
    }
  | {
      type: "workflow";
      title: string;
      description: string;
      workflowMermaid: string;
      createdAt: number;
    }
  | {
      type: "processing";
      title: string;
      description: string;
      processingSteps: string[];
      createdAt: number;
    };

const getPayloadId = () => new URLSearchParams(window.location.search).get("id") || "";

const ViewerApp: React.FC = () => {
  const [payload, setPayload] = useState<ViewerPayload | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    const id = getPayloadId();
    if (!id) {
      setError("열람할 데이터가 없습니다.");
      return;
    }

    if (typeof chrome === "undefined" || !chrome.storage?.local) {
      const raw = sessionStorage.getItem(id);
      if (!raw) {
        setError("확장 프로그램 저장소를 사용할 수 없습니다.");
        return;
      }
      try {
        setPayload(JSON.parse(raw) as ViewerPayload);
      } catch {
        setError("처리 기록을 읽을 수 없습니다.");
      }
      return;
    }

    chrome.storage.local.get([id], (result) => {
      const value = result[id] as ViewerPayload | undefined;
      if (!value) {
        setError("처리 기록을 찾을 수 없습니다.");
        return;
      }
      setPayload(value);
    });
  }, []);

  if (error) {
    return (
      <main className="viewer-page">
        <section className="viewer-empty">{error}</section>
      </main>
    );
  }

  if (!payload) {
    return (
      <main className="viewer-page">
        <section className="viewer-empty">처리 기록을 불러오는 중...</section>
      </main>
    );
  }

  const isWorkflow = payload.type === "workflow";
  const isProcessing = payload.type === "processing";
  const processingSteps = "processingSteps" in payload ? payload.processingSteps : [];
  const workflowMermaid = "workflowMermaid" in payload ? payload.workflowMermaid : "";

  return (
    <main className="viewer-page">
      <header className="viewer-header">
        <div className="viewer-title-row">
          <div className="viewer-icon">{isProcessing ? <ListChecks size={24} /> : <GitBranch size={24} />}</div>
          <div>
            <h1>{payload.title}</h1>
            <p>{payload.description}</p>
          </div>
        </div>
        <span className="viewer-time">{new Date(payload.createdAt).toLocaleString("ko-KR")}</span>
      </header>

      <section className={`viewer-content ${isWorkflow || payload.type === "trace" ? "workflow-viewer-content" : ""}`}>
        {payload.type === "trace" ? (
          <div className="trace-layout">
            <aside className="trace-process-panel">
              <div className="trace-section-title">
                <ListChecks size={18} />
                <h2>처리 과정</h2>
              </div>
              <ol className="viewer-process-list compact">
                {processingSteps.map((step, idx) => (
                  <li key={`${step}-${idx}`}>
                    <span className="step-index">{idx + 1}</span>
                    <span>{step}</span>
                  </li>
                ))}
              </ol>
            </aside>
            <section className="trace-workflow-panel">
              <div className="trace-section-title">
                <GitBranch size={18} />
                <h2>처리 경로</h2>
              </div>
              {workflowMermaid ? <WorkflowDiagram definition={workflowMermaid} /> : <div className="viewer-empty">처리 경로 데이터가 없습니다.</div>}
            </section>
          </div>
        ) : isWorkflow ? (
          <WorkflowDiagram definition={workflowMermaid} />
        ) : (
          <ol className="viewer-process-list">
            {processingSteps.map((step, idx) => (
              <li key={`${step}-${idx}`}>
                <span className="step-index">{idx + 1}</span>
                <span>{step}</span>
              </li>
            ))}
          </ol>
        )}
      </section>
    </main>
  );
};

const root = createRoot(document.getElementById("root")!);
root.render(
  <React.StrictMode>
    <ViewerApp />
  </React.StrictMode>
);
