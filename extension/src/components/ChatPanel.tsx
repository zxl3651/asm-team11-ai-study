import React, { useCallback, useEffect, useRef, useState } from "react";
import { Message, MessageCard } from "./MessageCard";
import { GraduationCap, RotateCcw, Info, SendHorizontal, Calendar, Bot, RefreshCw, Trash2, ChevronDown } from "lucide-react";
import {
  parseMentoringListPage,
  parseCalendarResultList,
  parseTeamPage,
  parseHistoryPage,
  parseMentoringDetailPage,
  parseMyInfoPage
} from "../parserUtils";

const API_BASE = "http://localhost:8000";

function generateId(): string {
  return Math.random().toString(36).substring(2, 9);
}

function generateSessionId(): string {
  return `session_${Date.now()}_${Math.random().toString(36).substring(2, 6)}`;
}

// ── chrome.storage.local에서 실시간 파싱 데이터 로드 ──

interface SyncStatus {
  hasUserInfo: boolean;
  hasMentorings: boolean;
  hasTeams: boolean;
  hasHistoryCalendar: boolean;
  hasSchedule: boolean;
  userInfoTimestamp: number | null;
  mentoringTimestamp: number | null;
  teamTimestamp: number | null;
  historyCalendarTimestamp: number | null;
  scheduleTimestamp: number | null;
  userInfoName: string;
  mentoringCount: number;
  teamCount: number;
  historyCalendarCount: number;
  scheduleCount: number;
}

async function loadParsedMentorings(): Promise<any[]> {
  return new Promise((resolve) => {
    if (typeof chrome !== "undefined" && chrome.storage && chrome.storage.local) {
      chrome.storage.local.get(["parsedMentorings"], (result) => {
        resolve(result.parsedMentorings || []);
      });
    } else {
      resolve([]);
    }
  });
}

async function loadParsedCalendar(): Promise<any[]> {
  return new Promise((resolve) => {
    if (typeof chrome !== "undefined" && chrome.storage && chrome.storage.local) {
      chrome.storage.local.get(
        ["parsedHistoryCalendar", "parsedSchedule"],
        (result) => {
          const history = result.parsedHistoryCalendar || [];
          const schedule = result.parsedSchedule || [];

          const formattedHistory = history.map((item: any) => ({
            source: "user_history",
            subjectTitle: item.title || "",
            date: item.dateStr || "",
            timeRangeStr: item.timeRangeStr || "",
            author: item.author || "",
            isApproved: item.isApproved || false,
            url: item.url || "",
          }));

          const formattedSchedule = schedule.map((item: any) => ({
            subjectTitle: item.subjectTitle || "",
            date: item.date || "",
            timeRangeStr: "09:00 ~ 18:00",
            author: "소마 센터",
            isApproved: true,
            url: item.url || "",
          }));

          resolve([...formattedHistory, ...formattedSchedule]);
        }
      );
    } else {
      resolve([]);
    }
  });
}

async function loadParsedTeamInfo(): Promise<any[]> {
  return new Promise((resolve) => {
    if (typeof chrome !== "undefined" && chrome.storage && chrome.storage.local) {
      chrome.storage.local.get(["parsedTeamInfo"], (result) => {
        resolve(result.parsedTeamInfo || []);
      });
    } else {
      resolve([]);
    }
  });
}

async function loadSyncStatus(): Promise<SyncStatus> {
  return new Promise((resolve) => {
    if (typeof chrome !== "undefined" && chrome.storage && chrome.storage.local) {
      chrome.storage.local.get(
        [
          "parsedMentorings",
          "parsedTeamInfo",
          "parsedHistoryCalendar",
          "parsedSchedule",
          "parsedUserInfo",
          "mentoringParseTimestamp",
          "teamParseTimestamp",
          "historyCalendarParseTimestamp",
          "scheduleParseTimestamp",
          "userInfoParseTimestamp",
        ],
        (result) => {
          const mList = result.parsedMentorings || [];
          const tList = result.parsedTeamInfo || [];
          const hcList = result.parsedHistoryCalendar || [];
          const sList = result.parsedSchedule || [];
          const userInfo = result.parsedUserInfo || null;
          resolve({
            hasUserInfo: !!(userInfo && (userInfo.name || userInfo.email || userInfo.phone)),
            hasMentorings: mList.length > 0,
            hasTeams: tList.length > 0,
            hasHistoryCalendar: hcList.length > 0,
            hasSchedule: sList.length > 0,
            userInfoTimestamp: result.userInfoParseTimestamp || null,
            mentoringTimestamp: result.mentoringParseTimestamp || null,
            teamTimestamp: result.teamParseTimestamp || null,
            historyCalendarTimestamp: result.historyCalendarParseTimestamp || null,
            scheduleTimestamp: result.scheduleParseTimestamp || null,
            userInfoName: userInfo?.name || "",
            mentoringCount: mList.length,
            teamCount: tList.length,
            historyCalendarCount: hcList.length,
            scheduleCount: sList.length,
          });
        }
      );
    } else {
      resolve({
        hasUserInfo: false,
        hasMentorings: false,
        hasTeams: false,
        hasHistoryCalendar: false,
        hasSchedule: false,
        userInfoTimestamp: null,
        mentoringTimestamp: null,
        teamTimestamp: null,
        historyCalendarTimestamp: null,
        scheduleTimestamp: null,
        userInfoName: "",
        mentoringCount: 0,
        teamCount: 0,
        historyCalendarCount: 0,
        scheduleCount: 0,
      });
    }
  });
}

function formatTimestamp(ts: number | null): string {
  if (!ts) return "미수집";
  const date = new Date(ts);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMin = Math.floor(diffMs / 60000);

  if (diffMin < 1) return "방금 전";
  if (diffMin < 60) return `${diffMin}분 전`;
  const diffHour = Math.floor(diffMin / 60);
  if (diffHour < 24) return `${diffHour}시간 전`;
  return date.toLocaleDateString("ko-KR", { month: "short", day: "numeric" });
}

// ── 메인 컴포넌트 ─────────────────────────────────────

export const ChatPanel: React.FC = () => {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: "welcome",
      role: "assistant",
      content:
        "안녕하세요! 소마 메이트입니다 👋\n\n저는 소마 연수생의 스케쥴 관리를 위한 AI 비서예요!",
      timestamp: new Date(),
    },
  ]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [sessionId] = useState<string>(generateSessionId);
  const [syncStatus, setSyncStatus] = useState<SyncStatus>({
    hasUserInfo: false,
    hasMentorings: false,
    hasTeams: false,
    hasHistoryCalendar: false,
    hasSchedule: false,
    userInfoTimestamp: null,
    mentoringTimestamp: null,
    teamTimestamp: null,
    historyCalendarTimestamp: null,
    scheduleTimestamp: null,
    userInfoName: "",
    mentoringCount: 0,
    teamCount: 0,
    historyCalendarCount: 0,
    scheduleCount: 0,
  });
  const [syncProgress, setSyncProgress] = useState<string | null>(null);
  const [agentStatus, setAgentStatus] = useState<string | null>(null);
  const [processingSteps, setProcessingSteps] = useState<string[]>([]);
  const [isSyncStatusOpen, setIsSyncStatusOpen] = useState(true);


  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const processingStepsRef = useRef<string[]>([]);

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, scrollToBottom]);

  // 마운트 시 동기화 상태 로드
  const refreshSyncStatus = useCallback(async () => {
    const status = await loadSyncStatus();
    setSyncStatus(status);
  }, []);

  useEffect(() => {
    refreshSyncStatus();

    // chrome.storage 변경 감지 (Content Script 파싱 완료 시 자동 갱신)
    if (typeof chrome !== "undefined" && chrome.storage && chrome.storage.onChanged) {
      const listener = (changes: any, area: string) => {
        if (area === "local") {
          refreshSyncStatus();
        }
      };
      chrome.storage.onChanged.addListener(listener);
      return () => chrome.storage.onChanged.removeListener(listener);
    }
  }, [refreshSyncStatus]);

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
      setAgentStatus("요청을 확인하고 있어요...");
      processingStepsRef.current = ["요청을 확인하고 있어요..."];
      setProcessingSteps(["요청을 확인하고 있어요..."]);

      try {
        const res = await fetch(`${API_BASE}/chat`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            message: trimmed,
            session_id: sessionId,
            user_calendar: null,
            available_mentorings: null,
            team_info: null,
          }),
        });

        if (!res.ok) {
          throw new Error(`서버 오류: ${res.status}`);
        }

        const reader = res.body?.getReader();
        const decoder = new TextDecoder();
        if (!reader) {
          throw new Error("스트림 리더를 생성할 수 없습니다.");
        }

        let buffer = "";

        while (true) {
          const { value, done } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n\n");
          buffer = lines.pop() || "";

          for (const line of lines) {
            const trimmedLine = line.trim();
            if (!trimmedLine.startsWith("data: ")) continue;

            const rawData = trimmedLine.substring(6).trim();
            if (!rawData) continue;

            try {
              const data = JSON.parse(rawData);
              if (data.type === "status") {
                setAgentStatus(data.message);
                setProcessingSteps((prev) => {
                  if (!data.message || prev[prev.length - 1] === data.message) return prev;
                  const next = [...prev, data.message];
                  processingStepsRef.current = next;
                  return next;
                });
              } else if (data.type === "complete") {
                const assistantMsg: Message = {
                  id: generateId(),
                  role: "assistant",
                  content: data.response,
                  timestamp: new Date(),
                  workflowMermaid: data.workflow_mermaid || undefined,
                  processingSteps: processingStepsRef.current,
                };
                setMessages((prev) => [...prev, assistantMsg]);
                setAgentStatus(null);
              } else if (data.type === "error") {
                throw new Error(data.message);
              }
            } catch (jsonErr) {
              console.warn("[SoMa Mate] SSE JSON 파싱 실패:", jsonErr);
            }
          }
        }
      } catch (err: any) {
        const errorMsg: Message = {
          id: generateId(),
          role: "system",
          content:
            "⚠️ 서버에 연결할 수 없어요. 백엔드 서버가 실행 중인지 확인해주세요.\n\n`./start.sh`를 통해 백엔드를 재시작할 수 있습니다.",
          timestamp: new Date(),
        };
        setMessages((prev) => [...prev, errorMsg]);
      } finally {
        setIsLoading(false);
        setAgentStatus(null);
        processingStepsRef.current = [];
        setProcessingSteps([]);
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

  const openViewerWindow = useCallback(async (payload: any) => {
    const id = `somaViewer:${Date.now()}:${generateId()}`;
    const url = typeof chrome !== "undefined" && chrome.runtime
      ? chrome.runtime.getURL(`viewer.html?id=${encodeURIComponent(id)}`)
      : `viewer.html?id=${encodeURIComponent(id)}`;

    const openWindow = () => {
      if (typeof chrome !== "undefined" && chrome.tabs?.create) {
        chrome.tabs.create({ url, active: true });
      } else {
        window.open(url, "_blank", "width=1280,height=900");
      }
    };

    if (typeof chrome !== "undefined" && chrome.storage?.local) {
      chrome.storage.local.set({ [id]: payload }, openWindow);
    } else {
      sessionStorage.setItem(id, JSON.stringify(payload));
      openWindow();
    }
  }, []);

  const openTraceViewer = useCallback(
    (message: Message) => {
      openViewerWindow({
        type: "trace",
        title: "처리 흐름",
        description: "응답 생성 과정과 실제로 선택된 LLM 분기 경로를 한 화면에서 봅니다.",
        workflowMermaid: message.workflowMermaid || "",
        processingSteps: message.processingSteps || [],
        createdAt: Date.now(),
      });
    },
    [openViewerWindow]
  );

  // 가장 최근 동기화 시각 계산
  const latestTimestamp = Math.max(
    syncStatus.userInfoTimestamp || 0,
    syncStatus.mentoringTimestamp || 0,
    syncStatus.teamTimestamp || 0,
    syncStatus.historyCalendarTimestamp || 0,
    syncStatus.scheduleTimestamp || 0
  );

  const hasAnyData =
    syncStatus.hasUserInfo || syncStatus.hasMentorings || syncStatus.hasTeams || syncStatus.hasHistoryCalendar || syncStatus.hasSchedule;

  const dataCount = [
    syncStatus.hasUserInfo,
    syncStatus.hasMentorings,
    syncStatus.hasTeams,
    syncStatus.hasHistoryCalendar,
    syncStatus.hasSchedule,
  ].filter(Boolean).length;

  const clearSyncData = async () => {
    if (typeof chrome !== "undefined" && chrome.storage && chrome.storage.local) {
      chrome.storage.local.clear(async () => {
        await fetch(`${API_BASE}/chat`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            message: "동기화 데이터를 수동으로 초기화했습니다.",
            session_id: sessionId,
            user_calendar: [],
            available_mentorings: [],
            team_info: [],
            user_info: {},
          }),
        }).catch(() => {});

        refreshSyncStatus();
      });
    }
  };

  const triggerBackgroundSync = async (silent = false) => {
    if (!silent) setIsLoading(true);
    try {
      const origins = ["https://www.swmaestro.ai", "https://swmaestro.org"];
      const centers = ["/busan", ""]; // 부산 센터 / 서울 본원
      let successCount = 0;
      const timestamp = Date.now();

      const fetchAndParse = async (pathSuffix: string, parser: (doc: Document) => any) => {
        for (const origin of origins) {
          for (const center of centers) {
            const url = `${origin}${center}/sw/mypage/${pathSuffix}`;
            try {
              const res = await fetch(url, { credentials: "include" });
              if (res.ok) {
                const html = await res.text();
                // 로그인 페이지로 튕겼는지 검사 (대략 "login" 폼이나 리다이렉션 여부 확인)
                if (html.includes("loginForm") || html.includes("member/user/login.do")) {
                  continue;
                }
                const doc = new DOMParser().parseFromString(html, "text/html");
                const data = parser(doc);
                if (data !== null) {
                  return data;
                }
              }
            } catch (e) {
              // 에러 무시하고 다음 주소 시도
            }
          }
        }
        return null;
      };

      // ── 병렬 처리용 컨커런트 풀 (Concurrent Worker Pool) 헬퍼 ──
      const runConcurrentPool = async <T, R>(
        items: T[],
        concurrency: number,
        workerFn: (item: T, index: number) => Promise<R>,
        onProgress?: (completed: number, total: number) => void
      ): Promise<R[]> => {
        const results: R[] = new Array(items.length);
        let activeIndex = 0;
        let completedCount = 0;

        const worker = async () => {
          while (activeIndex < items.length) {
            const index = activeIndex++;
            try {
              results[index] = await workerFn(items[index], index);
            } catch (e) {
              console.error(`[SoMa Mate] Concurrent pool worker error at index ${index}:`, e);
            } finally {
              completedCount++;
              if (onProgress) {
                onProgress(completedCount, items.length);
              }
            }
          }
        };

        const workers = [];
        const numWorkers = Math.min(concurrency, items.length);
        for (let w = 0; w < numWorkers; w++) {
          workers.push(worker());
        }
        await Promise.all(workers);
        return results;
      };

      // ── 다중 페이지 (페이징) HTML 수집 헬퍼 ──
      const fetchAllPagesDocs = async (pathSuffix: string, label: string): Promise<Document[] | null> => {
        let connector = pathSuffix.includes("?") ? "&" : "?";
        let page1Suffix = `${pathSuffix}${connector}pageIndex=1`;
        
        setSyncProgress(`${label} 첫 페이지 분석 중...`);
        let page1Doc: Document | null = null;
        let matchedOrigin = "";
        let matchedCenter = "";

        // 첫 페이지를 찾아서 세션이 유효한 origin, center 확인
        for (const origin of origins) {
          for (const center of centers) {
            const url = `${origin}${center}/sw/mypage/${page1Suffix}`;
            try {
              const res = await fetch(url, { credentials: "include" });
              if (res.ok) {
                const html = await res.text();
                if (html.includes("loginForm") || html.includes("member/user/login.do")) {
                  continue;
                }
                page1Doc = new DOMParser().parseFromString(html, "text/html");
                matchedOrigin = origin;
                matchedCenter = center;
                break;
              }
            } catch (e) {}
          }
          if (page1Doc) break;
        }

        if (!page1Doc) return null;

        const docsList: Document[] = [page1Doc];

        // 최대 페이지 번호 구하기
        const getMaxPage = (doc: Document): number => {
          const endLink = doc.querySelector("div.paginationSet li.i.end a, ul.pagination li.i.end a");
          if (endLink) {
            const href = endLink.getAttribute("href") || "";
            const match = href.match(/pageIndex=(\d+)/);
            if (match) return parseInt(match[1]) || 1;
          }
          const links = doc.querySelectorAll("div.paginationSet a, ul.pagination a");
          let max = 1;
          links.forEach(a => {
            const href = a.getAttribute("href") || "";
            const match = href.match(/pageIndex=(\d+)/);
            if (match) {
              const idx = parseInt(match[1]) || 1;
              if (idx > max) max = idx;
            }
          });
          return max;
        };

        const maxPage = getMaxPage(page1Doc);
        console.log(`[SoMa Mate] ${pathSuffix} 총 발견 페이지 수: ${maxPage}`);

        if (maxPage > 1) {
          const pagesToFetch: number[] = [];
          for (let p = 2; p <= maxPage; p++) {
            pagesToFetch.push(p);
          }

          setSyncProgress(`${label} 수집 중... (0 / ${pagesToFetch.length} 페이지 완료)`);

          const fetchPageDoc = async (pageIdx: number) => {
            const url = `${matchedOrigin}${matchedCenter}/sw/mypage/${pathSuffix}${connector}pageIndex=${pageIdx}`;
            try {
              const res = await fetch(url, { credentials: "include" });
              if (res.ok) {
                const html = await res.text();
                if (!html.includes("loginForm") && !html.includes("member/user/login.do")) {
                  return new DOMParser().parseFromString(html, "text/html");
                }
              }
            } catch (e) {
              console.error(`[SoMa Mate] 페이지 ${pageIdx} fetch 실패:`, e);
            }
            return null;
          };

          const docs = await runConcurrentPool(
            pagesToFetch,
            30, // 30개 동시 요청 한도 설정 (브라우저가 HTTP/2 or HTTP/1.1 대기열 자동 조절)
            async (p) => {
              return fetchPageDoc(p);
            },
            (completed, total) => {
              setSyncProgress(`${label} 수집 중... (${completed} / ${total} 페이지 완료)`);
            }
          );

          docs.forEach(d => {
            if (d) docsList.push(d);
          });
        }

        return docsList;
      };

      const now = new Date();
      const sYear = now.getFullYear();
      const sMonth = String(now.getMonth() + 1).padStart(2, '0');

      // 1. 기본정보, 2. 개인 접수 이력, 3. 월간 일정, 4. 팀 매칭, 5. 멘토링 목록을 병렬로 동시 시작!
      setSyncProgress("포털 데이터 병렬 수집 시작...");

      const [parsedUserInfo, historyDocs, parsedSchedule, parsedTeams, mentoringDocs] = await Promise.all([
        fetchAndParse("myInfo/forUpdateMy.do?menuNo=200036", parseMyInfoPage),
        fetchAllPagesDocs("userAnswer/history.do?menuNo=200047", "개인 시간표"),
        fetchAndParse(`schedule/list.do?menuNo=200043&sYear=${sYear}&sMonth=${sMonth}`, parseCalendarResultList),
        fetchAndParse("myTeam/team.do?menuNo=200093", parseTeamPage),
        fetchAllPagesDocs("mentoLec/list.do?menuNo=200046", "멘토링/특강 목록")
      ]);

      let parsedHistory: any[] | null = null;
      if (historyDocs) {
        parsedHistory = [];
        historyDocs.forEach(doc => {
          const items = parseHistoryPage(doc);
          if (items) parsedHistory = [...(parsedHistory || []), ...items];
        });
      }

      let parsedMentorings: any[] | null = null;
      let parsedCalendarItems: any[] = [];
      if (mentoringDocs) {
        parsedMentorings = [];
        mentoringDocs.forEach(doc => {
          const mList = parseMentoringListPage(doc);
          const cItems = parseCalendarResultList(doc);
          if (mList) parsedMentorings = [...(parsedMentorings || []), ...mList];
          if (cItems) parsedCalendarItems = [...parsedCalendarItems, ...cItems];
        });
      }

      if (parsedMentorings && parsedMentorings.length > 0) {
        // 수집된 모든 멘토링 중 "접수중"인 건들만 상세 페이지를 병렬 Fetch하여 상세 필드 갱신
        const activeMentorings = parsedMentorings.filter((item: any) => item.status === "접수중" && item.url);
        const detailedMentorings = [...parsedMentorings];

        if (activeMentorings.length > 0) {
          setSyncProgress(`멘토링 상세정보 업데이트 중... (0 / ${activeMentorings.length}건 완료)`);

          const results = await runConcurrentPool(
            activeMentorings,
            20, // 20개 동시 요청 한도 설정
            async (item) => {
              let targetUrl = item.url;
              if (targetUrl.startsWith("/")) {
                targetUrl = `${origins[0]}${targetUrl}`;
              }
              try {
                const res = await fetch(targetUrl, { credentials: "include" });
                if (res.ok) {
                  const html = await res.text();
                  if (!html.includes("loginForm") && !html.includes("member/user/login.do")) {
                    const doc = new DOMParser().parseFromString(html, "text/html");
                    const detail = parseMentoringDetailPage(doc);
                    return { id: item.id, detail };
                  }
                }
              } catch (e) {
                console.warn(`[SoMa Mate] 멘토링 상세 Fetch 실패: ${targetUrl}`, e);
              }
              return null;
            },
            (completed, total) => {
              setSyncProgress(`멘토링 상세정보 업데이트 중... (${completed} / ${total}건 완료)`);
            }
          );

          results.forEach(res => {
            if (res) {
              const idx = detailedMentorings.findIndex((m: any) => m.id === res.id);
              if (idx > -1) {
                const original = detailedMentorings[idx];
                detailedMentorings[idx] = {
                  ...original,
                  location: res.detail.location || "",
                  deliveryMethod: res.detail.deliveryMethod || "",
                  isOnline: res.detail.isOnline,
                  currentParticipants: res.detail.appliedCount || original.currentParticipants,
                  maxParticipants: res.detail.totalCount || original.maxParticipants,
                  mentor_name: res.detail.author || original.author,
                  description: res.detail.title || original.title,
                };
              }
            }
          });
        }
        parsedMentorings = detailedMentorings;
      }

      const updates: any = {};
      if (parsedUserInfo && (parsedUserInfo.name || parsedUserInfo.email || parsedUserInfo.phone)) {
        updates.parsedUserInfo = parsedUserInfo;
        updates.userInfoParseTimestamp = timestamp;
        successCount++;
      }
      if (parsedHistory) {
        updates.parsedHistoryCalendar = parsedHistory;
        updates.historyCalendarParseTimestamp = timestamp;
        successCount++;
      }
      if (parsedSchedule) {
        updates.parsedSchedule = parsedSchedule;
        updates.scheduleParseTimestamp = timestamp;
        successCount++;
      }
      if (parsedTeams) {
        updates.parsedTeamInfo = parsedTeams;
        updates.teamParseTimestamp = timestamp;
        successCount++;
      }
      if (parsedMentorings) {
        updates.parsedMentorings = parsedMentorings;
        updates.mentoringParseTimestamp = timestamp;
        if (parsedCalendarItems.length > 0) {
          updates.parsedCalendarItems = parsedCalendarItems;
        }
        successCount++;
      }

      if (successCount > 0) {
        await new Promise<void>((resolve) => {
          chrome.storage.local.set(updates, () => {
            resolve();
          });
        });

        // 📡 백엔드 데이터베이스 및 ChromaDB RAG 연동 (단 1회 수행)
        setSyncProgress("백엔드 데이터베이스 동기화 중...");
        
        const formattedHistory = (parsedHistory || []).map((item: any) => ({
          source: "user_history",
          id: item.id || "",
          title: item.title || "",
          url: item.url || "",
          author: item.author || "",
          dateStr: item.dateStr || "",
          timeRangeStr: item.timeRangeStr || "",
          status: item.status || "",
          isApproved: item.isApproved || false,
        }));

        try {
          const res = await fetch(`${API_BASE}/chat`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              message: "포털 데이터 동기화를 완료했습니다.",
              session_id: sessionId,
              user_calendar: formattedHistory,
              available_mentorings: parsedMentorings || [],
              team_info: parsedTeams || [],
              user_info: parsedUserInfo || null,
            }),
          });
          if (res.ok) {
            const reader = res.body?.getReader();
            if (reader) {
              while (true) {
                const { done } = await reader.read();
                if (done) break;
              }
            }
          }
        } catch (syncErr) {
          console.error("[SoMa Mate] 백엔드 연동 동기화 실패:", syncErr);
        }
      }
    } catch (err) {
      console.error("Background sync error:", err);
    } finally {
      if (!silent) setIsLoading(false);
      setSyncProgress(null);
      refreshSyncStatus();
    }
  };

  return (
    <div className="chat-panel">
      <header className="chat-header">
        <div className="header-left">
          <div className="logo-container">
            <GraduationCap size={20} />
          </div>
          <div>
            <h1>소마 메이트</h1>
            <p>소프트웨어 마에스트로 AI 비서</p>
          </div>
        </div>
      </header>

      {/* 직관적인 텍스트 제어 콘솔 및 동기화 현황 목록 */}
      <div className="control-console">
        <div className="console-buttons">
          <button className="console-btn sync-btn" onClick={() => triggerBackgroundSync(false)} disabled={isLoading}>
            <RefreshCw size={14} className={isLoading ? "spin" : ""} />
            <span>포털 데이터 동기화</span>
          </button>
          <button className="console-btn clear-msg-btn" onClick={clearChat}>
            <RotateCcw size={14} />
            <span>대화 초기화</span>
          </button>
          <button className="console-btn clear-data-btn" onClick={clearSyncData}>
            <Trash2 size={14} />
            <span>수집 데이터 초기화</span>
          </button>
        </div>

        <div className={`sync-status-box ${isSyncStatusOpen ? "open" : "collapsed"}`}>
          <button
            className="sync-status-header"
            onClick={() => setIsSyncStatusOpen((prev) => !prev)}
            aria-expanded={isSyncStatusOpen}
          >
            <span>📡 포털 데이터 수집 현황</span>
            <span className="sync-status-summary">
              {dataCount} / 5 연동
              <ChevronDown size={14} className={isSyncStatusOpen ? "chevron open" : "chevron"} />
            </span>
          </button>
          {syncProgress && (
            <div className="sync-progress">
              <div className="sync-spinner"></div>
              <span>{syncProgress}</span>
            </div>
          )}
          {isSyncStatusOpen && (
            <div className="sync-status-content">
              <ul className="sync-status-list">
                <li>
                  <span className="label">기본정보</span>
                  <span className={`value ${syncStatus.userInfoTimestamp ? "connected" : "disconnected"}`}>
                    {syncStatus.userInfoTimestamp
                      ? `✅ 연동됨${syncStatus.userInfoName ? ` (${syncStatus.userInfoName})` : ""} ${formatTimestamp(syncStatus.userInfoTimestamp)}`
                      : "⬜ 미수집"}
                  </span>
                </li>
                <li>
                  <span className="label">멘토링/특강 목록</span>
                  <span className={`value ${syncStatus.mentoringTimestamp ? "connected" : "disconnected"}`}>
                    {syncStatus.mentoringTimestamp ? `✅ 연동됨 (${syncStatus.mentoringCount}건) ${formatTimestamp(syncStatus.mentoringTimestamp)}` : "⬜ 미수집"}
                  </span>
                </li>
                <li>
                  <span className="label">개인 시간표 (접수내역)</span>
                  <span className={`value ${syncStatus.historyCalendarTimestamp ? "connected" : "disconnected"}`}>
                    {syncStatus.historyCalendarTimestamp ? `✅ 연동됨 (${syncStatus.historyCalendarCount}건) ${formatTimestamp(syncStatus.historyCalendarTimestamp)}` : "⬜ 미수집"}
                  </span>
                </li>
                <li>
                  <span className="label">센터 월간일정 (공식)</span>
                  <span className={`value ${syncStatus.scheduleTimestamp ? "connected" : "disconnected"}`}>
                    {syncStatus.scheduleTimestamp ? `✅ 연동됨 (${syncStatus.scheduleCount}건) ${formatTimestamp(syncStatus.scheduleTimestamp)}` : "⬜ 미수집"}
                  </span>
                </li>
                <li>
                  <span className="label">소속 팀 매칭 정보</span>
                  <span className={`value ${syncStatus.teamTimestamp ? "connected" : "disconnected"}`}>
                    {syncStatus.teamTimestamp ? `✅ 연동됨 (${syncStatus.teamCount}건) ${formatTimestamp(syncStatus.teamTimestamp)}` : "⬜ 미수집"}
                  </span>
                </li>
              </ul>
              {latestTimestamp > 0 && (
                <p className="last-sync-time">
                  마지막 전체 동기화: {formatTimestamp(latestTimestamp)}
                </p>
              )}
            </div>
          )}
        </div>
      </div>

      <div className="messages-container">
        {messages.map((msg) => (
          <MessageCard
            key={msg.id}
            message={msg}
            onShowTrace={openTraceViewer}
          />
        ))}
        {messages.length === 1 && (messages[0].id === "welcome" || messages[0].id === "welcome-new") && (
          <div className="quick-actions-container">
            <p className="quick-actions-title">💡 자주 묻는 질문 샘플</p>
            <div className="quick-actions-grid">
              <button
                className="quick-action-card"
                onClick={() => setInput("우리 팀 정보를 확인하고, 이번 주에 어떤 요일/시간대에 2시간 동안 팀 회의를 진행할 수 있을지 가능한 후보 시간대를 모두 찾아서 추천해줘.")}
              >
                <div className="quick-action-icon">👥</div>
                <div className="quick-action-content">
                  <span className="action-title">이번 주 팀 회의 가능 시간 찾기</span>
                  <span className="action-desc">우리 팀원들의 일정을 파악하여 이번 주 2시간 회의 가능 시간대를 분석해 줍니다.</span>
                </div>
              </button>
              <button
                className="quick-action-card"
                onClick={() => setInput("우리 팀의 정기 회의 시간(평일 10:00 ~ 12:00)을 내 일정에서 제외한 뒤, 이번 주 나머지 빈 시간대 중에서 내 수강 이력을 바탕으로 관심사에 부합하는 신청 가능한 특강/멘토링을 골라줘.")}
              >
                <div className="quick-action-icon">💡</div>
                <div className="quick-action-content">
                  <span className="action-title">회의 제외 빈 시간 특강 추천</span>
                  <span className="action-desc">정기 회의 시간을 피해서 수강 이력 기반 관심사에 맞는 특강을 찾아 추천합니다.</span>
                </div>
              </button>
            </div>
          </div>
        )}
        {isLoading && (
          <div className="loading-indicator">
            <div className="avatar assistant">
              <Bot size={16} />
            </div>
            <div className="loading-status-box">
              <div className="processing-card">
                <div className="processing-current">
                  <div className="loading-dots">
                    <span></span>
                    <span></span>
                    <span></span>
                  </div>
                  {agentStatus && <span className="agent-status-text">{agentStatus}</span>}
                </div>
                {processingSteps.length > 0 && (
                  <ol className="processing-steps">
                    {processingSteps.map((step, idx) => (
                      <li key={`${step}-${idx}`} className={idx === processingSteps.length - 1 ? "active" : "done"}>
                        <span className="step-index">{idx + 1}</span>
                        <span>{step}</span>
                      </li>
                    ))}
                  </ol>
                )}
              </div>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      <div className="input-area">
        <textarea
          ref={inputRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="스케줄 충돌 문의나 추천 질문을 해보세요..."
          rows={2}
          disabled={isLoading}
        />
        <button
          className="send-btn"
          onClick={() => sendMessage(input)}
          disabled={!input.trim() || isLoading}
        >
          <SendHorizontal size={16} />
        </button>
      </div>
    </div>
  );
};
