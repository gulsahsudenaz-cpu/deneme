// Shared utility functions for client and admin

// Create global Utils object for backward compatibility
window.Utils = window.Utils || {};

function formatTime(dateString) {
  if (!dateString) return getCurrentTime();
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

function getCurrentTime() {
  const now = new Date();
  return now.toLocaleTimeString('tr-TR', { 
    hour: '2-digit', 
    minute: '2-digit' 
  });
}

function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

function getUserInitial(name) {
  return name ? name.charAt(0).toUpperCase() : '?';
}

function showNotification(message, type = 'success') {
  const notification = document.createElement('div');
  notification.className = `notification ${type === 'error' ? 'error' : ''}`;
  notification.textContent = message;
  document.body.appendChild(notification);
  
  setTimeout(() => notification.classList.add('show'), 100);
  setTimeout(() => {
    notification.classList.remove('show');
    setTimeout(() => document.body.removeChild(notification), 300);
  }, 3000);
}

function autoResizeTextarea(textarea) {
  textarea.style.height = 'auto';
  textarea.style.height = Math.min(textarea.scrollHeight, 120) + 'px';
}

// Assign functions to global Utils object
window.Utils.formatTime = formatTime;
window.Utils.getCurrentTime = getCurrentTime;
window.Utils.escapeHtml = escapeHtml;
window.Utils.getUserInitial = getUserInitial;
window.Utils.showNotification = showNotification;
window.Utils.autoResizeTextarea = autoResizeTextarea;
