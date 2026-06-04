// 접수중 특강/멘토링 실시간 파싱.
//
// 로그인 필요한 SWM 포털 게시판(mentoLec/list.do)을 content script 가
// same-origin 세션으로 fetch 해 표를 파싱한다. searchStatMentolec=A 는 '접수중' 필터.
// 페이지당 10건이라 Total 만큼 페이지를 돌며 모은다.

const LIST_URL =
  "https://www.swmaestro.ai/busan/sw/mypage/mentoLec/list.do" +
  "?menuNo=200046&searchStatMentolec=A&pageIndex=";

export interface SessionItem {
  type: string; // "특강" | "멘토링"
  title: string;
  mentor: string;
  reg_period: string;
  event_date: string;
  applied: number;
  capacity: number;
  status: string;
}

export async function fetchOpenSessions(): Promise<SessionItem[]> {
  const items: SessionItem[] = [];
  let total = Infinity;

  for (let p = 1; p <= 20; p++) {
    let html: string;
    try {
      const res = await fetch(LIST_URL + p, { credentials: "include" });
      if (!res.ok) break;
      html = await res.text();
    } catch {
      break;
    }

    const doc = new DOMParser().parseFromString(html, "text/html");
    const totalMatch = (doc.body.textContent || "").match(/Total\s*:\s*([\d,]+)/);
    if (totalMatch) total = parseInt(totalMatch[1].replace(/,/g, ""), 10);

    const table = [...doc.querySelectorAll("table")].find((t) =>
      /접수기간/.test(t.textContent || "")
    );
    const rows = table ? [...table.querySelectorAll("tbody tr")] : [];
    if (!rows.length) break;

    for (const row of rows) {
      const cells = [...(row as HTMLTableRowElement).cells].map((c) =>
        (c.textContent || "").replace(/\s+/g, " ").trim()
      );
      if (cells.length < 8) continue;

      let title = cells[1].split("[접수중]")[0].trim();
      const type = /멘토 특강/.test(title) ? "특강" : "멘토링";
      title = title.replace(/^\[[^\]]+\]\s*/, "").trim(); // 앞 [멘토 특강] 태그 제거
      const cap = cells[4].match(/(\d+)\s*\/\s*(\d+)/);

      items.push({
        type,
        title,
        mentor: cells[7],
        reg_period: cells[2],
        event_date: cells[3],
        applied: cap ? Number(cap[1]) : 0,
        capacity: cap ? Number(cap[2]) : 0,
        status: "접수중",
      });
    }

    if (items.length >= total) break;
  }

  return items;
}
