// Background Service Worker

chrome.action.onClicked.addListener((tab) => {
  chrome.sidePanel.open({ tabId: tab.id! });
});

chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true });

// Content Script(somaParser)로부터 파싱 완료 메시지 수신
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === "PARSE_COMPLETE") {
    console.log(
      `[SoMa Mate BG] 데이터 수집 완료: ${message.page}`,
      message.counts
    );
  }
});
