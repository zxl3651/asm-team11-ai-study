// 소마 로그인/연수생 여부 확인.
//
// 원리: content script 는 swmaestro.ai 페이지 위에서 돌기 때문에,
// 마이페이지 대시보드를 same-origin 으로 fetch 하면 로그인 쿠키가 자동 첨부된다.
// - 로그인된 연수생  → 대시보드 HTML 에 "NN기 연수생" 텍스트가 들어있다.
// - 비로그인         → 소마가 로그인 페이지로 리다이렉트하므로 그 텍스트가 없다.

const DASHBOARD_URL =
  "https://www.swmaestro.ai/busan/sw/mypage/myMain/dashboard.do?menuNo=200026";

export interface AuthResult {
  loggedIn: boolean;
  cohort: string; // 예: "17기 연수생" (확인용 신원 문자열)
}

export async function checkAuth(): Promise<AuthResult> {
  try {
    const res = await fetch(DASHBOARD_URL, {
      credentials: "include",
      redirect: "follow",
    });

    // 로그인 페이지로 튕겼으면 비로그인
    if (res.redirected && /login/i.test(res.url)) {
      return { loggedIn: false, cohort: "" };
    }

    const html = await res.text();
    const m = html.match(/(\d+)\s*기\s*연수생/);
    if (m) {
      return { loggedIn: true, cohort: `${m[1]}기 연수생` };
    }
    return { loggedIn: false, cohort: "" };
  } catch {
    // 네트워크 실패 등은 비로그인으로 처리
    return { loggedIn: false, cohort: "" };
  }
}
