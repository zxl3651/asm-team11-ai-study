// 확장 아이콘을 누르면 사이드패널이 열리도록 설정한다.
chrome.runtime.onInstalled.addListener(() => {
  chrome.sidePanel
    .setPanelBehavior({ openPanelOnActionClick: true })
    .catch((err) => console.error(err));
});
