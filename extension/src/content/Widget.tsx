import { useEffect, useMemo, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { ChatMessage, streamChat } from "../lib/api";
import { runPortalSync, clearChatSession, SyncResult } from "./sync";
import { ScheduleCalendar } from "./components/ScheduleCalendar";
import { WorkflowDiagram } from "./components/WorkflowDiagram";

const BTN = 56; // FAB 지름
const GAP = 12; // FAB ↔ 패널 간격
const EDGE = 8; // 화면 가장자리 최소 여백
const MIN_W = 360;
const MIN_H = 460;
const POS_KEY = "soma-mate-pos";
const SIZE_KEY = "soma-mate-size";
const MSG_KEY = "soma-mate-messages";
const SESSION_KEY = "soma-mate-session";

const clamp = (v: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, v));

type Tab = "chat" | "viz";

interface Pos {
  x: number;
  y: number;
}
interface Size {
  w: number;
  h: number;
}

function loadJSON<T>(key: string, fallback: T): T {
  try {
    const s = localStorage.getItem(key);
    if (s) return JSON.parse(s) as T;
  } catch {
    /* ignore */
  }
  return fallback;
}

function initialPos(): Pos {
  return loadJSON(POS_KEY, { x: window.innerWidth - BTN - 24, y: window.innerHeight - BTN - 24 });
}
function initialSize(): Size {
  return loadJSON(SIZE_KEY, { w: 420, h: 600 });
}
function initialSession(): string {
  let s = "";
  try {
    s = localStorage.getItem(SESSION_KEY) || "";
  } catch {
    /* ignore */
  }
  if (!s) {
    s = `session_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`;
    try {
      localStorage.setItem(SESSION_KEY, s);
    } catch {
      /* ignore */
    }
  }
  return s;
}

/** 마지막 어시스턴트 메시지에서 ```schedule 블록을 추출. */
function extractScheduleBlock(content: string): string | null {
  const m = content.match(/```schedule\s*\n([\s\S]*?)```/);
  return m ? m[1].replace(/\n$/, "") : null;
}

// react-markdown: ```schedule 코드블록을 캘린더로 렌더.
const markdownComponents = {
  code({ className, children, ...props }: any) {
    const match = /language-(\w+)/.exec(className || "");
    const lang = match ? match[1] : null;
    if (lang === "schedule") {
      return <ScheduleCalendar content={String(children).replace(/\n$/, "")} />;
    }
    return (
      <code className={className} {...props}>
        {children}
      </code>
    );
  },
  pre({ children, ...props }: any) {
    const isSchedule =
      children &&
      typeof children === "object" &&
      children.props &&
      String(children.props.className || "").includes("language-schedule");
    if (isSchedule) return <>{children}</>;
    return <pre {...props}>{children}</pre>;
  },
  a({ children, ...props }: any) {
    return (
      <a target="_blank" rel="noopener noreferrer" {...props}>
        {children}
      </a>
    );
  },
};

// Shadow DOM 내부 전용 스타일 (CSS 변수 + 마크다운 + 캘린더 + 워크플로우)
const STYLE = `
.sm-root{
  --primary:#4f46e5;--primary-light:#e0e7ff;--primary-hover:#4338ca;
  --success:#10b981;--warning:#f59e0b;--error:#ef4444;
  --bg-app:#f8fafc;--bg-card:#fff;--border:#e2e8f0;--border-light:#f1f5f9;
  --text-primary:#0f172a;--text-secondary:#475569;--text-muted:#64748b;--text-light:#94a3b8;
  --font-title:system-ui,-apple-system,sans-serif;--font-body:system-ui,-apple-system,sans-serif;
  --shadow-sm:0 1px 2px 0 rgba(0,0,0,.05);
}
.sm-md p{margin:0 0 8px}
.sm-md h1,.sm-md h2,.sm-md h3{margin:10px 0 6px;font-size:14.5px;font-weight:700;line-height:1.3}
.sm-md ul,.sm-md ol{margin:4px 0 8px;padding-left:18px}
.sm-md li{margin:3px 0}
.sm-md a{color:#2563eb;text-decoration:underline;word-break:break-all}
.sm-md code{background:#e6ebf3;padding:1px 5px;border-radius:5px;font-size:12.5px;font-family:ui-monospace,monospace}
.sm-md pre{background:#0f172a;color:#e2e8f0;padding:10px 12px;border-radius:8px;overflow:auto;margin:6px 0}
.sm-md pre code{background:none;padding:0;color:inherit}
.sm-md table{border-collapse:collapse;margin:6px 0;font-size:12.5px}
.sm-md th,.sm-md td{border:1px solid #e2e8f0;padding:4px 8px}
.sm-md strong{font-weight:700}
.sm-md blockquote{margin:6px 0;padding:4px 12px;border-left:3px solid #cbd5e1;color:#475569}
.sm-md hr{border:none;border-top:1px solid #e2e8f0;margin:10px 0}
.sm-md > *:first-child{margin-top:0}
.sm-md > *:last-child{margin-bottom:0}
@keyframes sm-bounce{0%,80%,100%{transform:translateY(0);opacity:.4}40%{transform:translateY(-4px);opacity:1}}
.sm-dot{display:inline-block;width:6px;height:6px;border-radius:50%;background:#94a3b8;animation:sm-bounce 1.2s infinite}
.sm-dot:nth-child(2){animation-delay:.15s}
.sm-dot:nth-child(3){animation-delay:.3s}
.sm-body::-webkit-scrollbar{width:8px}
.sm-body::-webkit-scrollbar-thumb{background:#d3dae6;border-radius:8px}
.sm-spin{animation:sm-rot 1s linear infinite}
@keyframes sm-rot{to{transform:rotate(360deg)}}
.sm-loader{display:inline-block;width:13px;height:13px;border:2px solid #c7d2fe;border-top-color:#4f46e5;border-radius:50%;animation:sm-rot .7s linear infinite;flex:0 0 auto}
.sm-pulse{display:inline-flex;gap:3px;align-items:center}
.sm-pulse i{width:5px;height:5px;border-radius:50%;background:#4f46e5;animation:sm-pulse 1s ease-in-out infinite}
.sm-pulse i:nth-child(2){animation-delay:.18s}
.sm-pulse i:nth-child(3){animation-delay:.36s}
@keyframes sm-pulse{0%,100%{opacity:.3;transform:scale(.8)}50%{opacity:1;transform:scale(1)}}
.sm-steps{margin:6px 0 0;padding-left:0;list-style:none}
.sm-steps li{display:flex;gap:7px;align-items:flex-start;font-size:12px;color:#475569;margin:3px 0;line-height:1.4}
.sm-steps li .n{flex:0 0 16px;height:16px;border-radius:50%;background:#e0e7ff;color:#4f46e5;font-size:10px;font-weight:700;display:flex;align-items:center;justify-content:center;margin-top:1px}
.sm-steps li.active .n{background:#4f46e5;color:#fff}

/* ─ Schedule Calendar ─ */
.schedule-calendar-wrapper{margin:12px 0 8px;width:100%}
.schedule-calendar{overflow-x:auto;border-radius:10px;border:1px solid var(--border);box-shadow:var(--shadow-sm);background:#fff}
.schedule-calendar table{width:100%;border-collapse:collapse;font-size:11px;table-layout:fixed}
.schedule-calendar thead{position:sticky;top:0;z-index:2}
.schedule-calendar th{background:linear-gradient(135deg,#4f46e5,#6366f1);color:#fff;font-weight:600;font-size:10.5px;padding:8px 4px;text-align:center;white-space:nowrap;border:none}
.schedule-calendar th:first-child{border-radius:9px 0 0 0;width:52px;min-width:52px}
.schedule-calendar th:last-child{border-radius:0 9px 0 0}
.schedule-calendar .day-header{font-weight:700}
.schedule-calendar td{text-align:center;padding:0;height:28px;border:1px solid rgba(226,232,240,.5);position:relative}
.schedule-calendar .time-cell{font-size:10px;font-weight:500;color:var(--text-muted);background:#f8fafc;padding:4px 6px;white-space:nowrap;width:52px;min-width:52px;border-right:2px solid var(--border)}
.schedule-calendar .schedule-cell{cursor:default;overflow:visible}
.schedule-calendar .schedule-cell:hover{filter:brightness(.92);box-shadow:inset 0 0 0 1.5px rgba(0,0,0,.1)}
.schedule-calendar .cell-label{display:block;font-size:9px;font-weight:600;line-height:1.2;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;padding:0 2px;max-width:100%}
.schedule-calendar .schedule-tooltip{position:absolute;left:50%;bottom:calc(100% + 8px);transform:translateX(-50%) translateY(4px);z-index:20;min-width:160px;max-width:220px;padding:8px 10px;border-radius:8px;border:1px solid rgba(15,23,42,.12);background:rgba(15,23,42,.96);color:#f8fafc;box-shadow:0 10px 24px rgba(15,23,42,.18);opacity:0;visibility:hidden;pointer-events:none;transition:opacity .15s ease,transform .15s ease,visibility .15s ease;text-align:left}
.schedule-calendar .schedule-cell:hover .schedule-tooltip{opacity:1;visibility:visible;transform:translateX(-50%) translateY(0)}
.schedule-calendar .schedule-tooltip__header{font-size:10px;font-weight:700;margin-bottom:3px}
.schedule-calendar .schedule-tooltip__meta{font-size:9px;color:rgba(226,232,240,.78);margin-bottom:4px}
.schedule-calendar .schedule-tooltip__body{font-size:9px;line-height:1.4;color:rgba(248,250,252,.96);white-space:normal;word-break:keep-all}
.schedule-legend{display:flex;flex-wrap:wrap;gap:10px;margin-top:8px;padding:0 2px}
.legend-item{display:flex;align-items:center;gap:4px;font-size:10px;color:var(--text-secondary);font-weight:500}
.legend-swatch{display:inline-block;width:12px;height:12px;border-radius:3px;border:1px solid rgba(0,0,0,.08);flex-shrink:0}
.schedule-fallback{background:#f8fafc;border:1px solid var(--border);border-radius:8px;padding:12px;font-size:11px;white-space:pre-wrap;color:var(--text-secondary)}

/* ─ Workflow Diagram ─ */
.workflow-diagram{position:relative;display:flex;flex-direction:column;min-height:100%;background:#fff}
.workflow-toolbar{position:sticky;top:0;z-index:4;display:flex;align-items:center;gap:8px;padding:10px;border-bottom:1px solid var(--border);background:rgba(255,255,255,.94)}
.workflow-toolbar button{border:1px solid var(--border);border-radius:8px;background:var(--bg-card);color:var(--text-secondary);font-size:12px;font-weight:800;padding:7px 10px;cursor:pointer}
.workflow-toolbar button:hover{background:var(--primary-light);color:var(--primary)}
.workflow-toolbar span{min-width:48px;color:var(--text-muted);font-size:12px;font-weight:800;text-align:center}
.workflow-pan-stage{flex:1;min-height:760px;overflow:hidden;cursor:grab;touch-action:none;background:linear-gradient(#f1f5f9 1px,transparent 1px),linear-gradient(90deg,#f1f5f9 1px,transparent 1px);background-size:24px 24px}
.workflow-pan-stage:active{cursor:grabbing}
.workflow-pan-content{width:max-content;padding:24px;transform-origin:0 0}
.workflow-pan-content svg{display:block;max-width:none}
.workflow-svg .edgePaths path{stroke-dasharray:10 8;animation:wf 1.8s linear infinite}
@keyframes wf{from{stroke-dashoffset:18}to{stroke-dashoffset:0}}
.workflow-loading,.workflow-error{padding:40px 18px;color:var(--text-muted);font-size:13px;text-align:center}
.workflow-error{color:var(--error)}
`;

export function Widget() {
  const [open, setOpen] = useState(false);
  const [tab, setTab] = useState<Tab>("chat");
  const [messages, setMessages] = useState<ChatMessage[]>(() => loadJSON<ChatMessage[]>(MSG_KEY, []));
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [processingSteps, setProcessingSteps] = useState<string[]>([]);

  // 동기화 상태
  const [syncing, setSyncing] = useState(false);
  const [syncSteps, setSyncSteps] = useState<string[]>([]);
  const [syncOpen, setSyncOpen] = useState(false);
  const [syncResult, setSyncResult] = useState<SyncResult | null>(null);

  const [pos, setPos] = useState<Pos>(initialPos);
  const [size, setSize] = useState<Size>(initialSize);
  const sessionRef = useRef<string>(initialSession());

  const rootRef = useRef<HTMLDivElement>(null);
  const bodyRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const dragRef = useRef<{ sx: number; sy: number; ox: number; oy: number; moved: boolean } | null>(null);

  // 저장
  useEffect(() => {
    try {
      localStorage.setItem(POS_KEY, JSON.stringify(pos));
    } catch {
      /* ignore */
    }
  }, [pos]);
  useEffect(() => {
    try {
      localStorage.setItem(SIZE_KEY, JSON.stringify(size));
    } catch {
      /* ignore */
    }
  }, [size]);
  useEffect(() => {
    try {
      localStorage.setItem(MSG_KEY, JSON.stringify(messages));
    } catch {
      /* ignore */
    }
  }, [messages]);

  // 창 리사이즈 보정
  useEffect(() => {
    function onResize() {
      setPos((p) => ({
        x: clamp(p.x, EDGE, window.innerWidth - BTN - EDGE),
        y: clamp(p.y, EDGE, window.innerHeight - BTN - EDGE),
      }));
      setSize((s) => ({
        w: clamp(s.w, MIN_W, window.innerWidth * 0.9),
        h: clamp(s.h, MIN_H, window.innerHeight * 0.9),
      }));
    }
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  // Esc 로 닫기 (바깥 클릭은 데이터 수집 중 오작동 방지 위해 비활성)
  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);

  // 새 메시지/단계 → 맨 아래로 스크롤
  useEffect(() => {
    if (tab === "chat") bodyRef.current?.scrollTo({ top: bodyRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, loading, processingSteps, tab]);
  useEffect(() => {
    if (open && tab === "chat") setTimeout(() => inputRef.current?.focus(), 50);
  }, [open, tab]);

  // ── FAB 드래그 ──
  function onBtnMouseDown(e: React.MouseEvent) {
    e.preventDefault();
    dragRef.current = { sx: e.clientX, sy: e.clientY, ox: pos.x, oy: pos.y, moved: false };
    function onMove(ev: MouseEvent) {
      const d = dragRef.current;
      if (!d) return;
      const dx = ev.clientX - d.sx;
      const dy = ev.clientY - d.sy;
      if (Math.abs(dx) > 4 || Math.abs(dy) > 4) d.moved = true;
      setPos({
        x: clamp(d.ox + dx, EDGE, window.innerWidth - BTN - EDGE),
        y: clamp(d.oy + dy, EDGE, window.innerHeight - BTN - EDGE),
      });
    }
    function onUp() {
      const d = dragRef.current;
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
      dragRef.current = null;
      if (d && !d.moved) setOpen((v) => !v);
    }
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
  }

  // ── 패널 리사이즈 ──
  function onResizeMouseDown(e: React.MouseEvent, sx: number, sy: number) {
    e.preventDefault();
    e.stopPropagation();
    const startX = e.clientX;
    const startY = e.clientY;
    const startW = size.w;
    const startH = size.h;
    function onMove(ev: MouseEvent) {
      setSize({
        w: clamp(startW + (ev.clientX - startX) * sx, MIN_W, window.innerWidth * 0.9),
        h: clamp(startH + (ev.clientY - startY) * sy, MIN_H, window.innerHeight * 0.9),
      });
    }
    function onUp() {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    }
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
  }

  // ── 채팅 전송 (SSE 스트리밍) ──
  async function handleSend() {
    const text = input.trim();
    if (!text || loading) return;
    const next: ChatMessage[] = [...messages, { role: "user", content: text }];
    setMessages(next);
    setInput("");
    setLoading(true);
    setProcessingSteps(["요청을 확인하고 있어요..."]);
    const steps: string[] = ["요청을 확인하고 있어요..."];

    try {
      await streamChat(text, sessionRef.current, {
        onStatus: (msg) => {
          if (steps[steps.length - 1] !== msg) {
            steps.push(msg);
            setProcessingSteps([...steps]);
          }
        },
        onComplete: ({ response, workflowMermaid }) => {
          setMessages([
            ...next,
            { role: "assistant", content: response, workflowMermaid, processingSteps: [...steps] },
          ]);
        },
        onError: (msg) => {
          setMessages([...next, { role: "assistant", content: `⚠️ ${msg}` }]);
        },
      });
    } catch (e) {
      setMessages([...next, { role: "assistant", content: `⚠️ 오류가 발생했어요: ${String(e)}` }]);
    } finally {
      setLoading(false);
      setProcessingSteps([]);
    }
  }

  // ── 포털 데이터 동기화 (수동) ──
  async function handleSync() {
    if (syncing) return;
    setSyncing(true);
    setSyncOpen(true);
    setSyncSteps([]);
    const steps: string[] = [];
    // "… (3 / 10건 완료)" 같은 진행 메시지는 괄호 앞 텍스트를 단계 키로 보고,
    // 같은 단계면 줄을 새로 쌓지 않고 마지막 줄을 교체(숫자만 갱신)한다.
    const baseKey = (m: string) => m.replace(/\s*\([^)]*\)\s*$/, "").trim();
    const recordStep = (msg: string) => {
      const last = steps[steps.length - 1];
      if (last === msg) return;
      if (last && baseKey(last) === baseKey(msg) && /\([^)]*\)\s*$/.test(msg)) {
        steps[steps.length - 1] = msg; // 같은 진행 단계 → 교체
      } else {
        steps.push(msg);
      }
      setSyncSteps([...steps]);
    };
    const result = await runPortalSync(recordStep);
    setSyncResult(result);
    setSyncing(false);
    if (!result.ok) {
      recordStep(`⚠️ 동기화 실패: ${result.error || "알 수 없는 오류"}`);
    }
  }

  async function handleClearChat() {
    // 채팅 내용만 정리한다. 동기화된 포털 데이터(DB/벡터)는 건드리지 않는다.
    setMessages([]);
    setProcessingSteps([]);
    try {
      localStorage.removeItem(MSG_KEY);
    } catch {
      /* ignore */
    }
    await clearChatSession(sessionRef.current).catch(() => {});
  }

  // ── 시각화 탭용 최신 자료 추출 ──
  const latestWorkflow = useMemo(() => {
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i].role === "assistant" && messages[i].workflowMermaid) return messages[i].workflowMermaid!;
    }
    return null;
  }, [messages]);

  // ── 패널 위치/리사이즈 모서리 ──
  const onRight = pos.x + BTN / 2 > window.innerWidth / 2;
  const onBottom = pos.y + BTN / 2 > window.innerHeight / 2;
  const panelLeft = clamp(onRight ? pos.x + BTN - size.w : pos.x, EDGE, window.innerWidth - size.w - EDGE);
  const panelTop = clamp(onBottom ? pos.y - size.h - GAP : pos.y + BTN + GAP, EDGE, window.innerHeight - size.h - EDGE);
  const grip = {
    [onBottom ? "top" : "bottom"]: -3 as number,
    [onRight ? "left" : "right"]: -3 as number,
  };
  const gripCursor = onRight === onBottom ? "nwse-resize" : "nesw-resize";
  const resizeSx = onRight ? -1 : 1;
  const resizeSy = onBottom ? -1 : 1;

  const tabBtn = (key: Tab): React.CSSProperties => ({
    flex: 1,
    padding: "9px 0",
    textAlign: "center",
    cursor: "pointer",
    fontSize: 13,
    fontWeight: 600,
    color: tab === key ? "#fff" : "rgba(255,255,255,0.6)",
    borderBottom: tab === key ? "2px solid #fff" : "2px solid transparent",
    background: "transparent",
    border: "none",
  });

  return (
    <div ref={rootRef} className="sm-root" style={{ all: "initial", fontFamily: "system-ui, -apple-system, sans-serif" }}>
      <style>{STYLE}</style>

      {open && (
        <div
          style={{
            position: "fixed",
            left: panelLeft,
            top: panelTop,
            width: size.w,
            height: size.h,
            background: "#fff",
            borderRadius: 16,
            boxShadow: "0 16px 48px rgba(15,23,42,0.22)",
            display: "flex",
            flexDirection: "column",
            overflow: "hidden",
            zIndex: 2147483647,
          }}
        >
          {/* 헤더 */}
          <div style={{ background: "linear-gradient(135deg,#4f46e5,#4338ca)", color: "#fff" }}>
            <div
              style={{
                padding: "12px 16px 8px",
                fontWeight: 600,
                fontSize: 15,
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
              }}
            >
              <span>🤝 소마 메이트</span>
              <span style={{ display: "flex", alignItems: "center", gap: 12 }}>
                {messages.length > 0 && (
                  <span
                    onClick={handleClearChat}
                    style={{ cursor: "pointer", fontSize: 12, fontWeight: 400, opacity: 0.85 }}
                    title="대화 초기화"
                  >
                    ↺ 새 대화
                  </span>
                )}
                <span
                  onClick={() => setOpen(false)}
                  style={{ cursor: "pointer", fontSize: 16, opacity: 0.85, lineHeight: 1 }}
                  aria-label="닫기"
                >
                  ✕
                </span>
              </span>
            </div>
            {/* 탭 */}
            <div style={{ display: "flex", padding: "0 8px" }}>
              <button style={tabBtn("chat")} onClick={() => setTab("chat")}>
                💬 채팅
              </button>
              <button style={tabBtn("viz")} onClick={() => setTab("viz")}>
                📊 시각화
              </button>
            </div>
          </div>

          {/* 동기화 컨트롤 (양 탭 공통) */}
          <div style={{ borderBottom: "1px solid #e2e8f0", background: "#fbfcfe" }}>
            <div style={{ display: "flex", gap: 8, padding: "8px 12px" }}>
              <button
                onClick={handleSync}
                disabled={syncing}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 6,
                  padding: "7px 12px",
                  borderRadius: 8,
                  border: "1px solid #c7d2fe",
                  background: syncing ? "#eef2ff" : "#fff",
                  color: "#4f46e5",
                  fontSize: 12.5,
                  fontWeight: 600,
                  cursor: syncing ? "default" : "pointer",
                }}
              >
                {syncing ? (
                  <span className="sm-loader" />
                ) : (
                  <span style={{ display: "inline-block" }}>{syncResult?.ok ? "↻" : "⟳"}</span>
                )}
                {syncing ? "동기화 중…" : syncResult?.ok ? "데이터 동기화하기" : "포털 데이터 동기화"}
              </button>
              {(syncSteps.length > 0 || syncResult) && (
                <button
                  onClick={() => setSyncOpen((v) => !v)}
                  style={{
                    padding: "7px 10px",
                    borderRadius: 8,
                    border: "1px solid #e2e8f0",
                    background: "#fff",
                    color: "#475569",
                    fontSize: 12,
                    cursor: "pointer",
                  }}
                >
                  📡 수집 현황 {syncOpen ? "▲" : "▼"}
                </button>
              )}
            </div>
            {syncOpen && (syncSteps.length > 0 || syncResult) && (
              <div style={{ padding: "0 12px 10px" }}>
                <div
                  className="sm-body"
                  style={{
                    maxHeight: 160,
                    overflowY: "auto",
                    padding: "10px 12px",
                    background: "#fff",
                    border: "1px solid #e2e8f0",
                    borderRadius: 10,
                    boxShadow: "0 4px 12px rgba(15,23,42,0.10)",
                  }}
                >
                  <div style={{ fontSize: 11, fontWeight: 700, color: "#64748b", margin: "0 0 6px", letterSpacing: 0.2 }}>
                    📡 수집 현황
                  </div>
                  <ol className="sm-steps">
                    {syncSteps.map((s, i) => (
                      <li key={i} className={syncing && i === syncSteps.length - 1 ? "active" : ""}>
                        <span className="n">{i + 1}</span>
                        <span>{s}</span>
                      </li>
                    ))}
                  </ol>
                  {syncResult?.ok && (
                    <p style={{ margin: "8px 0 0", paddingTop: 8, borderTop: "1px solid #f1f5f9", fontSize: 11.5, color: "#16a34a" }}>
                      ✅ 멘토링 {syncResult.mentoringCount}건 · 팀 {syncResult.teamCount}건 · 상세 성공{" "}
                      {syncResult.detailSuccessCount}건 · 신청연결 {syncResult.participantLinkCount}건 · 벡터{" "}
                      {syncResult.vectorCount}건
                    </p>
                  )}
                </div>
              </div>
            )}
          </div>

          {/* ── 채팅 탭 ── */}
          {tab === "chat" && (
            <>
              <div
                ref={bodyRef}
                className="sm-body"
                style={{ flex: 1, overflowY: "auto", padding: 16, display: "flex", flexDirection: "column", gap: 10, background: "#f8fafc" }}
              >
                {messages.length === 0 && (
                  <div style={{ color: "#475569", fontSize: 13.5, lineHeight: 1.65 }}>
                    <p style={{ margin: "0 0 10px", fontWeight: 600, color: "#0f172a" }}>안녕하세요! 소마 메이트예요 🤝</p>
                    <p style={{ margin: "0 0 8px" }}>소마 데이터를 바탕으로 이런 걸 도와드려요:</p>
                    <ul style={{ margin: "0 0 12px", paddingLeft: 18 }}>
                      <li style={{ margin: "4px 0" }}>🧑‍🏫 <b>멘토 추천</b> — 스택·분야·창업경험 기반</li>
                      <li style={{ margin: "4px 0" }}>👥 <b>동료 연수생 찾기</b> · 🤝 <b>팀매칭 현황</b></li>
                      <li style={{ margin: "4px 0" }}>📅 <b>접수중 특강·멘토링</b> — 남은 자리·일정</li>
                      <li style={{ margin: "4px 0" }}>🗓 <b>팀 회의 시간 찾기</b> · 일정 충돌 분석</li>
                    </ul>
                    <p style={{ margin: "0 0 4px", color: "#ef4444", fontSize: 12 }}>
                      💡 먼저 위의 <b>포털 데이터 동기화</b>를 한 번 눌러 주세요.
                    </p>
                    <p style={{ margin: "8px 0 6px", color: "#94a3b8" }}>이렇게 물어보세요:</p>
                    {[
                      "연수생의 팀 정보를 알려줘.",
                      "연수생이 들을만한 특강을 한 개 추천해줘.",
                      "연수생의 팀에 대해서 이번주 특강/멘토링 일정을 제외하고, 2시간 회의 가능 시간을 알려줘.",
                      "연수생의 정보를 알려줘.",
                    ].map((q) => (
                      <button
                        key={q}
                        onClick={() => {
                          setInput(q);
                          inputRef.current?.focus();
                        }}
                        style={{
                          display: "block",
                          width: "100%",
                          textAlign: "left",
                          margin: "6px 0",
                          padding: "8px 11px",
                          borderRadius: 9,
                          border: "1px solid #e2e8f0",
                          background: "#fff",
                          color: "#4f46e5",
                          fontSize: 13,
                          cursor: "pointer",
                        }}
                      >
                        "{q}"
                      </button>
                    ))}
                  </div>
                )}
                {messages.map((m, i) =>
                  m.role === "user" ? (
                    <div
                      key={i}
                      style={{
                        alignSelf: "flex-end",
                        background: "#4f46e5",
                        color: "#fff",
                        padding: "9px 13px",
                        borderRadius: "14px 14px 4px 14px",
                        maxWidth: "85%",
                        whiteSpace: "pre-wrap",
                        fontSize: 14,
                        lineHeight: 1.55,
                      }}
                    >
                      {m.content}
                    </div>
                  ) : (
                    <div
                      key={i}
                      className="sm-md"
                      style={{
                        alignSelf: "flex-start",
                        background: "#fff",
                        color: "#0f172a",
                        padding: "11px 14px",
                        borderRadius: "14px 14px 14px 4px",
                        maxWidth: "95%",
                        fontSize: 14,
                        lineHeight: 1.6,
                        boxShadow: "0 1px 3px rgba(15,23,42,0.08)",
                        border: "1px solid #eef2f7",
                      }}
                    >
                      <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
                        {m.content}
                      </ReactMarkdown>
                      {(m.workflowMermaid || extractScheduleBlock(m.content)) && (
                        <button
                          onClick={() => setTab("viz")}
                          style={{
                            marginTop: 8,
                            display: "inline-flex",
                            alignItems: "center",
                            gap: 5,
                            padding: "5px 10px",
                            borderRadius: 7,
                            border: "1px solid #e2e8f0",
                            background: "#f8fafc",
                            color: "#4f46e5",
                            fontSize: 12,
                            cursor: "pointer",
                          }}
                        >
                          📊 처리 흐름·일정 시각화 보기
                        </button>
                      )}
                    </div>
                  )
                )}
                {loading && (
                  <div
                    style={{
                      alignSelf: "flex-start",
                      background: "#fff",
                      padding: "12px 14px",
                      borderRadius: "14px 14px 14px 4px",
                      boxShadow: "0 1px 3px rgba(15,23,42,0.08)",
                      border: "1px solid #eef2f7",
                      maxWidth: "95%",
                    }}
                  >
                    <div style={{ display: "flex", gap: 5, alignItems: "center" }}>
                      <span className="sm-dot" />
                      <span className="sm-dot" />
                      <span className="sm-dot" />
                    </div>
                    {processingSteps.length > 0 && (
                      <ol className="sm-steps">
                        {processingSteps.map((s, i) => (
                          <li key={i} className={i === processingSteps.length - 1 ? "active" : ""}>
                            <span className="n">{i + 1}</span>
                            <span>{s}</span>
                          </li>
                        ))}
                      </ol>
                    )}
                  </div>
                )}
              </div>

              <div style={{ display: "flex", gap: 8, padding: 12, borderTop: "1px solid #eef2f7", background: "#fff" }}>
                <textarea
                  ref={inputRef}
                  value={input}
                  disabled={loading}
                  rows={2}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      handleSend();
                    }
                  }}
                  placeholder={loading ? "답변을 기다리는 중…" : "질문을 입력하세요"}
                  style={{
                    flex: 1,
                    padding: "10px 12px",
                    borderRadius: 10,
                    border: "1px solid #cbd5e1",
                    fontSize: 14,
                    outline: "none",
                    resize: "none",
                    fontFamily: "inherit",
                    background: loading ? "#f1f5f9" : "#fff",
                  }}
                />
                <button
                  onClick={handleSend}
                  disabled={loading || !input.trim()}
                  style={{
                    padding: "0 16px",
                    borderRadius: 10,
                    border: "none",
                    background: loading || !input.trim() ? "#a5b4fc" : "#4f46e5",
                    color: "#fff",
                    cursor: loading || !input.trim() ? "default" : "pointer",
                    fontSize: 14,
                    fontWeight: 500,
                  }}
                >
                  전송
                </button>
              </div>
            </>
          )}

          {/* ── 시각화 탭 ── */}
          {tab === "viz" && (
            <div className="sm-body" style={{ flex: 1, overflowY: "auto", padding: 14, background: "#f8fafc" }}>
              <div style={{ margin: "0 0 8px", fontSize: 13, fontWeight: 700, color: "#0f172a" }}>🧭 에이전트 처리 흐름</div>
              {latestWorkflow ? (
                <div style={{ background: "#fff", border: "1px solid #e2e8f0", borderRadius: 10, overflow: "hidden", minHeight: 820 }}>
                  <WorkflowDiagram definition={latestWorkflow} />
                </div>
              ) : (
                <div style={{ padding: "18px 12px", fontSize: 12.5, color: "#94a3b8", textAlign: "center", background: "#fff", border: "1px dashed #e2e8f0", borderRadius: 10 }}>
                  아직 처리 흐름이 없어요. 질문을 보내면 에이전트 경로가 여기에 그려집니다.
                </div>
              )}
            </div>
          )}

          {/* 리사이즈 핸들 */}
          <div
            onMouseDown={(e) => onResizeMouseDown(e, resizeSx, resizeSy)}
            style={{ position: "absolute", ...grip, width: 18, height: 18, cursor: gripCursor, zIndex: 1 }}
          />
        </div>
      )}

      {/* FAB */}
      <button
        onMouseDown={onBtnMouseDown}
        aria-label="소마 메이트"
        style={{
          position: "fixed",
          left: pos.x,
          top: pos.y,
          width: BTN,
          height: BTN,
          borderRadius: "50%",
          border: "none",
          background: "linear-gradient(135deg,#4f46e5,#4338ca)",
          color: "#fff",
          fontSize: 24,
          cursor: "grab",
          boxShadow: "0 6px 20px rgba(79,70,229,0.5)",
          userSelect: "none",
          touchAction: "none",
          zIndex: 2147483647,
        }}
      >
        {open ? "✕" : "🤝"}
      </button>
    </div>
  );
}
