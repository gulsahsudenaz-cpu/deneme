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

  const escapeHtmlFunc = escapeHtml || function(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  };

  const getUserInitialFunc = getUserInitial || function(name) {
    return name ? name.charAt(0).toUpperCase() : '?';
  };

  function addMsg(sender, content, createdAt = null, messageType = 'text', fileUrl = null, fileSize = null, fileMime = null) {
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
      avatar.textContent = getUserInitialFunc(userName);
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
    
    // Handle different message types
    if (messageType === 'image' && fileUrl) {
      const img = document.createElement('img');
      img.src = fileUrl;
      img.className = 'message-image';
      img.style.maxWidth = '200px';
      img.style.maxHeight = '200px';
      img.style.borderRadius = '8px';
      img.style.cursor = 'pointer';
      img.onclick = () => window.open(fileUrl, '_blank');
      bubble.appendChild(img);
      
      if (content && content !== `Shared a image`) {
        const text = document.createElement('div');
        text.className = 'message-text';
        text.innerHTML = escapeHtmlFunc(content);
        bubble.appendChild(text);
      }
    } else if (messageType === 'audio' && fileUrl) {
      const audio = document.createElement('audio');
      audio.src = fileUrl;
      audio.controls = true;
      audio.style.maxWidth = '250px';
      bubble.appendChild(audio);
      
      if (content && content !== `Shared a audio`) {
        const text = document.createElement('div');
        text.className = 'message-text';
        text.innerHTML = escapeHtmlFunc(content);
        bubble.appendChild(text);
      }
    } else {
      const text = document.createElement('div');
      text.className = 'message-text';
      text.innerHTML = escapeHtmlFunc(content);
      bubble.appendChild(text);
    }
    
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
    // Railway doesn't support WebSockets - use HTTP polling fallback
    console.log('WebSocket not supported on Railway, using HTTP polling fallback');
    
    if (mode === 'join') {
      const name = (displayName.value || 'Ziyaretçi').trim();
      userName = name;
      
      try {
        const response = await fetch('/api/visitor/join', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ display_name: name })
        });
        
        if (response.ok) {
          const data = await response.json();
          conversationId = data.conversation_id;
          localStorage.setItem('conv_id', conversationId);
          showChatLayer();
          showNotificationFunc('Sohbete bağlandı ✅');
          addMsg('system', 'Destek ekibimiz en kısa sürede size yardımcı olacaktır. Lütfen bekleyin...');
          startPolling();
        }
      } catch (e) {
        showNotificationFunc('Bağlantı hatası', 'error');
      }
    } else if (mode === 'resume') {
      showChatLayer();
      loadMessages();
      startPolling();
    }
  }
  
  let pollingInterval;
  
  function startPolling() {
    console.log('Starting HTTP polling for client (WebSocket not supported on Railway)');
    setConnState(true);
    loadMessages(); // Initial load
    pollingInterval = setInterval(loadMessages, 8000); // Poll every 8 seconds (much slower)
  }
  
  function stopPolling() {
    setConnState(false);
    if (pollingInterval) {
      clearInterval(pollingInterval);
      pollingInterval = null;
    }
  }
  
  async function loadMessages() {
    if (!conversationId) return;
    
    try {
      const response = await fetch(`/api/visitor/messages/${conversationId}`);
      if (response.ok) {
        const newMessages = await response.json();
        
        // Check if we need to update messages
        const currentMsgCount = messages.querySelectorAll('.message').length;
        if (newMessages.length !== currentMsgCount) {
          // Clear and reload all messages
          messages.innerHTML = '';
          
          if (newMessages.length === 0) {
            messages.innerHTML = `
              <div class="empty-state">
                <i class="fas fa-comments"></i>
                <h3>Sohbete Hoş Geldiniz</h3>
                <p>Destek ekibimiz en kısa sürede size yardımcı olacaktır</p>
              </div>
            `;
          } else {
            newMessages.forEach(m => {
              addMsg(m.sender, m.content, m.created_at, m.message_type, m.file_url, m.file_size, m.file_mime);
            });
            scrollToBottom();
          }
        }
      }
    } catch (e) {
      console.error('Failed to load messages:', e);
    }
  }
  
  // Replace WebSocket message sending with HTTP
  async function sendMessage(content) {
    if (!conversationId) return;
    
    try {
      const response = await fetch('/api/visitor/send', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ conversation_id: conversationId, content })
      });
      
      if (response.ok) {
        // Message will appear in next poll
        return true;
      }
    } catch (e) {
      console.error('Failed to send message:', e);
      return false;
    }
    return false;
  }
  
  // File upload function
  async function uploadFile(file) {
    if (!conversationId) return false;
    
    const formData = new FormData();
    formData.append('conversation_id', conversationId);
    formData.append('file', file);
    
    try {
      const response = await fetch('/api/visitor/upload', {
        method: 'POST',
        body: formData
      });
      
      if (response.ok) {
        const result = await response.json();
        return result;
      } else {
        const error = await response.json();
        throw new Error(error.detail || 'Upload failed');
      }
    } catch (e) {
      console.error('Failed to upload file:', e);
      throw e;
    }
  }
  
  // Handle file selection
  function handleFileSelect(event) {
    const file = event.target.files[0];
    if (!file) return;
    
    // Validate file type
    const allowedTypes = {
      'image/jpeg': 'image',
      'image/png': 'image', 
      'image/gif': 'image',
      'image/webp': 'image',
      'audio/mpeg': 'audio',
      'audio/wav': 'audio',
      'audio/ogg': 'audio',
      'audio/webm': 'audio',
      'audio/mp4': 'audio'
    };
    
    if (!allowedTypes[file.type]) {
      showNotificationFunc('Desteklenmeyen dosya türü. Sadece resim ve ses dosyaları kabul edilir.', 'error');
      return;
    }
    
    const fileType = allowedTypes[file.type];
    const maxSize = fileType === 'image' ? 5 * 1024 * 1024 : 10 * 1024 * 1024; // 5MB for images, 10MB for audio
    
    if (file.size > maxSize) {
      showNotificationFunc(`Dosya çok büyük. Maksimum boyut: ${maxSize / 1024 / 1024}MB`, 'error');
      return;
    }
    
    // Show uploading message
    const uploadingMsg = `📤 ${fileType === 'image' ? 'Resim' : 'Ses dosyası'} yükleniyor...`;
    addMsg('visitor', uploadingMsg, null, 'text');
    
    // Upload file
    uploadFile(file)
      .then(result => {
        // Remove uploading message
        const lastMsg = messages.lastElementChild;
        if (lastMsg && lastMsg.textContent.includes('yükleniyor')) {
          lastMsg.remove();
        }
        
        // File will appear in next poll, but show immediate feedback
        const fileName = file.name || `${fileType} dosyası`;
        addMsg('visitor', `📎 ${fileName}`, null, fileType, result.file_url, result.file_size, file.type);
      })
      .catch(error => {
        // Remove uploading message
        const lastMsg = messages.lastElementChild;
        if (lastMsg && lastMsg.textContent.includes('yükleniyor')) {
          lastMsg.remove();
        }
        
        showNotificationFunc(`Dosya yüklenemedi: ${error.message}`, 'error');
      });
    
    // Clear file input
    event.target.value = '';
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

  msgForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const text = (msgInput.value || '').trim();
    if (!text) return;
    if (text.length > 2000) {
      showNotificationFunc('Mesaj çok uzun (max 2000 karakter)', 'error');
      return;
    }
    
    // Send message via HTTP
    const success = await sendMessage(text);
    if (success) {
      addMsg('visitor', text, null, 'text');
      msgInput.value = '';
      autoResizeTextareaFunc(msgInput);
    } else {
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
  
  // File input handler
  const fileInput = document.getElementById('fileInput');
  if (fileInput) {
    fileInput.addEventListener('change', handleFileSelect);
  }
  
  // File upload button handler
  const fileBtn = document.getElementById('fileBtn');
  if (fileBtn && fileInput) {
    fileBtn.addEventListener('click', () => {
      fileInput.click();
    });
  }

  minimizeBtn.addEventListener('click', () => {
    stopPolling();
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
