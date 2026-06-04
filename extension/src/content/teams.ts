// 팀매칭 현황 실시간 파싱.
//
// 로그인 필요한 SWM 포털 팀매칭 페이지(myTeam/team.do)를 content script 가
// same-origin 세션으로 fetch 해 파싱한다. 데이터가 <table>이 아니라 div 카드라,
// '팀장/팀원/멘토/ICT기술분류' 라벨을 모두 가진 최소 블록을 한 팀 단위로 본다.

const TEAM_URL = "https://www.swmaestro.ai/busan/sw/mypage/myTeam/team.do?menuNo=200093";

export interface TeamItem {
  team: string;
  leader: string;
  members: string[];
  mentor: string;
}

function segment(text: string, start: RegExp, end: RegExp): string[] {
  const i = text.search(start);
  if (i < 0) return [];
  const after = text.slice(i).replace(start, "");
  const j = after.search(end);
  return (j < 0 ? after : after.slice(0, j))
    .split("\n")
    .map((x) => x.trim())
    .filter(Boolean);
}

export async function fetchTeams(): Promise<TeamItem[]> {
  let html: string;
  try {
    const res = await fetch(TEAM_URL, { credentials: "include" });
    if (!res.ok) return [];
    html = await res.text();
  } catch {
    return [];
  }

  const doc = new DOMParser().parseFromString(html, "text/html");
  let cards = [...doc.querySelectorAll("div,li,article,section")].filter((el) => {
    const t = el.textContent || "";
    return /팀장/.test(t) && /멘토\s*:/.test(t) && /ICT기술분류\(중\)/.test(t);
  });
  // 다른 카드를 포함하는 상위 블록 제거 → 한 팀 단위만 남긴다
  cards = cards.filter((el) => !cards.some((o) => o !== el && el.contains(o)));

  return cards.map((el) => {
    const t = (el as HTMLElement).innerText.replace(/ /g, " ");
    const name = (t.split("\n").map((x) => x.trim()).filter(Boolean)[0]) || "";
    return {
      team: name,
      leader: segment(t, /팀장\s*:/, /팀원\s*:/).join(" "),
      members: segment(t, /팀원\s*:/, /멘토\s*:/),
      mentor: segment(t, /멘토\s*:/, /ICT기술분류\(대\)/).join(" "),
    };
  });
}
