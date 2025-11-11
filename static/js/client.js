(() => {
  // Elements
  const welcomeLayer = document.getElementById('welcomeLayer');
  const chatLayer = document.getElementById('chatLayer');
  const displayName = document.getElementById('displayName');
  const startBtn = document.getElementById('startBtn');
  const messages = document.getElementById('messages');
  const msgForm = document.getElementById('msgForm');
  const msgInput = document.getElementById('msgInput');
  const statusDot = document.getElementById('statusDot');
  const statusText = document.getElementById('statusText');
  const minimizeBtn = document.getElementById('minimizeBtn');

  let ws = null;
  let conversationId = localStorage.getItem('conv_id');
  let userName = '';

  function setConnState(online) {
    if (online) {
      statusDot.className = 'status-dot online';
      statusText.textContent = 'Bağlı';
      statusText.style.color = '#10b981';
    } else {
      statusDot.className = 'status-dot offline';
      statusText.textContent = 'Bağlı değil';
      statusText.style.color = '#ef4444';
    }
  }

  // Import utility functions
  const { formatTime, escapeHtml, getUserInitial, showNotification, autoResizeTextarea, getCurrentTime } = window.Utils || {};
  
  // Fallback functions
  const showNotificationFunc = showNotification || function(message, type = 'success') {
    const notification = document.createElement('div');
    notification.className = `notification ${type === 'error' ? 'error' : ''}`;
    notification.textContent = message;
    document.body.appendChild(notification);
    
    setTimeout(() => notification.classList.add('show'), 100);
    setTimeout(() => {
      notification.classList.remove('show');
      setTimeout(() => document.body.removeChild(notification), 300);
    }, 3000);
  };

  function showWelcomeLayer() {
    welcomeLayer.style.display = 'flex';
    chatLayer.classList.add('hidden');
    displayName.focus();
  }

  function showChatLayer() {
    welcomeLayer.style.display = 'none';
    chatLayer.classList.remove('hidden');
    msgInput.focus();
  }

  const autoResizeTextareaFunc = autoResizeTextarea || function(textarea) {
    textarea.style.height = 'auto';
    textarea.style.height = Math.min(textarea.scrollHeight, 120) + 'px';
  };

  const getCurrentTimeFunc = getCurrentTime || function() {
    const now = new Date();
    return now.toLocaleTimeString('tr-TR', { 
      hour: '2-digit', 
      minute: '2-digit' 
    });
  };

  function scrollToBottom() {
    messages.scrollTop = messages.scrollHeight;
  }

  function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }

  function getUserInitial(name) {
    return name ? name.charAt(0).toUpperCase() : '?';
  }

  function addMsg(sender, content, createdAt = null) {
    // Remove empty state if exists
    const emptyState = messages.querySelector('.empty-state');
    if (emptyState) {
      emptyState.remove();
    }

    const div = document.createElement('div');
    div.className = `message ${sender === 'visitor' ? 'visitor' : ''}`;
    
    const avatar = document.createElement('div');
    avatar.className = 'message-avatar';
    
    if (sender === 'visitor') {
      avatar.textContent = getUserInitial(userName);
    } else if (sender === 'system') {
      avatar.innerHTML = '<i class="fas fa-info-circle"></i>';
      avatar.style.fontSize = '1rem';
    } else {
      avatar.innerHTML = '<i class="fas fa-headset"></i>';
      avatar.style.fontSize = '1rem';
    }
    
    div.appendChild(avatar);
    
    const bubble = document.createElement('div');
    bubble.className = 'message-bubble';
    
    const text = document.createElement('div');
    text.className = 'message-text';
    text.textContent = content;
    bubble.appendChild(text);
    
    if (createdAt) {
      const time = document.createElement('div');
      time.className = 'message-time';
      time.textContent = formatTimeFunc(createdAt);
      bubble.appendChild(time);
    } else {
      const time = document.createElement('div');
      time.className = 'message-time';
      time.textContent = getCurrentTimeFunc();
      bubble.appendChild(time);
    }
    
    div.appendChild(bubble);
    messages.appendChild(div);
    scrollToBottom();
  }

  const formatTimeFunc = formatTime || function(dateString) {
    if (!dateString) return getCurrentTimeFunc();
    const date = new Date(dateString);
    const now = new Date();
    const diff = now - date;
    
    if (diff < 60000) {
      return 'Şimdi';
    } else if (diff < 3600000) {
      return Math.floor(diff / 60000) + ' dk önce';
    } else if (diff < 86400000) {
      return date.toLocaleTimeString('tr-TR', { 
        hour: '2-digit', 
        minute: '2-digit' 
      });
    } else {
      return date.toLocaleDateString('tr-TR');
    }
  }

  async function connect(mode) {
    ws = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws/client`);
    
    ws.onopen = () => {
      setConnState(true);
      if (mode === 'join') {
        const name = (displayName.value || 'Ziyaretçi').trim();
        userName = name;
        ws.send(JSON.stringify({type:'join', display_name: name}));
      } else if (mode === 'resume') {
        ws.send(JSON.stringify({type:'resume', conversation_id: conversationId}));
      }
    };
    
    ws.onclose = () => {
      setConnState(false);
      // Try to reconnect after 3 seconds if we have a conversation
      if (conversationId) {
        setTimeout(() => connect('resume'), 3000);
      }
    };
    
    ws.onerror = () => {
      setConnState(false);
    };
    
    ws.onmessage = (ev) => {
      try {
        const d = JSON.parse(ev.data);
        if (d.type === 'joined') {
          conversationId = d.conversation_id;
          localStorage.setItem('conv_id', conversationId);
          showChatLayer();
          showNotificationFunc('Sohbete bağlandı ✅');
          // Add welcome message
          addMsg('system', 'Destek ekibimiz en kısa sürede size yardımcı olacaktır. Lütfen bekleyin...');
        } else if (d.type === 'history') {
          showChatLayer();
          messages.innerHTML = '';
          // Store visitor name from history if available
          if (d.visitor_name) {
            userName = d.visitor_name;
          }
          if (d.messages && d.messages.length > 0) {
            d.messages.forEach(m => addMsg(m.sender, m.content, m.created_at));
          } else {
            // Show empty state if no messages
            messages.innerHTML = `
              <div class="empty-state">
                <i class="fas fa-comments"></i>
                <h3>Sohbete Hoş Geldiniz</h3>
                <p>Destek ekibimiz en kısa sürede size yardımcı olacaktır</p>
              </div>
            `;
          }
          showNotificationFunc('Önceki sohbet yüklendi ✅');
        } else if (d.type === 'message') {
          addMsg(d.sender, d.content, d.created_at || new Date().toISOString());
          // Show notification for new messages from admin
          if (d.sender !== 'visitor') {
            showNotificationFunc('Yeni mesajınız var!');
          }
        } else if (d.type === 'conversation_deleted') {
          localStorage.removeItem('conv_id');
          conversationId = null;
          messages.innerHTML = '';
          showWelcomeLayer();
          showNotificationFunc('Sohbet sonlandırıldı', 'error');
        } else if (d.type === 'error') {
          console.error('WebSocket error:', d.error);
          if (d.error === 'conversation_not_found') {
            localStorage.removeItem('conv_id');
            conversationId = null;
            messages.innerHTML = '';
            showWelcomeLayer();
            showNotificationFunc('Sohbet bulunamadı veya kapatıldı.', 'error');
          } else if (d.error === 'rate_limited') {
            showNotificationFunc('Çok hızlı mesaj gönderiyorsunuz. Lütfen bekleyin.', 'error');
          } else {
            showNotificationFunc('Bir hata oluştu', 'error');
          }
        }
      } catch (e) {
        console.error('Failed to parse WebSocket message:', e);
      }
    };
  }

  // Event listeners
  startBtn.addEventListener('click', () => {
    const name = (displayName.value || '').trim();
    if (!name) {
      showNotificationFunc('Lütfen adınızı girin', 'error');
      displayName.focus();
      return;
    }
    userName = name;
    connect('join');
  });

  displayName.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      startBtn.click();
    }
  });

  msgForm.addEventListener('submit', (e) => {
    e.preventDefault();
    const text = (msgInput.value || '').trim();
    if (!text) return;
    if (text.length > 2000) {
      showNotificationFunc('Mesaj çok uzun (max 2000 karakter)', 'error');
      return;
    }
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      showNotificationFunc('Bağlantı yok. Lütfen bekleyin...', 'error');
      return;
    }
    
    // Optimistically add message
    addMsg('visitor', text);
    msgInput.value = '';
    autoResizeTextareaFunc(msgInput);
    
    try {
      ws.send(JSON.stringify({type:'message', content:text}));
    } catch (e) {
      console.error('Failed to send message:', e);
      showNotificationFunc('Mesaj gönderilemedi', 'error');
    }
  });

  msgInput.addEventListener('input', (e) => {
    autoResizeTextareaFunc(e.target);
  });

  msgInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      msgForm.dispatchEvent(new Event('submit'));
    }
  });

  minimizeBtn.addEventListener('click', () => {
    showWelcomeLayer();
  });

  // Initialize
  if (conversationId) {
    // Try to resume existing conversation
    showChatLayer();
    connect('resume');
  } else {
    showWelcomeLayer();
  }
})();
