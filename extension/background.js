// SoMa Mate - Background Service Worker
// 확장 아이콘 클릭 시 사이드패널이 바로 열리도록 설정합니다.
chrome.sidePanel
  .setPanelBehavior({ openPanelOnActionClick: true })
  .catch((error) => console.error('사이드패널 설정 오류:', error));

// 소마 사이트에서 자동 활성화
chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (changeInfo.status === 'complete' && tab.url) {
    if (tab.url.includes('swmaestro.ai')) {
      chrome.sidePanel.setOptions({
        tabId,
        path: 'sidepanel.html',
        enabled: true
      });
    }
  }
});

// 설치 시 초기 설정
chrome.runtime.onInstalled.addListener(() => {
  console.log('소마 메이트가 설치되었습니다!');
});
