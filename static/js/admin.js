(() => {
  // Elements
  const loginModal = document.getElementById('loginModal');
  const usersLayer = document.querySelector('.users-layer');
  const chatLayer = document.querySelector('.chat-layer');
  
  const reqOtpBtn = document.getElementById('reqOtpBtn');
  const loginBtn = document.getElementById('loginBtn');
  const loginForm = document.getElementById('loginForm');
  const otpInput = document.getElementById('otpInput');
  const loginMsg = document.getElementById('loginMsg');

  const convList = document.getElementById('convList');
  const adminMessages = document.getElementById('adminMessages');
  const adminForm = document.getElementById('adminForm');
  const adminInput = document.getElementById('adminInput');
  const backBtn = document.getElementById('backBtn');
  const delBtn = document.getElementById('delBtn');
  const convTitle = document.getElementById('convTitle');
  const chatUserAvatar = document.getElementById('chatUserAvatar');
  const userStatus = document.getElementById('userStatus');
  const wsDot = document.getElementById('wsDot');
  const wsTxt = document.getElementById('wsTxt');
  const refreshBtn = document.getElementById('refreshBtn');
  const logoutBtn = document.getElementById('logoutBtn');
  const searchInput = document.getElementById('searchInput');
  const activeUsers = document.getElementById('activeUsers');
  const totalMessages = document.getElementById('totalMessages');

  let token = localStorage.getItem('admin_token');
  let selectedConv = null;
  let conversations = [];
  const messageCache = new Map();

  function setWsState(ok) {
    if (ok) {
      wsDot.className = 'status-dot online';
      wsTxt.textContent = 'Bağlı';
      wsTxt.style.color = '#10b981';
    } else {
      wsDot.className = 'status-dot offline';
      wsTxt.textContent = 'Bağlı değil';
      wsTxt.style.color = '#6b7280';
    }
  }

  // Import utility functions
  const { formatTime, escapeHtml, getUserInitial, showNotification, autoResizeTextarea } = window.Utils || {};
  
  // Fallback if utils not loaded
  function showNotificationFallback(message, type = 'success') {
    const notification = document.createElement('div');
    notification.style.cssText = `
      position: fixed;
      top: 20px;
      right: 20px;
      background: ${type === 'error' ? '#ef4444' : '#10b981'};
      color: white;
      padding: 12px 20px;
      border-radius: 8px;
      box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.25);
      z-index: 9999;
      transform: translateX(400px);
      transition: transform 0.3s ease;
      font-size: 0.875rem;
      font-weight: 500;
    `;
    notification.textContent = message;
    document.body.appendChild(notification);
    
    setTimeout(() => notification.style.transform = 'translateX(0)', 100);
    setTimeout(() => {
      notification.style.transform = 'translateX(400px)';
      setTimeout(() => document.body.removeChild(notification), 300);
    }, 3000);
  }
  
  const showNotificationFunc = showNotification || showNotificationFallback;

  function showLoginMessage(message, type = 'info') {
    loginMsg.textContent = message;
    loginMsg.className = `login-message ${type}`;
  }

  function showLoginLayer() {
    loginModal.style.display = 'flex';
    usersLayer.classList.add('hidden');
    chatLayer.classList.add('hidden');
    messageCache.clear();
  }

  function showUsersLayer() {
    loginModal.style.display = 'none';
    usersLayer.classList.remove('hidden');
    chatLayer.classList.add('hidden');
    selectedConv = null;
    messageCache.clear();
    loadConversations();
  }

  function showChatLayer() {
    loginModal.style.display = 'none';
    usersLayer.classList.add('hidden');
    chatLayer.classList.remove('hidden');
  }

  // Use utility functions from utils.js or fallbacks
  const autoResizeTextareaFunc = autoResizeTextarea || function(textarea) {
    textarea.style.height = 'auto';
    textarea.style.height = Math.min(textarea.scrollHeight, 120) + 'px';
  };

  const formatTimeFunc = formatTime || function(dateString) {
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
  };

  const escapeHtmlFunc = escapeHtml || function(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  };

  const getUserInitialFunc = getUserInitial || function(name) {
    return name ? name.charAt(0).toUpperCase() : '?';
  };

  function resetConversationCache(convId) {
    if (!convId) return;
    messageCache.set(convId, []);
  }

  function rememberMessages(convId, ids) {
    messageCache.set(convId, ids.slice(-200));
  }

  function getCachedMessages(convId) {
    return messageCache.get(convId) || [];
  }

  async function api(path, opts = {}) {
    opts.headers = opts.headers || {};
    if (token) opts.headers['Authorization'] = `Bearer ${token}`;
    const r = await fetch(path, opts);
    if (!r.ok) {
      const text = await r.text();
      throw new Error(text || `HTTP ${r.status}`);
    }
    // Check for token rotation in response header
    const newToken = r.headers.get('X-New-Token');
    const tokenRotated = r.headers.get('X-Token-Rotated');
    if (tokenRotated === 'true' && newToken) {
      token = newToken;
      localStorage.setItem('admin_token', token);
    }
    return r.json();
  }

  async function loadConversations() {
    try {
      const data = await api('/api/admin/conversations');
      conversations = data;
      
      // Update stats
      const activeCount = data.length;
      activeUsers.textContent = `${activeCount} Aktif`;
      const totalMsgCount = data.reduce((sum, c) => sum + (c.message_count || 0), 0);
      totalMessages.textContent = `${totalMsgCount} Mesaj`;
      
      renderConversationsList(data);
    } catch (e) {
      console.error('Failed to load conversations:', e);
      showNotificationFunc('Sohbetler yüklenemedi', 'error');
    }
  }

  function renderConversationsList(data) {
    if (data.length === 0) {
      convList.innerHTML = `
        <div class="empty-state">
          <i class="fas fa-comments"></i>
          <h4>Henüz sohbet yok</h4>
          <p>Aktif sohbet bulunmuyor</p>
        </div>
      `;
      return;
    }

    // Filter by search
    const searchQuery = searchInput.value.toLowerCase();
    const filtered = searchQuery 
      ? data.filter(c => c.visitor_name.toLowerCase().includes(searchQuery))
      : data;

    convList.innerHTML = filtered.map(c => {
      const isActive = selectedConv === c.conversation_id;
      const lastActivity = formatTimeFunc(c.last_activity_at);
      const initial = getUserInitialFunc(c.visitor_name);
      
      return `
        <div class="user-item ${isActive ? 'active' : ''}" data-id="${c.conversation_id}">
          <div class="user-avatar">${initial}</div>
          <div class="user-info">
            <div class="user-name">${escapeHtmlFunc(c.visitor_name)}</div>
            <div class="user-status">
              <span class="status-indicator" style="background: #10b981"></span>
              <span>Aktif</span>
            </div>
            <div class="user-meta">${lastActivity}</div>
          </div>
        </div>
      `;
    }).join('');

    // Add click listeners
    convList.querySelectorAll('.user-item').forEach(item => {
      item.addEventListener('click', () => {
        const convId = item.dataset.id;
        const conv = data.find(c => c.conversation_id === convId);
        if (conv) {
          openConversation(convId, conv.visitor_name);
        }
      });
    });
  }


async function openConversation(id, nameText) {
  try {
    selectedConv = id;
    convTitle.textContent = nameText;
    // Set avatar with initial (avatar already has CSS class)
    const initial = getUserInitialFunc(nameText);
    chatUserAvatar.textContent = initial;
    chatUserAvatar.className = 'user-avatar';
    userStatus.textContent = 'Aktif';
    userStatus.style.color = '#10b981';
    adminMessages.innerHTML = '';
    resetConversationCache(id);

    // Update active state in list
    convList.querySelectorAll('.user-item').forEach(item => {
      item.classList.toggle('active', item.dataset.id === id);
    });

    showChatLayer();

    // Load messages
    const result = await api(`/api/admin/messages/${id}`);

    // Handle new response format (with cursor) or old format (array)
    const messages = Array.isArray(result) ? result : (result.messages || []);

    if (messages.length === 0) {
      renderEmptyMessages();
      rememberMessages(id, []);
      return;
    }

    adminMessages.innerHTML = '';
    messages.forEach(m => addMsg(m.sender, m.content, m.created_at, m.message_type, m.file_url, m.file_size, m.file_mime));
    rememberMessages(id, messages.map(m => m.id));
    scrollToBottom();
  } catch (e) {
    console.error('Failed to open conversation:', e);
    showNotificationFunc('Sohbet yüklenemedi', 'error');
    selectedConv = null;
    convTitle.textContent = 'Sohbet seçiniz';
  }
}



function addMsg(sender, content, createdAt = null, messageType = 'text', fileUrl = null, fileSize = null, fileMime = null) {
  const emptyState = adminMessages.querySelector('.empty-state');
  if (emptyState) {
    emptyState.remove();
  }

  const div = document.createElement('div');
  div.className = `message ${sender === 'admin' ? 'admin' : ''}`;

  const avatar = document.createElement('div');
  avatar.className = 'message-avatar';
  avatar.textContent = sender === 'admin' ? 'A' : getUserInitialFunc(convTitle.textContent);
  div.appendChild(avatar);

  const bubble = document.createElement('div');
  bubble.className = 'message-bubble';

  const hasFilePreview = Boolean(fileUrl && messageType !== 'text');

  if (hasFilePreview) {
    if (messageType === 'image') {
      const img = document.createElement('img');
      img.src = fileUrl;
      img.alt = content || 'Image';
      img.className = 'message-image';
      img.style.maxWidth = '220px';
      img.style.borderRadius = '8px';
      img.style.cursor = 'pointer';
      img.addEventListener('click', () => window.open(fileUrl, '_blank'));
      bubble.appendChild(img);
    } else if (messageType === 'audio') {
      const audio = document.createElement('audio');
      audio.controls = true;
      audio.src = fileUrl;
      audio.style.width = '100%';
      bubble.appendChild(audio);
    }
  }

  if (content) {
    const textNode = document.createElement('div');
    textNode.className = 'message-text';
    textNode.textContent = content;
    bubble.appendChild(textNode);
  }

  if (fileUrl) {
    const meta = document.createElement('div');
    meta.className = 'message-file';

    const link = document.createElement('a');
    link.href = fileUrl;
    link.target = '_blank';
    link.rel = 'noopener noreferrer';
    link.textContent = 'Dosyayı aç';
    meta.appendChild(link);

    if (fileSize) {
      const size = document.createElement('span');
      size.textContent = ` • ${formatFileSize(fileSize)}`;
      meta.appendChild(size);
    }

    if (fileMime) {
      const mime = document.createElement('span');
      mime.textContent = ` • ${fileMime}`;
      meta.appendChild(mime);
    }

    bubble.appendChild(meta);
  }

  const time = document.createElement('div');
  time.className = 'message-time';
  if (createdAt) {
    time.textContent = formatTimeFunc(createdAt);
  } else {
    time.textContent = new Date().toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit' });
  }
  bubble.appendChild(time);

  div.appendChild(bubble);
  adminMessages.appendChild(div);
  scrollToBottom();
  return div;
}

function scrollToBottom() {
  adminMessages.scrollTop = adminMessages.scrollHeight;
}

function formatFileSize(bytes) {
  if (!bytes && bytes !== 0) return '';
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  if (bytes >= 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${bytes} B`;
}

function renderEmptyMessages() {
  adminMessages.innerHTML = `
    <div class="empty-state">
      <i class="fas fa-comment-dots"></i>
      <h4>Henüz mesaj yok</h4>
      <p>İlk mesajı siz gönderin</p>
    </div>
  `;
}

function removeTempMessage(sender) {
  if (sender !== 'admin') return;
  const temp = adminMessages.querySelector('.message[data-temp="true"]');
  if (temp) {
    temp.remove();
  }
}

function syncConversationMessages(convId, messages) {
  const cachedIds = getCachedMessages(convId);

  if (messages.length === 0) {
    renderEmptyMessages();
    rememberMessages(convId, []);
    return;
  }

  if (!cachedIds.length || messages.length < cachedIds.length) {
    adminMessages.innerHTML = '';
    messages.forEach(m => addMsg(m.sender, m.content, m.created_at, m.message_type, m.file_url, m.file_size, m.file_mime));
    rememberMessages(convId, messages.map(m => m.id));
    scrollToBottom();
    return;
  }

  const known = new Set(cachedIds);
  const newOnes = messages.filter(m => !known.has(m.id));
  if (!newOnes.length) {
    return;
  }

  newOnes.forEach(m => {
    removeTempMessage(m.sender);
    addMsg(m.sender, m.content, m.created_at, m.message_type, m.file_url, m.file_size, m.file_mime);
  });

  rememberMessages(convId, cachedIds.concat(newOnes.map(m => m.id)));
  scrollToBottom();
}

  // HTTP Polling (WebSocket replacement for Railway)
  let pollingInterval;
  
  function startPolling() {
    console.log('Starting HTTP polling for admin (WebSocket not supported on Railway)');
    setWsState(true);
    loadConversations(); // Initial load
    pollingInterval = setInterval(() => {
      loadConversations();
      if (selectedConv) {
        loadSelectedConversationMessages();
      }
    }, 5000); // Poll every 5 seconds (reduced frequency)
  }
  
  function stopPolling() {
    setWsState(false);
    if (pollingInterval) {
      clearInterval(pollingInterval);
      pollingInterval = null;
    }
  }
  


  async function loadSelectedConversationMessages() {
    if (!selectedConv) return;
  
    try {
      const result = await api(`/api/admin/messages/${selectedConv}`);
      const messages = Array.isArray(result) ? result : (result.messages || []);
      syncConversationMessages(selectedConv, messages);
    } catch (e) {
      console.error('Failed to load conversation messages:', e);
    }
  }
  
  // Event listeners


  reqOtpBtn.addEventListener('click', async () => {
    showLoginMessage('Kod gönderiliyor...', 'info');
    reqOtpBtn.disabled = true;
    reqOtpBtn.classList.add('loading');
    try {
      const r = await fetch('/api/admin/request_otp', { 
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        }
      });
      
      if (!r.ok) {
        throw new Error(`HTTP ${r.status}`);
      }
      
      const data = await r.json();
      if (data.sent) {
        showLoginMessage('Kod Telegram\'a gönderildi! ✅', 'success');
        otpInput.focus();
      } else {
        const reason = data.error || 'Kod gönderilemedi';
        showLoginMessage(`❌ ${reason}`, 'error');
      }
    } catch (e) {
      console.error('Failed to request OTP:', e);
      showLoginMessage('❌ Bağlantı hatası. Tekrar deneyin.', 'error');
    } finally {
      reqOtpBtn.disabled = false;
      reqOtpBtn.classList.remove('loading');
    }
  });

  loginForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const code = (otpInput.value || '').trim();
    if (code.length !== 6) {
      showLoginMessage('Lütfen 6 haneli kodu girin', 'error');
      return;
    }
    
    try {
      showLoginMessage('Giriş yapılıyor...', 'info');
      const r = await fetch('/api/admin/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code })
      });
      
      if (!r.ok) {
        showLoginMessage('Kod hatalı veya süresi geçti.', 'error');
        return;
      }
      
      const data = await r.json();
      token = data.token;
      localStorage.setItem('admin_token', token);
      showUsersLayer();
      showNotificationFunc('Giriş başarılı! 🎉');
      startPolling(); // Use HTTP polling instead of WebSocket
      await loadConversations();
      // Note: Token rotation is handled in api() function for subsequent requests
    } catch (e) {
      console.error('Login error:', e);
      showLoginMessage('Giriş hatası. Lütfen tekrar deneyin.', 'error');
    }
  });



  adminForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    if (!selectedConv) return;
    const textValue = (adminInput.value || '').trim();
    if (!textValue) return;
    if (textValue.length > 2000) {
      showNotificationFunc('Mesaj çok uzun (max 2000 karakter)', 'error');
      return;
    }
    const tempMsg = addMsg('admin', textValue);
    tempMsg.dataset.temp = 'true';
    adminInput.value = '';
    autoResizeTextareaFunc(adminInput);
    try {
      await api('/api/admin/send', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          conversation_id: selectedConv,
          content: textValue
        })
      });
    } catch (e) {
      console.error('Failed to send message:', e);
      if (tempMsg && tempMsg.parentElement) {
        tempMsg.remove();
      }
      showNotificationFunc('Mesaj gönderilemedi', 'error');
    }
  });

  adminInput.addEventListener('input', (e) => {
    autoResizeTextareaFunc(e.target);
  });

  adminInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      adminForm.dispatchEvent(new Event('submit'));
    }
  });
  
  // File upload function
  async function uploadFile(file) {
    if (!selectedConv) return false;
    
    const formData = new FormData();
    formData.append('conversation_id', selectedConv);
    formData.append('file', file);
    
    try {
      const response = await fetch('/api/admin/upload', {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` },
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
    if (!file || !selectedConv) return;
    
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
    addMsg('admin', uploadingMsg, null, 'text');
    
    // Upload file
    uploadFile(file)
      .then(result => {
        // Remove uploading message
        const lastMsg = adminMessages.lastElementChild;
        if (lastMsg && lastMsg.textContent.includes('yükleniyor')) {
          lastMsg.remove();
        }
        
        // File will appear in next poll, but show immediate feedback
        const fileName = file.name || `${fileType} dosyası`;
        addMsg('admin', `📎 ${fileName}`, null, fileType, result.file_url, result.file_size, file.type);
      })
      .catch(error => {
        // Remove uploading message
        const lastMsg = adminMessages.lastElementChild;
        if (lastMsg && lastMsg.textContent.includes('yükleniyor')) {
          lastMsg.remove();
        }
        
        showNotificationFunc(`Dosya yüklenemedi: ${error.message}`, 'error');
      });
    
    // Clear file input
    event.target.value = '';
  }
  
  // File input handler - FIXED
  const adminFileInput = document.getElementById('adminFileInput');
  const adminFileBtn = document.getElementById('adminFileBtn');
  
  if (adminFileInput) {
    adminFileInput.addEventListener('change', handleFileSelect);
  }
  
  if (adminFileBtn) {
    adminFileBtn.addEventListener('click', () => {
      if (!selectedConv) {
        showNotificationFunc('Lütfen önce bir sohbet seçin', 'error');
        return;
      }
      if (adminFileInput) {
        adminFileInput.click();
      }
    });
  }

  backBtn.addEventListener('click', () => {
    showUsersLayer();
  });

  delBtn.addEventListener('click', async () => {
    if (!selectedConv) return;
    if (!confirm('Bu konuşmayı kalıcı olarak silmek istiyor musunuz?')) return;
    
    try {
      await fetch(`/api/admin/conversations/${selectedConv}`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${token}` }
      });
      showNotificationFunc('Sohbet silindi 🗑️');
      selectedConv = null;
      showUsersLayer();
      await loadConversations();
    } catch (e) {
      console.error('Failed to delete conversation:', e);
      showNotificationFunc('Sohbet silinemedi', 'error');
    }
  });

  refreshBtn.addEventListener('click', () => {
    loadConversations();
    showNotificationFunc('Yenilendi 🔄');
  });

  logoutBtn.addEventListener('click', async () => {
    if (!confirm('Çıkış yapmak istediğinize emin misiniz?')) return;
    
    try {
      await fetch('/api/admin/logout', {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` }
      });
    } catch (e) {
      console.error('Logout error:', e);
    }
    
    localStorage.removeItem('admin_token');
    token = null;
    stopPolling();
    showLoginLayer();
    showNotificationFunc('Çıkış yapıldı 👋');
  });

  searchInput.addEventListener('input', (e) => {
    renderConversationsList(conversations);
  });

  // Initialize - Check token validity
  if (token) {
    // Test token validity before showing users layer
    api('/api/admin/conversations')
      .then(() => {
        showUsersLayer();
        startPolling();
      })
      .catch(() => {
        // Token invalid, clear and show login
        localStorage.removeItem('admin_token');
        token = null;
        showLoginLayer();
        showNotificationFunc('Oturum süresi dolmuş, tekrar giriş yapın', 'error');
      });
  } else {
    showLoginLayer();
  }
})();
