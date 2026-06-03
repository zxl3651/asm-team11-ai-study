/**
 * SoMa Portal Content Script (somaParser.ts)
 *
 * 소마 포털(swmaestro.ai) 페이지 로드 시 DOM을 파싱하여
 * 멘토링/특강, 팀매칭, 월간일정 데이터를 chrome.storage.local에 저장한다.
 */

import {
  parseMentoringListPage,
  parseCalendarResultList,
  parseTeamPage,
  parseHistoryPage,
  parseMentoringDetailPage
} from "./parserUtils";

// ── 해시 유틸리티 ─────────────────────────────────────
// djb2 해시: 빠르고 가벼운 문자열 해시 (변경 감지 용도)
function computeHash(str: string): string {
  let hash = 5381;
  for (let i = 0; i < str.length; i++) {
    hash = ((hash << 5) + hash + str.charCodeAt(i)) & 0xffffffff;
  }
  return hash.toString(36);
}

function getContentHash(doc: Document, pageType: string): string {
  let contentToHash = "";

  switch (pageType) {
    case "mentoring": {
      const tbody = doc.querySelector(
        "#listFrm > div.boardlist.mt50 > table > tbody"
      );
      contentToHash += tbody?.innerHTML || "";

      const scripts = Array.from(doc.querySelectorAll("script"));
      for (const s of scripts) {
        const text = s.textContent || "";
        if (text.includes("resultList.push")) {
          contentToHash += text;
          break;
        }
      }
      break;
    }
    case "team": {
      const tbody = doc.querySelector(
        "table.tbl-st1_sui.t.team > tbody"
      );
      contentToHash += tbody?.innerHTML || "";
      break;
    }
    case "schedule": {
      const scripts = Array.from(doc.querySelectorAll("script"));
      for (const s of scripts) {
        const text = s.textContent || "";
        if (text.includes("resultList.push")) {
          contentToHash += text;
          break;
        }
      }
      break;
    }
    case "history": {
      const tbody = doc.querySelector(
        "#contentsList > div > div > div.boardlist > div.tbl-ovx > table > tbody"
      );
      contentToHash += tbody?.innerHTML || "";
      break;
    }
  }

  contentToHash = contentToHash.replace(/\s+/g, " ").trim();
  return computeHash(contentToHash);
}

function checkHashAndParse(
  pageType: string,
  currentHash: string,
  parseAndSave: () => void
): void {
  const hashKey = `${pageType}_contentHash`;

  chrome.storage.local.get([hashKey], (result) => {
    const savedHash = result[hashKey];

    if (savedHash === currentHash) {
      console.log(
        `[SoMa Mate] ${pageType} 페이지 내용 변경 없음 (hash: ${currentHash}). 파싱 스킵.`
      );
      chrome.runtime.sendMessage({
        type: "PARSE_SKIPPED",
        page: pageType,
        reason: "no_change",
      });
      return;
    }

    console.log(
      `[SoMa Mate] ${pageType} 페이지 내용 변경 감지 (old: ${savedHash || "없음"} → new: ${currentHash}). 파싱 실행.`
    );

    chrome.storage.local.set({ [hashKey]: currentHash }, () => {
      parseAndSave();
    });
  });
}

// ── 메인 실행 로직 ────────────────────────────────────

function main() {
  const path = window.location.pathname;
  const url = window.location.href;
  const timestamp = Date.now();

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
          type: detail.deliveryMethod.includes("자유") ? "mentoring" : "lecture",
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
