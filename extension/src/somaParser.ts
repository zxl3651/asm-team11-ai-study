/**
 * SoMa Portal Content Script (somaParser.ts)
 *
 * 소마 포털(swmaestro.ai) 페이지 로드 시 DOM을 파싱하여
 * 멘토링/특강, 팀매칭, 월간일정 데이터를 chrome.storage.local에 저장한다.
 */

import {
  parseMentoringDetailPage
} from "./parserUtils";

// ── 메인 실행 로직 ────────────────────────────────────

function main() {
  const path = window.location.pathname;
  const url = window.location.href;

  console.log(`[SoMa Mate] Content Script 실행: ${path}`);

  // 1. 멘토링/특강 상세 정보 페이지 (사용자 직접 방문 시 동적 업데이트 - 머지 방식으로 기존 목록 훼손 방지)
  if (path.includes("mentoLec/view.do")) {
    const urlMatch = url.match(/qustnrSn=(\d+)/);
    if (urlMatch) {
      const id = urlMatch[1];
      const detail = parseMentoringDetailPage(document);

      console.log(`[SoMa Mate] 상세 페이지 파싱 완료: ${detail.title} (${id})`);

      chrome.storage.local.get(["parsedMentorings"], (result) => {
        const list = result.parsedMentorings || [];
        const index = list.findIndex((item: any) => item.id === id);

        const updatedItem = {
          id,
          type: (detail.title.includes("자유 멘토링") || detail.title.includes("자유멘토링")) ? "mentoring" : "lecture",
          title: detail.title,
          url: path + window.location.search,
          registrationPeriod: list[index]?.registrationPeriod || "",
          dateStr: detail.dateStr,
          timeRangeStr: detail.timeRangeStr,
          currentParticipants: detail.appliedCount,
          maxParticipants: detail.totalCount,
          isApproved: detail.isApproved,
          status: detail.appliedCount >= detail.totalCount ? "마감" : "접수중",
          author: detail.author,
          registeredDate: list[index]?.registeredDate || "",
          location: detail.location,
          deliveryMethod: detail.deliveryMethod,
          isOnline: detail.isOnline,
          description: detail.title,
        };

        if (index > -1) {
          list[index] = { ...list[index], ...updatedItem };
        } else {
          list.push(updatedItem);
        }

        chrome.storage.local.set({ parsedMentorings: list }, () => {
          chrome.runtime.sendMessage({
            type: "PARSE_COMPLETE",
            page: "detail",
            url,
            counts: { detail: 1 },
          });
        });
      });
    }
  }
}

// 페이지 로드 완료 후 실행
if (
  document.readyState === "complete" ||
  document.readyState === "interactive"
) {
  main();
} else {
  document.addEventListener("DOMContentLoaded", main);
}
