/**
 * shared parser utilities (parserUtils.ts)
 */

export interface ParsedMentoring {
  id: string;
  type: "mentoring" | "lecture";
  title: string;
  url: string;
  registrationPeriod: string;
  dateStr: string;
  timeRangeStr: string;
  currentParticipants: number;
  maxParticipants: number;
  isApproved: boolean;
  status: string;
  author: string;
  registeredDate: string;
}

export interface ParsedCalendarItem {
  subjectTitle: string;
  subject: string;
  date: string;
  url: string;
  category: string;
  categoryNm: string;
}

export interface ParsedTeam {
  no: number;
  teamName: string;
  leader: string;
  members: string[];
  mentorName: string;
  projectName: string;
  ictCategoryLarge: string;
  ictCategoryMedium: string;
}


// ── 멘토링/특강 게시판 파서 ──
export function parseMentoringListPage(doc: Document): ParsedMentoring[] {
  const rows = doc.querySelectorAll(
    "#listFrm > div.boardlist.mt50 > table > tbody > tr"
  );
  const results: ParsedMentoring[] = [];

  rows.forEach((row) => {
    try {
      const tds = row.querySelectorAll("td");
      if (tds.length < 2) return;

      const titleTd = row.querySelector("td.tit");
      if (!titleTd) return;

      const titleLink = titleTd.querySelector("a[href*='mentoLec/view.do']");
      if (!titleLink) return;

      const rawTitle = (titleLink.textContent || "").trim();
      const url = titleLink.getAttribute("href") || "";

      let type: "mentoring" | "lecture" = "lecture";
      if (rawTitle.includes("자유 멘토링") || rawTitle.includes("자유멘토링")) {
        type = "mentoring";
      }

      const statusEl =
        titleTd.querySelector(".ab") ||
        titleTd.querySelector("strong.color-red");
      let status = "알수없음";
      if (statusEl) {
        const statusText = (statusEl.textContent || "").trim();
        if (statusText.includes("접수중")) status = "접수중";
        else if (statusText.includes("마감")) status = "마감";
        else status = statusText.replace(/[\[\]]/g, "");
      }

      const pcTds = row.querySelectorAll("td.pc_only");
      if (pcTds.length < 8) return;

      const no = (pcTds[0]?.textContent || "").trim();
      const regPeriodText = (pcTds[1]?.textContent || "").replace(/\s+/g, " ").trim();

      const dateTimeText = (pcTds[2]?.textContent || "").replace(/\u00a0/g, " ");
      const dateTimeParts = dateTimeText
        .split("\n")
        .map((s) => s.trim())
        .filter(Boolean);
      const dateStr = dateTimeParts[0] || "";
      const timeRangeStr = dateTimeParts
        .slice(1)
        .join(" ")
        .replace(/\s+/g, " ")
        .trim();

      const capacityText = (pcTds[3]?.textContent || "").replace(/\s+/g, "").trim();
      const capacityParts = capacityText.split("/");
      const currentParticipants = parseInt(capacityParts[0]) || 0;
      const maxParticipants = parseInt(capacityParts[1]) || 0;

      const approvedText = (pcTds[4]?.textContent || "").trim();
      const isApproved = approvedText === "OK";

      const statusTdText = (pcTds[5]?.textContent || "").trim();
      if (statusTdText.includes("접수중")) status = "접수중";
      else if (statusTdText.includes("마감")) status = "마감";

      const author = (pcTds[6]?.textContent || "").trim();
      const registeredDate = (pcTds[7]?.textContent || "").trim();

      let id = no;
      const urlMatch = url.match(/qustnrSn=(\d+)/);
      if (urlMatch) id = urlMatch[1];

      results.push({
        id,
        type,
        title: rawTitle,
        url,
        registrationPeriod: regPeriodText,
        dateStr,
        timeRangeStr,
        currentParticipants,
        maxParticipants,
        isApproved,
        status,
        author,
        registeredDate,
      });
    } catch (e) {
      console.warn("[SoMa Mate] 멘토링 행 파싱 실패:", e);
    }
  });

  return results;
}

// ── 캘린더 resultList 파서 (공지 및 멘토링 캘린더 공통) ──
export function parseCalendarResultList(doc: Document): ParsedCalendarItem[] {
  const scripts = Array.from(doc.querySelectorAll("script"));
  const items: ParsedCalendarItem[] = [];

  const parseObjectLiteralRegex = (objStr: string) => {
    const getFieldVal = (field: string) => {
      const r = new RegExp("['\"]?" + field + "['\"]?\\s*:\\s*['\"]?([^'\"\\r\\n]+)['\"]?");
      const m = objStr.match(r);
      if (!m) return "";
      let val = m[1].trim();
      if (val.startsWith('"') || val.startsWith("'")) {
        val = val.substring(1);
      }
      if (val.endsWith('"') || val.endsWith("'") || val.endsWith(",")) {
        val = val.replace(/['\",\s}]+$/, "");
      }
      return val;
    };

    const subjectTitle = getFieldVal("subjectTitle");
    const subject = getFieldVal("subject");
    const date = getFieldVal("date") || getFieldVal("ntceBgnde");
    const url = getFieldVal("url");
    const category = getFieldVal("category");
    const categoryNm = getFieldVal("categoryNm");

    return { subjectTitle, subject, date, url, category, categoryNm };
  };

  for (const script of scripts) {
    const text = script.textContent || "";
    if (!text.includes("resultList.push")) continue;

    const pushRegex = /resultList\.push\s*\(\s*(\{[\s\S]*?\})\s*\)/g;
    let match: RegExpExecArray | null;

    while ((match = pushRegex.exec(text)) !== null) {
      try {
        const parsed = parseObjectLiteralRegex(match[1]);
        const eventDate = parsed.date;

        if (parsed && parsed.subjectTitle && eventDate) {
          items.push({
            subjectTitle: parsed.subjectTitle || "",
            subject: parsed.subject || "",
            date: eventDate,
            url: parsed.url || "",
            category: parsed.category || "",
            categoryNm: parsed.categoryNm || "",
          });
        }
      } catch (e) {
        console.warn("[SoMa Mate] resultList 항목 파싱 실패:", e);
      }
    }
  }

  return items;
}

// ── 팀매칭 정보 파서 ──
export function parseTeamPage(doc: Document): ParsedTeam[] {
  const rows = doc.querySelectorAll(
    "table.tbl-st1_sui.t.team > tbody > tr"
  );
  const results: ParsedTeam[] = [];

  rows.forEach((row, index) => {
    try {
      const tds = row.querySelectorAll("td");
      if (tds.length < 5) return;

      const noTd = row.querySelector("td.pc_only");
      const no = parseInt(noTd?.textContent?.trim() || "0") || index + 1;

      const teamNameTd = row.querySelector("td.popuser");
      const teamNameLink = teamNameTd?.querySelector("a");
      const teamName = (teamNameLink?.textContent || "").trim();

      const pcOnlyTds = row.querySelectorAll("td.pc_only");
      let leader = "";
      if (pcOnlyTds.length >= 2) {
        const leaderLink = pcOnlyTds[1]?.querySelector("a.sui");
        leader = (leaderLink?.textContent || "").trim();
      }

      const popuserTds = row.querySelectorAll("td.popuser");
      const members: string[] = [];
      if (popuserTds.length >= 2) {
        const memberLinks = popuserTds[1]?.querySelectorAll("a.sui") || [];
        memberLinks.forEach((link) => {
          const name = (link.textContent || "").trim();
          if (name) members.push(name);
        });
      }

      let mentorName = "";
      if (popuserTds.length >= 3) {
        const mentorLink = popuserTds[2]?.querySelector("a.sui");
        mentorName = (mentorLink?.textContent || "").trim();
      }

      let projectName = "";
      let ictLarge = "";
      let ictMedium = "";
      if (pcOnlyTds.length >= 5) {
        projectName = (pcOnlyTds[2]?.textContent || "").trim();
        ictLarge = (pcOnlyTds[3]?.textContent || "").trim();
        ictMedium = (pcOnlyTds[4]?.textContent || "").trim();
      }

      if (teamName) {
        results.push({
          no,
          teamName,
          leader,
          members,
          mentorName,
          projectName,
          ictCategoryLarge: ictLarge,
          ictCategoryMedium: ictMedium,
        });
      }
    } catch (e) {
      console.warn("[SoMa Mate] 팀 행 파싱 실패:", e);
    }
  });

  // 2. 다른 팀 목록 파싱 (ul.bbs-team > li)
  const listItems = doc.querySelectorAll("ul.bbs-team > li");
  listItems.forEach((li) => {
    try {
      const teamNameLink = li.querySelector("div.top strong.t a");
      if (!teamNameLink) return;
      const teamName = (teamNameLink.textContent || "").trim();
      if (!teamName) return;

      // 이미 테이블에서 파싱한 팀이면 스킵 (중복 방지)
      if (results.some(t => t.teamName === teamName)) return;

      const projNameEl = li.querySelector("div.top span.add-txt");
      const projectName = (projNameEl?.textContent || "").trim();

      let leader = "";
      let members: string[] = [];
      let mentorName = "";

      const infoLis = li.querySelectorAll("div.top ul.info > li");
      infoLis.forEach((infoLi) => {
        const strongText = infoLi.querySelector("strong")?.textContent || "";
        if (strongText.includes("팀장")) {
          const spanEl = infoLi.querySelector("span");
          leader = (spanEl?.textContent || infoLi.textContent || "").replace("팀장 :", "").trim();
        } else if (strongText.includes("팀원")) {
          const memberLinks = infoLi.querySelectorAll("span a");
          memberLinks.forEach((link) => {
            const name = (link.textContent || "").trim();
            if (name) members.push(name);
          });
          if (members.length === 0) {
            const txt = (infoLi.textContent || "").replace("팀원 :", "").trim();
            members = txt.split(",").map(n => n.trim()).filter(Boolean);
          }
        } else if (strongText.includes("멘토")) {
          const mentorLink = infoLi.querySelector("span a");
          mentorName = (mentorLink?.textContent || infoLi.querySelector("span")?.textContent || "").trim();
          if (!mentorName) {
            mentorName = (infoLi.textContent || "").replace("멘토 :", "").trim();
          }
        }
      });

      let ictLarge = "";
      let ictMedium = "";
      const ictLis = li.querySelectorAll("div.bot ul.ict > li");
      ictLis.forEach((ictLi) => {
        const text = ictLi.textContent || "";
        if (text.includes("ICT기술분류(대)")) {
          ictLarge = text.replace("ICT기술분류(대) :", "").trim();
        } else if (text.includes("ICT기술분류(중)")) {
          ictMedium = text.replace("ICT기술분류(중) :", "").trim();
        }
      });

      results.push({
        no: results.length + 1,
        teamName,
        leader,
        members,
        mentorName,
        projectName,
        ictCategoryLarge: ictLarge,
        ictCategoryMedium: ictMedium,
      });
    } catch (e) {
      console.warn("[SoMa Mate] 다른 팀 리스트 항목 파싱 실패:", e);
    }
  });

  return results;
}

// ── 멘토링/특강 상세 정보 파서 ──
export interface MentoringDetail {
  title: string;
  author: string;
  location: string;
  deliveryMethod: string;
  isOnline: boolean;
  timeStr: string;
  dateStr: string;
  timeRangeStr: string;
  appliedCount: number;
  totalCount: number;
  isApproved: boolean;
  participantNames: string[];
  participantPageCount: number;
}

function getTopValue(container: Document | HTMLElement, label: string): string | null {
  const groups = Array.from(container.querySelectorAll("div.top .group"));
  const group = groups.find(
    (item) => (item.querySelector(".t")?.textContent || "").trim() === label
  );
  return (
    group?.querySelector(".c")?.textContent?.replace(/\s+/g, " ").trim() || null
  );
}

function getPeopleCount(text: string | null): number {
  if (!text) return 0;
  const match = text.match(/(\d+)\s*명/) || text.match(/(\d+)/);
  return match ? parseInt(match[1]) : 0;
}

function getAppliedCount(text: string | null): number {
  if (!text) return 0;
  const match = text.match(/\[(\d+)\s*명\]/) || text.match(/(\d+)\s*명/) || text.match(/(\d+)/);
  return match ? parseInt(match[1]) : 0;
}

function getDetailTimeFields(timeStr: string | null): { dateStr: string; timeRangeStr: string } {
  if (!timeStr) return { dateStr: "", timeRangeStr: "" };

  const dateMatch = timeStr.match(/(\d{4})\D+(\d{1,2})\D+(\d{1,2})/);
  if (!dateMatch) return { dateStr: "", timeRangeStr: "" };

  const [, year, month, day] = dateMatch;
  const timeText = timeStr.slice(dateMatch.index! + dateMatch[0].length);
  const timeMatches = Array.from(timeText.matchAll(/(\d{1,2})(?::(\d{2}))?\s*시?/g));
  if (timeMatches.length < 2) return { dateStr: "", timeRangeStr: "" };

  const formatTime = (match: RegExpMatchArray | any) => {
    const hour = match[1];
    const minute = match[2] || "00";
    return `${hour.padStart(2, "0")}:${minute.padStart(2, "0")}`;
  };
  const weekdayMatch = timeStr.match(/\([^)]+\)/);
  const weekday = weekdayMatch ? weekdayMatch[0] : "";

  return {
    dateStr: `${year}-${month.padStart(2, "0")}-${day.padStart(2, "0")}${weekday}`,
    timeRangeStr: `${formatTime(timeMatches[0])} ~ ${formatTime(timeMatches[1])}`,
  };
}

function extractParticipantNames(doc: Document, maxExpectedCount: number): string[] {
  const keywords = ["신청자", "참여자", "접수자", "신청 연수생", "참여 연수생", "신청현황", "참여현황", "수강생"];
  const excluded = new Set([
    "작성자", "모집인원", "개설 승인", "진행방식", "강의날짜", "장소", "모집 명",
    "신청", "취소", "상태", "승인", "이름", "소속", "연수생", "멘토",
    "신청완료", "접수완료", "승인완료", "취소완료", "신청취소", "미승인",
    "로그아웃", "공지사항", "등록일", "마이페이지", "멘토링", "특강", "접수내역",
    "모집안내", "링크드인", "교육과정", "연수센터", "전체메뉴",
    "목록", "블로그", "사업소개", "소마기술력", "소마사람들", "안녕하세요",
    "알림마당", "연혁", "월간일정", "유튜브", "이용약관", "인스타그램",
    "주요성과", "참여후기", "창업기업", "팀매칭", "페이스북", "회원정보", "거짓",
  ]);
  const namePattern = /^[가-힣]{2,5}$/;
  const names = new Set<string>();

  const addName = (value: string | null | undefined) => {
    const cleanValue = (value || "")
      .replace(/^(이름|성명|신청자|참여자|연수생|멘토)\s*[:：]\s*/, "")
      .replace(/\s+/g, " ")
      .trim();
    if (!cleanValue || excluded.has(cleanValue)) return;
    if (namePattern.test(cleanValue)) {
      names.add(cleanValue);
    }
  };

  const addNamesFromText = (value: string | null | undefined) => {
    const text = (value || "").replace(/\s+/g, " ").trim();
    if (!text) return;
    text
      .split(/[,/·|()\[\]{}<>\s]+/)
      .map((part) => part.trim())
      .filter(Boolean)
      .forEach(addName);
  };

  const isReasonableContainer = (el: Element) => {
      const text = (el.textContent || "").replace(/\s+/g, " ").trim();
      if (text.length > 5000) return false;
      return true;
  };

  const candidateContainers = Array.from(doc.querySelectorAll("table, tbody, ul, ol, .boardlist, .tbl-ovx"))
    .filter((el) => {
      if (!isReasonableContainer(el)) return false;
      const text = (el.textContent || "").replace(/\s+/g, " ").trim();
      const hasKeyword = keywords.some((keyword) => text.includes(keyword));
      const hasNameHeader = Array.from(el.querySelectorAll("th, td, dt, strong, span")).some((cell) => {
        const cellText = (cell.textContent || "").replace(/\s+/g, " ").trim();
        return ["이름", "성명", "신청자", "참여자", "연수생"].some((keyword) => cellText === keyword || cellText.includes(keyword));
      });
      return hasKeyword || hasNameHeader;
    });

  const scopedContainers: Element[] = [];
  const addScopedContainer = (el: Element | null) => {
    if (!el || !isReasonableContainer(el)) return;
    if (!scopedContainers.includes(el)) scopedContainers.push(el);
  };

  const appliedSummaryEl = doc.querySelector(".total-normal.mt50");
  if (appliedSummaryEl) {
    let sibling = appliedSummaryEl.nextElementSibling;
    let scanned = 0;
    while (sibling && scanned < 6) {
      if (sibling.matches("table, tbody, ul, ol, .boardlist, .tbl-ovx")) {
        addScopedContainer(sibling);
      }
      sibling.querySelectorAll?.("table, tbody, ul, ol, .boardlist, .tbl-ovx").forEach(addScopedContainer);
      sibling = sibling.nextElementSibling;
      scanned++;
    }

    const parent = appliedSummaryEl.parentElement;
    if (parent) {
      parent.querySelectorAll("table, tbody, ul, ol, .boardlist, .tbl-ovx").forEach(addScopedContainer);
    }
  }

  scopedContainers.forEach((container) => {
    if (!candidateContainers.includes(container)) {
      candidateContainers.push(container);
    }
  });

  for (const container of candidateContainers) {
    const tables = container.matches("table")
      ? [container]
      : Array.from(container.querySelectorAll("table"));
    tables.forEach((table) => {
      const headers = Array.from(table.querySelectorAll("thead th"));
      const traineeIndex = headers.findIndex((header) => {
        const text = (header.textContent || "").replace(/\s+/g, " ").trim();
        return ["연수생", "이름", "성명", "신청자", "참여자"].some((keyword) => text === keyword || text.includes(keyword));
      });
      if (traineeIndex < 0) return;

      table.querySelectorAll("tbody tr").forEach((row) => {
        const cells = Array.from(row.querySelectorAll("td"));
        const nameCell = cells[traineeIndex];
        if (!nameCell) return;
        addName(nameCell.querySelector("a")?.textContent || nameCell.textContent);
      });
    });

    container.querySelectorAll("a.sui, a[href*='user'], a[href*='member'], a[href*='popuser'], a[href^='javascript: popuser'], td.popuser a, span.name, td.name, strong.name").forEach((el) => {
      addName(el.textContent);
    });

    container.querySelectorAll("td, span.name, strong.name").forEach((el) => {
      const text = (el.textContent || "").replace(/\s+/g, " ").trim();
      addNamesFromText(text);
    });

    container.querySelectorAll("tr").forEach((row) => {
      const cells = Array.from(row.querySelectorAll("th, td"));
      if (cells.length === 0) return;
      const rowText = (row.textContent || "").replace(/\s+/g, " ").trim();
      if (rowText.length > 600) return;

      const table = row.closest("table");
      const headers = table ? Array.from(table.querySelectorAll("thead th")) : [];
      const traineeIndex = headers.findIndex((header) => {
        const text = (header.textContent || "").replace(/\s+/g, " ").trim();
        return ["연수생", "이름", "성명", "신청자", "참여자"].some((keyword) => text === keyword || text.includes(keyword));
      });
      if (traineeIndex >= 0 && cells[traineeIndex]) {
        addName(cells[traineeIndex].querySelector("a")?.textContent || cells[traineeIndex].textContent);
        return;
      }

      const labelIndex = cells.findIndex((cell) => {
        const text = (cell.textContent || "").replace(/\s+/g, " ").trim();
        return ["이름", "성명", "신청자", "참여자", "연수생"].some((keyword) => text === keyword || text.includes(keyword));
      });
      if (labelIndex >= 0 && cells[labelIndex + 1]) {
        addNamesFromText(cells[labelIndex + 1].textContent);
      } else {
        cells.forEach((cell) => addNamesFromText(cell.textContent));
      }
    });
  }

  const result = Array.from(names);
  if (maxExpectedCount > 0 && result.length > maxExpectedCount + 5) {
    console.warn(
      `[SoMa Mate] 신청자 명단 파싱 결과가 정원 대비 과도해 무시합니다. expected=${maxExpectedCount}, parsed=${result.length}`,
      result
    );
    return [];
  }
  return result;
}

export function parseMentoringDetailPage(doc: Document): MentoringDetail {
  const capacityText = getTopValue(doc, "모집인원");
  const approvedText = getTopValue(doc, "개설 승인");
  const appliedSummary =
    doc.querySelector(".total-normal.mt50")
      ?.textContent?.replace(/\s+/g, " ")
      .trim() || "";
  const deliveryMethod = getTopValue(doc, "진행방식") || "";
  const timeStr = getTopValue(doc, "강의날짜");
  const appliedCount = getAppliedCount(appliedSummary);
  const totalCount = getPeopleCount(capacityText);
  const participantPageCount = (() => {
    const appliedSummaryEl = doc.querySelector(".total-normal.mt50");
    const scope = appliedSummaryEl?.nextElementSibling || doc;
    const endPageAttr = scope.querySelector("a[data-endpage]")?.getAttribute("data-endpage");
    if (endPageAttr) {
      const parsed = parseInt(endPageAttr, 10);
      if (parsed > 0) return parsed;
    }

    let maxPage = 1;
    scope.querySelectorAll("a[href*='pageIndex=']").forEach((link) => {
      const href = link.getAttribute("href") || "";
      const match = href.match(/pageIndex=(\d+)/);
      if (!match) return;
      const page = parseInt(match[1], 10) || 1;
      if (page > maxPage) maxPage = page;
    });
    return maxPage;
  })();

  return {
    title: getTopValue(doc, "모집 명") || "",
    author: getTopValue(doc, "작성자") || "",
    location: getTopValue(doc, "장소") || "",
    deliveryMethod,
    isOnline: deliveryMethod.includes("온라인"),
    timeStr: timeStr || "",
    ...getDetailTimeFields(timeStr),
    appliedCount,
    totalCount,
    isApproved: approvedText === "OK",
    participantNames: extractParticipantNames(doc, Math.max(appliedCount, totalCount)),
    participantPageCount,
  };
}

export interface ParsedMyInfo {
  name: string;
  email: string;
  phone: string;
  role: string;
  techStacks: string[];
}

export function parseMyInfoPage(doc: Document): ParsedMyInfo {
  let name = "";
  let email = "";
  let phone = "";
  let role = "연수생";
  const techStacks: string[] = [];

  const clean = (value: string | null | undefined) =>
    (value || "").replace(/\s+/g, " ").trim();

  const getControlValue = (el: Element | null): string => {
    if (!el) return "";
    if (el instanceof HTMLSelectElement) {
      return clean(el.selectedOptions[0]?.textContent || el.value);
    }
    if (el instanceof HTMLTextAreaElement) {
      return clean(el.value);
    }
    if (el instanceof HTMLInputElement) {
      if ((el.type === "checkbox" || el.type === "radio") && !el.checked) return "";
      const label = el.id ? doc.querySelector(`label[for='${el.id}']`) : null;
      return clean(label?.textContent || el.value);
    }
    return clean(el.textContent);
  };

  const getInputValueByNames = (patterns: string[]): string => {
    const controls = Array.from(doc.querySelectorAll("input, select, textarea"));
    const found = controls.find((control) => {
      const nameAttr = (control.getAttribute("name") || "").toLowerCase();
      const idAttr = (control.getAttribute("id") || "").toLowerCase();
      return patterns.some((pattern) => {
        const lower = pattern.toLowerCase();
        return nameAttr.includes(lower) || idAttr.includes(lower);
      });
    });
    return getControlValue(found || null);
  };

  name = getInputValueByNames(["userNm", "mberNm", "memberNm", "name", "korNm", "applcntNm"]);
  email = getInputValueByNames(["email", "emailAddr", "emailAdres", "mail"]);
  phone = getInputValueByNames(["mbtlnum", "moblphon", "mobile", "phone", "tel", "hp"]);

  const ths = Array.from(doc.querySelectorAll("table th, label, td.tit, dt"));
  ths.forEach((th) => {
    const text = clean(th.textContent);
    const td =
      th.nextElementSibling ||
      (th.parentElement ? Array.from(th.parentElement.children).find((child) => child !== th && ["TD", "DD"].includes(child.tagName)) : null);
    if (!td) return;

    const input = td.querySelector("input, select, textarea");
    const value = input ? getControlValue(input) : clean(td.textContent);

    if (text.includes("이름") || text.includes("성명")) {
      if (!name) name = value;
    } else if (text.includes("이메일") || text.includes("이메일 주소")) {
      if (!email) email = value;
    } else if (text.includes("휴대폰") || text.includes("전화번호") || text.includes("연락처")) {
      if (!phone) phone = value;
    } else if (text.includes("구분") || text.includes("역할")) {
      role = value;
    } else if (text.includes("기술") || text.includes("스택") || text.includes("관심")) {
      const checkedBoxes = Array.from(td.querySelectorAll("input[type='checkbox']:checked, input[type='radio']:checked"));
      if (checkedBoxes.length > 0) {
        checkedBoxes.forEach((cb: any) => {
          const lbl = doc.querySelector(`label[for='${cb.id}']`);
          const labelText = lbl ? clean(lbl.textContent) : clean(cb.value);
          if (labelText) techStacks.push(labelText);
        });
      } else if (value) {
        value.split(/[,/·]/).forEach((s) => {
          const trimmed = s.trim();
          if (trimmed) techStacks.push(trimmed);
        });
      }
    }
  });

  if (!email) {
    const emails = clean(doc.body.textContent).match(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/i);
    if (emails) email = emails[0];
  }

  if (!phone) {
    const phones = clean(doc.body.textContent).match(/01[016789][-\s.]?\d{3,4}[-\s.]?\d{4}/);
    if (phones) phone = phones[0];
  }

  if (!name) {
    const nameTd = doc.querySelector("td.name, td#name, td.userNm, td.mberNm, span.name, strong.name");
    if (nameTd) name = clean(nameTd.textContent);
  }

  return {
    name,
    email,
    phone,
    role,
    techStacks: Array.from(new Set(techStacks.map(clean).filter(Boolean))),
  };
}
