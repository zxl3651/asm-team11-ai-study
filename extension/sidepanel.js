// ============================================
// 소마 메이트 - 사이드패널 UI 컨트롤러
// ============================================

(function () {
  'use strict';

  // DOM References
  const chatArea = document.getElementById('chatArea');
  const welcomeScreen = document.getElementById('welcomeScreen');
  const messageInput = document.getElementById('messageInput');
  const sendBtn = document.getElementById('sendBtn');
  const clearBtn = document.getElementById('clearBtn');
  const chips = document.querySelectorAll('.chip');

  let isProcessing = false;

  // ── 초기화 ──
  function init() {
    // 서버 연결 확인 (선택)
    console.log('[SoMa Mate] Sidepanel initialized.');

    // 이벤트 바인딩
    sendBtn.addEventListener('click', handleSend);
    messageInput.addEventListener('input', handleInputChange);
    messageInput.addEventListener('keydown', handleKeyDown);
    clearBtn.addEventListener('click', handleClear);

    // 빠른 질문 칩
    chips.forEach(chip => {
      chip.addEventListener('click', () => {
        const query = chip.dataset.query;
        if (query && !isProcessing) {
          messageInput.value = query;
          handleSend();
        }
      });
    });

    // 텍스트에어리어 자동 높이
    messageInput.addEventListener('input', autoResize);
  }

  // ── 메시지 전송 ──
  async function handleSend() {
    const message = messageInput.value.trim();
    if (!message || isProcessing) return;

    isProcessing = true;
    sendBtn.disabled = true;

    // 환영 화면 숨기기
    if (welcomeScreen) {
      welcomeScreen.classList.add('hidden');
    }

    // 사용자 메시지 표시
    appendMessage('user', message);
    messageInput.value = '';
    messageInput.style.height = 'auto';

    // 타이핑 인디케이터 표시
    const typingEl = appendTypingIndicator();

    try {
      // 백엔드 API 호출
      let response;
      try {
        const res = await fetch('http://localhost:8000/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ message, session_id: 'default' })
        });
        
        if (!res.ok) throw new Error('서버 통신 오류');
        const data = await res.json();
        
        let finalData = data;
        
        while (finalData.action && finalData.action.action === 'FETCH_URL') {
          console.log('[SoMa Mate] Fetching from client:', finalData.action.url);
          // 익스텐션에서 소마 홈페이지 쿠키를 활용해 데이터 요청
          const htmlRes = await fetch(finalData.action.url);
          const htmlText = await htmlRes.text();
          
          console.log('[SoMa Mate] Sending HTML to backend callback');
          const callbackRes = await fetch('http://localhost:8000/chat/callback', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              session_id: 'default',
              tool_call_id: finalData.action.tool_call_id,
              html_content: htmlText
            })
          });
          
          if (!callbackRes.ok) throw new Error('콜백 통신 오류');
          finalData = await callbackRes.json();
        }
        
        response = {
          text: finalData.response,
          cards: finalData.cards || [],
          sources: []
        };
      } catch (err) {
        response = {
          text: '백엔드 서버와 통신할 수 없습니다. 로컬 서버(http://localhost:8000)가 켜져 있는지 확인해주세요.',
          cards: [],
          sources: []
        };
      }

      // 타이핑 인디케이터 제거
      removeTypingIndicator(typingEl);

      // 에이전트 응답 표시
      appendAgentResponse(response);

    } catch (error) {
      removeTypingIndicator(typingEl);
      appendErrorMessage(error.message || '오류가 발생했습니다. 다시 시도해주세요.');
    } finally {
      isProcessing = false;
      updateSendButton();
    }
  }

  // ── 메시지 렌더링 ──
  function appendMessage(role, text) {
    const msgEl = document.createElement('div');
    msgEl.className = `message ${role}`;

    const avatar = role === 'agent' ? '🎓' : '👤';

    msgEl.innerHTML = `
      <div class="message-avatar">${avatar}</div>
      <div class="message-content">
        <div class="message-bubble">
          ${formatText(text)}
        </div>
      </div>
    `;

    chatArea.appendChild(msgEl);
    scrollToBottom();
    return msgEl;
  }

  function appendAgentResponse(response) {
    const msgEl = document.createElement('div');
    msgEl.className = 'message agent';

    msgEl.innerHTML = `
      <div class="message-avatar">🎓</div>
      <div class="message-content">
        <div class="message-bubble">
          ${formatText(response.text)}
        </div>
      </div>
    `;

    chatArea.appendChild(msgEl);
    scrollToBottom();
  }

  function appendErrorMessage(errorText) {
    const msgEl = document.createElement('div');
    msgEl.className = 'message agent';
    msgEl.innerHTML = `
      <div class="message-avatar">🎓</div>
      <div class="message-content">
        <div class="error-msg">⚠️ ${errorText}</div>
      </div>
    `;
    chatArea.appendChild(msgEl);
    scrollToBottom();
  }

  function appendTypingIndicator() {
    const msgEl = document.createElement('div');
    msgEl.className = 'message agent';
    msgEl.innerHTML = `
      <div class="message-avatar">🎓</div>
      <div class="message-content">
        <div class="message-bubble">
          <div class="typing-indicator">
            <div class="typing-dot"></div>
            <div class="typing-dot"></div>
            <div class="typing-dot"></div>
          </div>
        </div>
      </div>
    `;
    chatArea.appendChild(msgEl);
    scrollToBottom();
    return msgEl;
  }

  function removeTypingIndicator(el) {
    if (el && el.parentNode) {
      el.parentNode.removeChild(el);
    }
  }


  // ── Input Handlers ──
  function handleInputChange() {
    updateSendButton();
  }

  function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  function updateSendButton() {
    sendBtn.disabled = !messageInput.value.trim() || isProcessing;
  }

  function autoResize() {
    messageInput.style.height = 'auto';
    messageInput.style.height = Math.min(messageInput.scrollHeight, 120) + 'px';
  }

  function handleClear() {
    // 메시지 영역 초기화
    chatArea.innerHTML = '';
    chatArea.appendChild(welcomeScreen);
    welcomeScreen.classList.remove('hidden');

    // 백엔드 세션 초기화
    try {
      fetch('http://localhost:8000/chat/default', { method: 'DELETE' });
    } catch(e) {}
  }

  // ── Utilities ──
  function formatText(text) {
    if (!text) return '';
    
    let html = text.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" style="color: #6366f1; text-decoration: underline;">$1</a>');
    html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
    html = html.replace(/`(.*?)`/g, '<code style="background:rgba(99,102,241,0.1);padding:1px 5px;border-radius:3px;font-size:12px;">$1</code>');
    html = html.replace(/^### (.*$)/gim, '<h3 style="margin: 12px 0 6px 0; font-size: 1.1em; color: #1f2937;">$1</h3>');
    html = html.replace(/^## (.*$)/gim, '<h2 style="margin: 14px 0 6px 0; font-size: 1.2em; color: #111827;">$1</h2>');
    html = html.replace(/^---$/gim, '<hr style="margin: 12px 0; border: 0; border-top: 1px solid #e5e7eb;">');

    const lines = html.split('\n');
    let inTable = false;
    let isFirstTableRow = false;
    let inList = false;
    let newLines = [];
    
    for (let i = 0; i < lines.length; i++) {
        let line = lines[i].trim();
        
        // Handle Tables
        if (line.startsWith('|') && line.endsWith('|')) {
            if (inList) { inList = false; newLines.push('</ul>'); }
            if (!inTable) {
                inTable = true;
                isFirstTableRow = true;
                newLines.push('<div style="overflow-x:auto;"><table style="width:100%; border-collapse: collapse; margin: 10px 0; font-size: 13px; text-align: left;">');
            }
            if (line.match(/^\|[\s\-:|]+\|$/)) {
                continue; // 테이블 구분선 무시
            }
            let cells = line.split('|').slice(1, -1).map(c => c.trim());
            let tr;
            if (isFirstTableRow) {
                tr = '<tr>' + cells.map(c => `<th style="background-color: #f9fafb; font-weight: 600; padding: 8px; border: 1px solid #e5e7eb;">${c}</th>`).join('') + '</tr>';
                isFirstTableRow = false;
            } else {
                tr = '<tr>' + cells.map(c => `<td style="border: 1px solid #e5e7eb; padding: 8px;">${c}</td>`).join('') + '</tr>';
            }
            newLines.push(tr);

        } else {
            if (inTable) {
                inTable = false;
                newLines.push('</table></div>');
            }
            
            // Handle Lists (- or 1. etc)
            let listMatch = line.match(/^(\-|\*|\d+\.)\s+(.+)$/);
            if (listMatch) {
                if (!inList) {
                    inList = true;
                    newLines.push('<ul style="margin: 8px 0; padding-left: 20px;">');
                }
                newLines.push(`<li>${listMatch[2]}</li>`);
            } else {
                if (inList) {
                    inList = false;
                    newLines.push('</ul>');
                }
                newLines.push(lines[i] + '<br>');
            }
        }
    }
    if (inTable) {
        newLines.push('</table></div>');
    }
    if (inList) {
        newLines.push('</ul>');
    }
    
    return newLines.join('').replace(/(<br>)$/, '');
  }

  function escapeHtml(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  }

  function scrollToBottom() {
    requestAnimationFrame(() => {
      chatArea.scrollTop = chatArea.scrollHeight;
    });
  }

  // ── 시작 ──
  document.addEventListener('DOMContentLoaded', init);
})();
