/**
 * 포털 데이터 동기화 (minsu 파이프라인 이식)
 *
 * 소마 포털(swmaestro.ai/org)의 마이페이지 여러 화면을 사용자 세션으로 fetch·파싱해
 *  - 기본정보 / 월간일정 / 팀매칭 / 멘토링·특강 목록 + 상세 + 신청자 명단
 * 을 수집하고, 백엔드 `/sync`(SQLite 정규화 + ChromaDB 벡터 인덱싱)로 전송한다.
 *
 * 위젯은 포털 페이지 위 content script 로 동작하므로 credentials:"include" fetch 로
 * 로그인 세션을 그대로 활용할 수 있다.
 */

import {
  parseMentoringListPage,
  parseCalendarResultList,
  parseTeamPage,
  parseMentoringDetailPage,
  parseMyInfoPage,
} from "../lib/parserUtils";

const API_BASE = "http://localhost:8000";

export interface SyncResult {
  ok: boolean;
  successCount: number;
  mentoringCount: number;
  teamCount: number;
  detailSuccessCount: number;
  detailFailCount: number;
  participantLinkCount: number;
  vectorCount: number;
  error?: string;
}

/** 포털 전체 동기화. onStep 으로 진행 단계를 실시간 보고한다. */
export async function runPortalSync(onStep: (msg: string) => void): Promise<SyncResult> {
  const recordSyncStep = (message: string) => onStep(message);

  try {
    const origins = ["https://www.swmaestro.ai", "https://swmaestro.org"];
    const centers = ["/busan", ""]; // 부산 센터 / 서울 본원
    let successCount = 0;

    const fetchAndParse = async (pathSuffix: string, parser: (doc: Document) => any) => {
      for (const origin of origins) {
        for (const center of centers) {
          const url = `${origin}${center}/sw/mypage/${pathSuffix}`;
          try {
            const res = await fetch(url, { credentials: "include" });
            if (res.ok) {
              const html = await res.text();
              if (html.includes("loginForm") || html.includes("member/user/login.do")) continue;
              const doc = new DOMParser().parseFromString(html, "text/html");
              const data = parser(doc);
              if (data !== null) return data;
            }
          } catch {
            /* 다음 주소 시도 */
          }
        }
      }
      return null;
    };

    // ── 컨커런트 워커 풀 ──
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
            console.error(`[SoMa Mate] pool worker error @${index}:`, e);
          } finally {
            completedCount++;
            onProgress?.(completedCount, items.length);
          }
        }
      };
      const workers = [];
      const numWorkers = Math.min(concurrency, items.length);
      for (let w = 0; w < numWorkers; w++) workers.push(worker());
      await Promise.all(workers);
      return results;
    };

    // ── 다중 페이지(페이징) 수집 ──
    const fetchAllPagesDocs = async (pathSuffix: string, label: string): Promise<Document[] | null> => {
      const connector = pathSuffix.includes("?") ? "&" : "?";
      const page1Suffix = `${pathSuffix}${connector}pageIndex=1`;
      recordSyncStep(`${label} 첫 페이지 분석 중...`);
      let page1Doc: Document | null = null;
      let matchedOrigin = "";
      let matchedCenter = "";

      for (const origin of origins) {
        for (const center of centers) {
          const url = `${origin}${center}/sw/mypage/${page1Suffix}`;
          try {
            const res = await fetch(url, { credentials: "include" });
            if (res.ok) {
              const html = await res.text();
              if (html.includes("loginForm") || html.includes("member/user/login.do")) continue;
              page1Doc = new DOMParser().parseFromString(html, "text/html");
              matchedOrigin = origin;
              matchedCenter = center;
              break;
            }
          } catch {
            /* skip */
          }
        }
        if (page1Doc) break;
      }
      if (!page1Doc) return null;

      const docsList: Document[] = [page1Doc];
      const getMaxPage = (doc: Document): number => {
        const endLink = doc.querySelector("div.paginationSet li.i.end a, ul.pagination li.i.end a");
        if (endLink) {
          const href = endLink.getAttribute("href") || "";
          const match = href.match(/pageIndex=(\d+)/);
          if (match) return parseInt(match[1]) || 1;
        }
        const links = doc.querySelectorAll("div.paginationSet a, ul.pagination a");
        let max = 1;
        links.forEach((a) => {
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
      if (maxPage > 1) {
        const pagesToFetch: number[] = [];
        for (let p = 2; p <= maxPage; p++) pagesToFetch.push(p);
        recordSyncStep(`${label} 수집 중... (0 / ${pagesToFetch.length} 페이지 완료)`);
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
        const docs = await runConcurrentPool(pagesToFetch, 30, async (p) => fetchPageDoc(p), (c, t) => {
          recordSyncStep(`${label} 수집 중... (${c} / ${t} 페이지 완료)`);
        });
        docs.forEach((d) => {
          if (d) docsList.push(d);
        });
      }
      return docsList;
    };

    const now = new Date();
    const sYear = now.getFullYear();
    const sMonth = String(now.getMonth() + 1).padStart(2, "0");

    recordSyncStep("포털 데이터 병렬 수집 시작...");
    const [parsedUserInfo, parsedSchedule, parsedTeams, mentoringDocs] = await Promise.all([
      fetchAndParse("myInfo/forUpdateMy.do?menuNo=200036", parseMyInfoPage),
      fetchAndParse(`schedule/list.do?menuNo=200043&sYear=${sYear}&sMonth=${sMonth}`, parseCalendarResultList),
      fetchAndParse("myTeam/team.do?menuNo=200093", parseTeamPage),
      fetchAllPagesDocs("mentoLec/list.do?menuNo=200046", "멘토링/특강 목록"),
    ]);

    let parsedMentorings: any[] | null = null;
    if (mentoringDocs) {
      parsedMentorings = [];
      mentoringDocs.forEach((doc) => {
        const mList = parseMentoringListPage(doc);
        if (mList) parsedMentorings = [...(parsedMentorings || []), ...mList];
      });
    }

    let detailSuccessCount = 0;
    let detailFailCount = 0;

    if (parsedMentorings && parsedMentorings.length > 0) {
      const seenDetailKeys = new Set<string>();
      const mentoringDetailTargets = parsedMentorings.filter((item: any) => {
        if (!item.url) return false;
        const key = item.id || item.url;
        if (seenDetailKeys.has(key)) return false;
        seenDetailKeys.add(key);
        return true;
      });
      const detailedMentorings = parsedMentorings.map((item: any) => ({
        ...item,
        detailStatus: item.url ? "pending" : "skipped",
      }));

      const buildDetailUrlCandidates = (item: any): string[] => {
        const url = item.url || "";
        const fallbackPath = item.id
          ? `mentoLec/view.do?menuNo=200046&qustnrSn=${encodeURIComponent(item.id)}`
          : "";
        if (/^https?:\/\//i.test(url)) return [url];
        const relativePaths = url.toLowerCase().startsWith("javascript:")
          ? [fallbackPath].filter(Boolean)
          : [url, fallbackPath].filter(Boolean);
        const candidates: string[] = [];
        for (const origin of origins) {
          for (const path of relativePaths) {
            if (path.startsWith("/")) {
              candidates.push(`${origin}${path}`);
              continue;
            }
            for (const center of centers) {
              candidates.push(`${origin}${center}/sw/mypage/${path}`);
            }
          }
        }
        return Array.from(new Set(candidates));
      };

      if (mentoringDetailTargets.length > 0) {
        recordSyncStep(`멘토링 상세정보 전체 업데이트 중... (0 / ${mentoringDetailTargets.length}건 완료)`);
        const results = await runConcurrentPool(
          mentoringDetailTargets,
          30,
          async (item) => {
            let lastError = "";
            const buildParticipantPageUrl = (baseUrl: string, pageIndex: number): string => {
              try {
                const parsed = new URL(baseUrl, window.location.origin);
                parsed.searchParams.set("pageIndex", String(pageIndex));
                return parsed.toString();
              } catch {
                const separator = baseUrl.includes("?") ? "&" : "?";
                if (baseUrl.includes("pageIndex=")) {
                  return baseUrl.replace(/([?&]pageIndex=)\d+/, `$1${pageIndex}`);
                }
                return `${baseUrl}${separator}pageIndex=${pageIndex}`;
              }
            };
            const mergeUniqueNames = (baseNames: string[], extraNames: string[]) => {
              const seen = new Set(baseNames);
              extraNames.forEach((name) => {
                if (name && !seen.has(name)) {
                  seen.add(name);
                  baseNames.push(name);
                }
              });
              return baseNames;
            };

            for (const targetUrl of buildDetailUrlCandidates(item)) {
              try {
                const res = await fetch(targetUrl, { credentials: "include" });
                if (res.ok) {
                  const html = await res.text();
                  if (!html.includes("loginForm") && !html.includes("member/user/login.do")) {
                    const doc = new DOMParser().parseFromString(html, "text/html");
                    const detail = parseMentoringDetailPage(doc);
                    const participantNames = [...(detail.participantNames || [])];
                    const pageCount = Math.min(detail.participantPageCount || 1, 100);
                    for (let page = 2; page <= pageCount; page++) {
                      const pageUrl = buildParticipantPageUrl(targetUrl, page);
                      try {
                        const pageRes = await fetch(pageUrl, { credentials: "include" });
                        if (!pageRes.ok) continue;
                        const pageHtml = await pageRes.text();
                        if (pageHtml.includes("loginForm") || pageHtml.includes("member/user/login.do")) continue;
                        const pageDoc = new DOMParser().parseFromString(pageHtml, "text/html");
                        const pageDetail = parseMentoringDetailPage(pageDoc);
                        mergeUniqueNames(participantNames, pageDetail.participantNames || []);
                      } catch (pageErr) {
                        console.warn(`[SoMa Mate] 신청자 추가 페이지 Fetch 실패: ${pageUrl}`, pageErr);
                      }
                    }
                    detail.participantNames = participantNames;
                    return { id: item.id, url: item.url, detail, status: "success", error: "" };
                  }
                  lastError = "로그인 페이지로 리다이렉트됨";
                } else {
                  lastError = `HTTP ${res.status}`;
                }
              } catch (e) {
                lastError = e instanceof Error ? e.message : String(e);
              }
            }
            return { id: item.id, url: item.url, detail: null, status: "failed", error: lastError || "상세 페이지 수집 실패" };
          },
          (completed, total) => {
            recordSyncStep(`멘토링 상세정보 전체 업데이트 중... (${completed} / ${total}건 완료)`);
          }
        );

        results.forEach((res: any) => {
          if (res && res.status === "success" && res.detail) {
            detailSuccessCount++;
            const idx = detailedMentorings.findIndex(
              (m: any) => (res.id && m.id === res.id) || m.url === res.url
            );
            if (idx > -1) {
              const original = detailedMentorings[idx];
              detailedMentorings[idx] = {
                ...original,
                location: res.detail.location || original.location || "",
                deliveryMethod: res.detail.deliveryMethod || original.deliveryMethod || "",
                isOnline: res.detail.isOnline ?? original.isOnline,
                currentParticipants: res.detail.appliedCount || original.currentParticipants,
                maxParticipants: res.detail.totalCount || original.maxParticipants,
                mentor_name: res.detail.author || original.author,
                author: res.detail.author || original.author,
                dateStr: res.detail.dateStr || original.dateStr,
                timeRangeStr: res.detail.timeRangeStr || original.timeRangeStr,
                description: res.detail.title || original.title,
                participantNames: res.detail.participantNames || original.participantNames || [],
                detailStatus: "success",
                detailError: "",
              };
            }
          } else if (res) {
            detailFailCount++;
            const idx = detailedMentorings.findIndex(
              (m: any) => (res.id && m.id === res.id) || m.url === res.url
            );
            if (idx > -1) {
              detailedMentorings[idx] = {
                ...detailedMentorings[idx],
                detailStatus: "failed",
                detailError: res.error || "상세 페이지 수집 실패",
              };
            }
          }
        });
        recordSyncStep(`멘토링 상세정보 수집 완료: 성공 ${detailSuccessCount}건 / 실패 ${detailFailCount}건`);
      }
      parsedMentorings = detailedMentorings;
    }

    if (parsedUserInfo && (parsedUserInfo.name || parsedUserInfo.email || parsedUserInfo.phone)) successCount++;
    if (parsedSchedule) successCount++;
    if (parsedTeams) successCount++;
    if (parsedMentorings) successCount++;

    let participantLinkCount = 0;
    let vectorCount = 0;

    if (successCount > 0) {
      recordSyncStep("백엔드 데이터베이스 정규화 저장 중...");
      try {
        const res = await fetch(`${API_BASE}/sync`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            user_calendar: null,
            available_mentorings: parsedMentorings || [],
            team_info: parsedTeams || [],
            user_info: parsedUserInfo || null,
          }),
        });
        if (!res.ok) throw new Error(`Backend sync failed: ${res.status}`);
        const syncResult = await res.json();
        participantLinkCount = syncResult?.details?.participant_registrations?.registration_link_count ?? 0;
        vectorCount = syncResult?.details?.vector_store?.collection_count ?? 0;
        recordSyncStep(`백엔드 정규화 완료: 신청 연결 ${participantLinkCount}건 / 벡터 ${vectorCount}건`);
      } catch (syncErr) {
        recordSyncStep("백엔드 동기화 실패");
        throw syncErr;
      }
    }

    return {
      ok: true,
      successCount,
      mentoringCount: parsedMentorings?.length || 0,
      teamCount: parsedTeams?.length || 0,
      detailSuccessCount,
      detailFailCount,
      participantLinkCount,
      vectorCount,
    };
  } catch (err) {
    return {
      ok: false,
      successCount: 0,
      mentoringCount: 0,
      teamCount: 0,
      detailSuccessCount: 0,
      detailFailCount: 0,
      participantLinkCount: 0,
      vectorCount: 0,
      error: err instanceof Error ? err.message : String(err),
    };
  }
}

/** 백엔드에 저장된 동기화 데이터 + 대화 세션 초기화. */
export async function clearSyncedData(sessionId?: string): Promise<void> {
  await fetch(`${API_BASE}/sync`, { method: "DELETE" }).catch(() => {});
  if (sessionId) {
    await fetch(`${API_BASE}/chat/${sessionId}`, { method: "DELETE" }).catch(() => {});
  }
}

/** 대화 세션만 초기화한다(동기화된 포털 데이터는 그대로 유지). */
export async function clearChatSession(sessionId: string): Promise<void> {
  await fetch(`${API_BASE}/chat/${sessionId}`, { method: "DELETE" }).catch(() => {});
}
