import { useEffect, useRef, useState } from "react";
import { marked } from "marked";

import { ChatMessage, sendChat, postContext } from "../lib/api";
import { AuthResult } from "./auth"; // checkAuth 는 게이팅 보류로 미사용
import { fetchOpenSessions } from "./sessions";
import { fetchTeams } from "./teams";

const BTN = 56; // FAB 지름
const GAP = 12; // FAB ↔ 패널 간격
const EDGE = 8; // 화면 가장자리 최소 여백
const MIN_W = 320;
const MIN_H = 400;
const POS_KEY = "soma-mate-pos";
const SIZE_KEY = "soma-mate-size";
const MSG_KEY = "soma-mate-messages";

const clamp = (v: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, v));

marked.setOptions({ gfm: true, breaks: true });

/** 어시스턴트 마크다운 → 안전한 HTML(링크는 새 탭). */
function renderMarkdown(text: string): string {
  const html = marked.parse(text) as string;
  return html.replace(/<a /g, '<a target="_blank" rel="noopener noreferrer" ');
}

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
  return loadJSON(SIZE_KEY, { w: 380, h: 520 });
}

// Shadow DOM 안에서만 적용되는 스타일 (마크다운/타이핑 애니메이션 등)
const STYLE = `
.sm-md p{margin:0 0 8px}
.sm-md h1,.sm-md h2,.sm-md h3{margin:10px 0 6px;font-size:14.5px;font-weight:700;line-height:1.3}
.sm-md ul,.sm-md ol{margin:4px 0 8px;padding-left:18px}
.sm-md li{margin:3px 0}
.sm-md a{color:#2563eb;text-decoration:underline;word-break:break-all}
.sm-md code{background:#e6ebf3;padding:1px 5px;border-radius:5px;font-size:12.5px;font-family:ui-monospace,monospace}
.sm-md pre{background:#0f172a;color:#e2e8f0;padding:10px 12px;border-radius:8px;overflow:auto;margin:6px 0}
.sm-md pre code{background:none;padding:0;color:inherit}
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
`;

export function Widget() {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>(() => loadJSON<ChatMessage[]>(MSG_KEY, []));
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  // [보류] 로그인 게이팅 비활성화 — 인증 기준 재설계 전까지 항상 통과로 둔다.
  const [auth] = useState<AuthResult | null>({ loggedIn: true, cohort: "" });
  const [pos, setPos] = useState<Pos>(initialPos);
  const [size, setSize] = useState<Size>(initialSize);

  const rootRef = useRef<HTMLDivElement>(null);
  const bodyRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const dragRef = useRef<{ sx: number; sy: number; ox: number; oy: number; moved: boolean } | null>(null);
  const ctxSentRef = useRef(false); // 특강/멘토링 컨텍스트 동기화 1회 가드

  // 위치/크기 저장
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
  // 대화 기록 저장 (페이지 이동·재방문해도 유지)
  useEffect(() => {
    try {
      localStorage.setItem(MSG_KEY, JSON.stringify(messages));
    } catch {
      /* ignore */
    }
  }, [messages]);

  // 창 크기 바뀌면 버튼/패널이 화면 밖으로 안 나가게 보정
  useEffect(() => {
    function onResize() {
      setPos((p) => ({
        x: clamp(p.x, EDGE, window.innerWidth - BTN - EDGE),
        y: clamp(p.y, EDGE, window.innerHeight - BTN - EDGE),
      }));
      setSize((s) => ({
        w: clamp(s.w, MIN_W, window.innerWidth * 0.8),
        h: clamp(s.h, MIN_H, window.innerHeight * 0.8),
      }));
    }
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  // 바깥 클릭 / Esc 로 닫기 (Shadow DOM: composedPath 로 내부 판정)
  useEffect(() => {
    if (!open) return;
    function onDown(e: MouseEvent) {
      if (rootRef.current && e.composedPath().includes(rootRef.current)) return;
      setOpen(false);
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

  // 새 메시지 오면 맨 아래로 스크롤 + 열릴 때 입력창 포커스
  useEffect(() => {
    bodyRef.current?.scrollTo({ top: bodyRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, loading]);
  useEffect(() => {
    if (open) setTimeout(() => inputRef.current?.focus(), 50);
  }, [open]);

  // 마운트 즉시 1회(백그라운드): 접수중 특강/멘토링을 세션으로 파싱해 백엔드 캐시에 올린다.
  // 위젯을 열기 전에 미리 동기화해 두어, 사용자가 열자마자 질문해도 데이터가 준비돼 있게 한다.
  useEffect(() => {
    if (ctxSentRef.current) return;
    ctxSentRef.current = true;
    Promise.all([fetchOpenSessions(), fetchTeams()])
      .then(([sessions, teams]) => postContext({ sessions, teams }))
      .catch(() => {
        ctxSentRef.current = false; // 실패 시 재시도 여지
      });
  }, []);

  // ── FAB 드래그: 이동했으면 위치만, 안 움직였으면 클릭=토글 ──
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

  // ── 패널 모서리 리사이즈 ──
  function onResizeMouseDown(e: React.MouseEvent, sx: number, sy: number) {
    e.preventDefault();
    e.stopPropagation();
    const startX = e.clientX;
    const startY = e.clientY;
    const startW = size.w;
    const startH = size.h;
    function onMove(ev: MouseEvent) {
      setSize({
        w: clamp(startW + (ev.clientX - startX) * sx, MIN_W, window.innerWidth * 0.8),
        h: clamp(startH + (ev.clientY - startY) * sy, MIN_H, window.innerHeight * 0.8),
      });
    }
    function onUp() {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    }
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
  }

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
      setMessages([...next, { role: "assistant", content: `⚠️ 오류가 발생했어요: ${String(e)}` }]);
    } finally {
      setLoading(false);
    }
  }

  // ── 패널 위치(FAB 사분면의 반대쪽) + 리사이즈 모서리 ──
  const onRight = pos.x + BTN / 2 > window.innerWidth / 2;
  const onBottom = pos.y + BTN / 2 > window.innerHeight / 2;
  const panelLeft = clamp(onRight ? pos.x + BTN - size.w : pos.x, EDGE, window.innerWidth - size.w - EDGE);
  const panelTop = clamp(onBottom ? pos.y - size.h - GAP : pos.y + BTN + GAP, EDGE, window.innerHeight - size.h - EDGE);
  // 리사이즈 핸들은 FAB 반대쪽(빈 공간 쪽) 모서리에 둔다.
  const grip = {
    [onBottom ? "top" : "bottom"]: -3 as number,
    [onRight ? "left" : "right"]: -3 as number,
  };
  const gripCursor = onRight === onBottom ? "nwse-resize" : "nesw-resize";
  const resizeSx = onRight ? -1 : 1;
  const resizeSy = onBottom ? -1 : 1;

  return (
    <div ref={rootRef} style={{ all: "initial", fontFamily: "system-ui, -apple-system, sans-serif" }}>
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
          <div
            style={{
              padding: "13px 16px",
              background: "linear-gradient(135deg,#2563eb,#1d4ed8)",
              color: "#fff",
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
                  onClick={() => {
                    setMessages([]);
                    setInput("");
                  }}
                  style={{ cursor: "pointer", fontSize: 12, fontWeight: 400, opacity: 0.85 }}
                  aria-label="대화 초기화"
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

          <div
            ref={bodyRef}
            className="sm-body"
            style={{ flex: 1, overflowY: "auto", padding: 16, display: "flex", flexDirection: "column", gap: 10, background: "#f8fafc" }}
          >
            {messages.length === 0 && (
              <div style={{ color: "#475569", fontSize: 13.5, lineHeight: 1.65 }}>
                <p style={{ margin: "0 0 10px", fontWeight: 600, color: "#0f172a" }}>
                  안녕하세요! 소마 메이트예요 🤝
                </p>
                <p style={{ margin: "0 0 8px" }}>소마 데이터를 바탕으로 이런 걸 도와드려요:</p>
                <ul style={{ margin: "0 0 12px", paddingLeft: 18 }}>
                  <li style={{ margin: "4px 0" }}>🧑‍🏫 <b>멘토 추천</b> — 스택·분야·창업경험 기반</li>
                  <li style={{ margin: "4px 0" }}>👥 <b>동료 연수생 찾기</b> — 팀원·같은 스택</li>
                  <li style={{ margin: "4px 0" }}>🤝 <b>팀매칭 현황</b> — 누가 어느 팀, 매칭 멘토</li>
                  <li style={{ margin: "4px 0" }}>📅 <b>접수중 특강·멘토링</b> — 남은 자리·일정</li>
                </ul>
                <p style={{ margin: "0 0 6px", color: "#94a3b8" }}>이렇게 물어보세요:</p>
                {[
                  "React 쓰는 풀스택 멘토 추천해줘",
                  "AI 에이전트 관련 접수중 특강 있어?",
                  "백엔드 하면서 팀 구하는 연수생 찾아줘",
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
                      color: "#2563eb",
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
                    background: "#2563eb",
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
                    maxWidth: "92%",
                    fontSize: 14,
                    lineHeight: 1.6,
                    boxShadow: "0 1px 3px rgba(15,23,42,0.08)",
                    border: "1px solid #eef2f7",
                  }}
                  dangerouslySetInnerHTML={{ __html: renderMarkdown(m.content) }}
                />
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
                  display: "flex",
                  gap: 5,
                  alignItems: "center",
                }}
              >
                <span className="sm-dot" />
                <span className="sm-dot" />
                <span className="sm-dot" />
              </div>
            )}
          </div>

          <div style={{ display: "flex", gap: 8, padding: 12, borderTop: "1px solid #eef2f7", background: "#fff" }}>
            <input
              ref={inputRef}
              value={input}
              disabled={loading}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSend()}
              placeholder={loading ? "답변을 기다리는 중…" : "질문을 입력하세요"}
              style={{
                flex: 1,
                padding: "10px 12px",
                borderRadius: 10,
                border: "1px solid #cbd5e1",
                fontSize: 14,
                outline: "none",
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
                background: loading || !input.trim() ? "#93b4f5" : "#2563eb",
                color: "#fff",
                cursor: loading || !input.trim() ? "default" : "pointer",
                fontSize: 14,
                fontWeight: 500,
              }}
            >
              전송
            </button>
          </div>

          {/* 리사이즈 핸들 (FAB 반대쪽 모서리) */}
          <div
            onMouseDown={(e) => onResizeMouseDown(e, resizeSx, resizeSy)}
            style={{ position: "absolute", ...grip, width: 18, height: 18, cursor: gripCursor, zIndex: 1 }}
          />
        </div>
      )}

      {/* 드래그 가능한 FAB 버튼 */}
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
          background: "linear-gradient(135deg,#2563eb,#1d4ed8)",
          color: "#fff",
          fontSize: 24,
          cursor: "grab",
          boxShadow: "0 6px 20px rgba(37,99,235,0.5)",
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
