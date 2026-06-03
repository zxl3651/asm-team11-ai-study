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

export interface ParsedHistoryItem {
  id: string;
  title: string;
  url: string;
  author: string;
  dateStr: string;
  timeRangeStr: string;
  isApproved: boolean;
  status: string;
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

// ── 개인 접수 완료 이력 파서 ──
export function parseHistoryPage(doc: Document): ParsedHistoryItem[] {
  const rows = doc.querySelectorAll(
    "#contentsList > div > div > div.boardlist > div.tbl-ovx > table > tbody > tr"
  );
  const results: ParsedHistoryItem[] = [];

  rows.forEach((row, index) => {
    try {
      const tds = row.querySelectorAll("td");
      if (tds.length < 8) return;

      const appliedText = (tds[6]?.textContent || "").replace(/\s+/g, " ").trim();

      const aLink = tds[2]?.querySelector("a");
      const url = aLink ? (aLink.getAttribute("href") || "") : "";
      const title = (tds[2]?.textContent || "").trim();
      const author = (tds[3]?.textContent || "").trim();

      const dateTimeText = (tds[4]?.textContent || "").replace(/\u00a0/g, " ");
      const dateTimeParts = dateTimeText
        .split("\n")
        .map((s) => s.trim())
        .filter(Boolean);
      const dateStr = dateTimeParts[0] || "";
      const timeRangeStr = dateTimeParts.slice(1).join(" ").trim();

      const isApproved = (tds[7]?.textContent || "").trim().toUpperCase() === "OK";

      let id = "";
      if (url) {
        const urlMatch = url.match(/qustnrSn=(\d+)/);
        if (urlMatch) id = urlMatch[1];
      }
      if (!id) id = `hist_${index}`;

      results.push({
        id,
        title,
        url,
        author,
        dateStr,
        timeRangeStr,
        isApproved,
        status: appliedText,
      });
    } catch (e) {
      console.warn("[SoMa Mate] 접수 이력 행 파싱 실패:", e);
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

export function parseMentoringDetailPage(doc: Document): MentoringDetail {
  const capacityText = getTopValue(doc, "모집인원");
  const approvedText = getTopValue(doc, "개설 승인");
  const appliedSummary =
    doc.querySelector(".total-normal.mt50")
      ?.textContent?.replace(/\s+/g, " ")
      .trim() || "";
  const deliveryMethod = getTopValue(doc, "진행방식") || "";
  const timeStr = getTopValue(doc, "강의날짜");

  return {
    title: getTopValue(doc, "모집 명") || "",
    author: getTopValue(doc, "작성자") || "",
    location: getTopValue(doc, "장소") || "",
    deliveryMethod,
    isOnline: deliveryMethod.includes("온라인"),
    timeStr: timeStr || "",
    ...getDetailTimeFields(timeStr),
    appliedCount: getAppliedCount(appliedSummary),
    totalCount: getPeopleCount(capacityText),
    isApproved: approvedText === "OK",
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
