/**
 * NyayaDesk - Modern Judiciary SaaS Client Scripts
 * Handles Dark Mode, Toasts, Modals, Drawers, Sidebar Collapse,
 * Notifications Bell, and Global Search.
 */

// ==========================================================================
// 0. Security Utilities & CSRF Interceptor
// ==========================================================================
function escapeHtml(str) {
  if (str === null || str === undefined) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}
window.escapeHtml = escapeHtml;

// Global CSRF Header Injection for Fetch API
(function() {
  const originalFetch = window.fetch;
  window.fetch = function(url, options = {}) {
    const opts = Object.assign({}, options);
    const method = (opts.method || 'GET').toUpperCase();
    if (['POST', 'PUT', 'DELETE', 'PATCH'].includes(method)) {
      if (!opts.headers) {
        opts.headers = {};
      }
      const hasHeader = opts.headers instanceof Headers 
        ? (opts.headers.has('X-CSRFToken') || opts.headers.has('X-CSRF-Token'))
        : (opts.headers['X-CSRFToken'] || opts.headers['X-CSRF-Token'] || opts.headers['x-csrftoken']);
      
      if (!hasHeader) {
        const metaTag = document.querySelector('meta[name="csrf-token"]');
        if (metaTag && metaTag.content) {
          if (opts.headers instanceof Headers) {
            opts.headers.set('X-CSRFToken', metaTag.content);
          } else {
            opts.headers['X-CSRFToken'] = metaTag.content;
          }
        }
      }
    }
    return originalFetch(url, opts);
  };
})();

// ==========================================================================
// 1. Theme Management (Light / Dark Mode)
// ==========================================================================
function initTheme() {
  let savedTheme = localStorage.getItem('nyayadesk_theme');
  if (!savedTheme) {
    savedTheme = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  }
  document.documentElement.setAttribute('data-theme', savedTheme);
  updateThemeIcon(savedTheme);
}

function toggleTheme() {
  const current = document.documentElement.getAttribute('data-theme') || 'light';
  const next = current === 'dark' ? 'light' : 'dark';
  document.documentElement.setAttribute('data-theme', next);
  localStorage.setItem('nyayadesk_theme', next);
  updateThemeIcon(next);
  showToast(`Switched to ${next.toUpperCase()} mode`, 'info', 2000);
}

function updateThemeIcon(theme) {
  const btn = document.getElementById('theme-toggle-btn');
  if (btn) {
    btn.innerHTML = theme === 'dark' 
      ? '<i data-lucide="sun"></i>' 
      : '<i data-lucide="moon"></i>';
    if (window.lucide && typeof window.lucide.createIcons === 'function') {
      window.lucide.createIcons();
    }
  }
}

// ==========================================================================
// 2. Toast Notification System
// ==========================================================================
function showToast(message, type = 'info', duration = 4000) {
  let container = document.getElementById('toast-container');
  if (!container) {
    container = document.createElement('div');
    container.id = 'toast-container';
    container.className = 'toast-container';
    document.body.appendChild(container);
  }

  const toast = document.createElement('div');
  toast.className = `toast ${type}`;

  const iconMap = {
    success: 'check-circle',
    danger: 'alert-circle',
    warning: 'alert-triangle',
    info: 'info'
  };

  toast.innerHTML = `
    <i data-lucide="${iconMap[type] || 'info'}" style="width: 20px; height: 20px; flex-shrink: 0;"></i>
    <div style="flex: 1;">${message}</div>
    <button onclick="this.parentElement.remove()" style="background:transparent; border:none; color:var(--color-text-muted); cursor:pointer; padding:0 4px;">&times;</button>
  `;

  container.appendChild(toast);
  if (window.lucide && typeof window.lucide.createIcons === 'function') {
    window.lucide.createIcons();
  }

  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateX(20px)';
    toast.style.transition = 'all 0.3s ease';
    setTimeout(() => toast.remove(), 300);
  }, duration);
}

// ==========================================================================
// 3. Modals and Drawers
// ==========================================================================
function openModal(id) {
  const modal = document.getElementById(id);
  if (modal) {
    modal.classList.add('open');
    document.body.style.overflow = 'hidden';
  }
}

function closeModal(id) {
  const modal = document.getElementById(id);
  if (modal) {
    modal.classList.remove('open');
    document.body.style.overflow = '';
  }
}

function openDrawer(id) {
  const overlay = document.getElementById(id);
  if (overlay) {
    overlay.classList.add('open');
    document.body.style.overflow = 'hidden';
  }
}

function closeDrawer(id) {
  const overlay = document.getElementById(id);
  if (overlay) {
    overlay.classList.remove('open');
    document.body.style.overflow = '';
  }
}

// Close modals when clicking backdrop
document.addEventListener('click', (e) => {
  if (e.target.classList.contains('modal-overlay')) {
    e.target.classList.remove('open');
    document.body.style.overflow = '';
  }
  if (e.target.classList.contains('drawer-overlay')) {
    e.target.classList.remove('open');
    document.body.style.overflow = '';
  }
});

// ==========================================================================
// 4. Sidebar Management
// ==========================================================================
function toggleSidebar() {
  const sidebar = document.getElementById('app-sidebar');
  if (sidebar) {
    sidebar.classList.toggle('collapsed');
    const isCollapsed = sidebar.classList.contains('collapsed');
    localStorage.setItem('nyayadesk_sidebar_collapsed', isCollapsed ? '1' : '0');
  }
}

function toggleMobileSidebar() {
  const sidebar = document.getElementById('app-sidebar');
  const backdrop = document.getElementById('sidebar-backdrop');
  if (sidebar) {
    sidebar.classList.toggle('mobile-open');
    if (backdrop) {
      backdrop.classList.toggle('active', sidebar.classList.contains('mobile-open'));
    }
  }
}

function closeMobileSidebar() {
  const sidebar = document.getElementById('app-sidebar');
  const backdrop = document.getElementById('sidebar-backdrop');
  if (sidebar && sidebar.classList.contains('mobile-open')) {
    sidebar.classList.remove('mobile-open');
    if (backdrop) backdrop.classList.remove('active');
  }
}

// Close mobile sidebar on Escape key
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    closeMobileSidebar();
  }
});

// ==========================================================================
// 5. Notifications Bell & Polling
// ==========================================================================
async function loadNotifications() {
  const countBadge = document.getElementById('notif-unread-count');
  const dropdownList = document.getElementById('notif-dropdown-list');
  if (!dropdownList) return;

  try {
    const res = await fetch('/api/notifications');
    if (res.ok) {
      const data = await res.json();
      const notifs = data.notifications || [];
      const unreadCount = data.unread_count || 0;

      if (countBadge) {
        if (unreadCount > 0) {
          countBadge.textContent = unreadCount > 9 ? '9+' : unreadCount;
          countBadge.style.display = 'block';
        } else {
          countBadge.style.display = 'none';
        }
      }

      if (notifs.length === 0) {
        dropdownList.innerHTML = `
          <div style="padding: 1.5rem; text-align: center; color: var(--color-text-muted); font-size: 0.85rem;">
            <i data-lucide="bell-off" style="width: 28px; height: 28px; margin-bottom: 0.35rem;"></i>
            <div>No notifications yet</div>
          </div>
        `;
      } else {
        dropdownList.innerHTML = notifs.map(n => `
          <div style="padding: 0.75rem 1rem; border-bottom: 1px solid var(--color-border); font-size: 0.85rem; display: flex; gap: 0.65rem; align-items: flex-start;">
            <div style="width: 8px; height: 8px; border-radius: 50%; background: ${n.status === 'Sent' ? 'var(--color-accent)' : 'var(--color-border)'}; margin-top: 5px; flex-shrink: 0;"></div>
            <div style="flex: 1;">
              <div>${escapeHtml(n.message)}</div>
              <div style="font-size: 0.72rem; color: var(--color-text-muted); margin-top: 2px;">${escapeHtml(n.sent_at)} &bull; ${escapeHtml(n.channel)}</div>
            </div>
          </div>
        `).join('');
      }
      if (window.lucide && typeof window.lucide.createIcons === 'function') {
        window.lucide.createIcons();
      }
    }
  } catch (err) {
    // Graceful error suppression for network/session timeouts
  }
}

async function markAllNotificationsRead() {
  try {
    const res = await fetch('/api/notifications/mark-read', { method: 'POST' });
    if (res.ok) {
      loadNotifications();
      showToast('All notifications marked as read', 'success');
    }
  } catch (err) {
    showToast('Failed to mark notifications', 'danger');
  }
}

function toggleNotifDropdown() {
  const dd = document.getElementById('notif-dropdown');
  if (dd) {
    dd.style.display = dd.style.display === 'block' ? 'none' : 'block';
  }
}

// Close notif dropdown on outside click
document.addEventListener('click', (e) => {
  const bell = document.getElementById('notif-bell-btn');
  const dd = document.getElementById('notif-dropdown');
  if (bell && dd && !bell.contains(e.target) && !dd.contains(e.target)) {
    dd.style.display = 'none';
  }
});

// ==========================================================================
// 6. Global Case Search
// ==========================================================================
function openGlobalSearch() {
  openModal('global-search-modal');
  const input = document.getElementById('global-search-modal-input');
  if (input) {
    input.focus();
  }
}

let searchDebounceTimer = null;
function handleGlobalSearch(query) {
  clearTimeout(searchDebounceTimer);
  const resultsContainer = document.getElementById('global-search-results');
  if (!resultsContainer) return;

  if (!query || query.trim().length < 2) {
    resultsContainer.innerHTML = '<div style="padding: 1rem; text-align: center; color: var(--color-text-muted);">Type at least 2 characters (Case No, Party Name, or Title)...</div>';
    return;
  }

  resultsContainer.innerHTML = '<div style="padding: 1rem; text-align: center; color: var(--color-text-muted);">Searching judicial records...</div>';

  searchDebounceTimer = setTimeout(async () => {
    try {
      const res = await fetch(`/api/search?q=${encodeURIComponent(query.trim())}`);
      if (res.ok) {
        const data = await res.json();
        const cases = data.cases || [];
        if (cases.length === 0) {
          resultsContainer.innerHTML = '<div style="padding: 1.5rem; text-align: center; color: var(--color-text-muted);">No matching court records found.</div>';
          return;
        }

        resultsContainer.innerHTML = cases.map(c => `
          <div style="padding: 0.85rem 1rem; border-bottom: 1px solid var(--color-border); display: flex; align-items: center; justify-content: space-between; gap: 1rem;">
            <div>
              <div style="font-weight: 700; color: var(--color-primary-dark); font-size: 0.95rem;">${escapeHtml(c.case_number)}</div>
              <div style="font-size: 0.85rem; color: var(--color-text); margin-top: 2px;">${escapeHtml(c.title)}</div>
              <div style="font-size: 0.75rem; color: var(--color-text-muted); margin-top: 2px;">
                ${escapeHtml(c.court)} &bull; Next Date: <strong>${escapeHtml(c.next_hearing_date || 'N/A')}</strong>
              </div>
            </div>
            <div style="text-align: right; flex-shrink: 0;">
              <span class="badge badge-info">${escapeHtml(c.status)}</span>
              <div style="margin-top: 4px;">
                <span class="badge badge-primary">${escapeHtml(c.case_type)}</span>
              </div>
            </div>
          </div>
        `).join('');
      }
    } catch (err) {
      resultsContainer.innerHTML = '<div style="padding: 1rem; text-align: center; color: var(--color-danger);">Error querying court records.</div>';
    }
  }, 300);
}

// ==========================================================================
// 7. Initializer on DOM Load
// ==========================================================================
document.addEventListener('DOMContentLoaded', () => {
  initTheme();

  // Restore sidebar collapsed state
  const isCollapsed = localStorage.getItem('nyayadesk_sidebar_collapsed') === '1';
  const sidebar = document.getElementById('app-sidebar');
  if (sidebar && isCollapsed && window.innerWidth > 768) {
    sidebar.classList.add('collapsed');
  }

  // Initialize Lucide icons
  if (window.lucide && typeof window.lucide.createIcons === 'function') {
    window.lucide.createIcons();
  }

  // Live judicial clock
  const liveClockEl = document.getElementById('live-judicial-clock');
  if (liveClockEl) {
    const updateClock = () => {
      const now = new Date();
      liveClockEl.textContent = now.toLocaleDateString('en-IN', {
        weekday: 'short',
        year: 'numeric',
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
      });
    };
    updateClock();
    setInterval(updateClock, 1000);
  }

  // Load notifications if user authenticated and poll every 20 seconds
  if (document.getElementById('notif-bell-btn')) {
    loadNotifications();
    setInterval(loadNotifications, 20000); // Poll unread badge every 20 seconds
  }
});

// ==========================================================================
// 8. Notification Preferences Modal Management
// ==========================================================================
async function openNotificationPrefsModal() {
  openModal('modal-notification-prefs');
  try {
    const res = await fetch('/api/notifications/preferences');
    if (res.ok) {
      const data = await res.json();
      const prefs = data.preferences || {};
      
      const elSms = document.getElementById('pref-sms');
      const elWa = document.getElementById('pref-whatsapp');
      const elEmail = document.getElementById('pref-email');
      const elInApp = document.getElementById('pref-inapp');
      const elQuiet = document.getElementById('pref-quiet-enabled');
      const elQStart = document.getElementById('pref-quiet-start');
      const elQEnd = document.getElementById('pref-quiet-end');
      const elLang = document.getElementById('pref-language');

      if (elSms) elSms.checked = prefs.sms !== false;
      if (elWa) elWa.checked = prefs.whatsapp !== false;
      if (elEmail) elEmail.checked = prefs.email !== false;
      if (elInApp) elInApp.checked = prefs.in_app !== false;
      if (elQuiet) elQuiet.checked = Boolean(prefs.quiet_hours_enabled);
      if (elQStart) elQStart.value = prefs.quiet_hours_start || '22:00';
      if (elQEnd) elQEnd.value = prefs.quiet_hours_end || '07:00';
      if (elLang) elLang.value = data.language_pref || 'en';

      toggleQuietHoursFields();
    }
  } catch (err) {
    // Graceful error suppression for network/session timeouts
  }
}

function toggleQuietHoursFields() {
  const chk = document.getElementById('pref-quiet-enabled');
  const box = document.getElementById('quiet-hours-container');
  if (chk && box) {
    box.style.display = chk.checked ? 'grid' : 'none';
  }
}

async function saveNotificationPrefs(e) {
  e.preventDefault();
  const sms = document.getElementById('pref-sms').checked;
  const whatsapp = document.getElementById('pref-whatsapp').checked;
  const email = document.getElementById('pref-email').checked;
  const in_app = document.getElementById('pref-inapp').checked;
  const quiet_hours_enabled = document.getElementById('pref-quiet-enabled').checked;
  const quiet_hours_start = document.getElementById('pref-quiet-start').value;
  const quiet_hours_end = document.getElementById('pref-quiet-end').value;
  const language_pref = document.getElementById('pref-language').value;

  try {
    const res = await fetch('/api/notifications/preferences', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        sms,
        whatsapp,
        email,
        in_app,
        quiet_hours_enabled,
        quiet_hours_start,
        quiet_hours_end,
        language_pref
      })
    });
    const result = await res.json();
    if (result.success) {
      showToast(result.message || 'Preferences updated!', 'success');
      closeModal('modal-notification-prefs');
    } else {
      showToast('Failed to save preferences.', 'danger');
    }
  } catch (err) {
    showToast('Network error saving preferences.', 'danger');
  }
}

// ==========================================================================
// 8. Animated Number Count-Up for Stat Cards
// ==========================================================================
function initStatCountUp() {
  const statElements = document.querySelectorAll('.stat-value');
  statElements.forEach(el => {
    const rawText = el.textContent.trim().replace(/,/g, '');
    const target = parseInt(rawText, 10);
    if (!isNaN(target) && target > 0 && !el.dataset.animated) {
      el.dataset.animated = 'true';
      const duration = 750; // ms
      const startTime = performance.now();
      const startVal = 0;

      function updateNumber(now) {
        const elapsed = now - startTime;
        const progress = Math.min(elapsed / duration, 1);
        // Ease-out cubic
        const ease = 1 - Math.pow(1 - progress, 3);
        const current = Math.floor(startVal + (target - startVal) * ease);
        el.textContent = current.toLocaleString();

        if (progress < 1) {
          requestAnimationFrame(updateNumber);
        } else {
          el.textContent = target.toLocaleString();
        }
      }

      requestAnimationFrame(updateNumber);
    }
  });
}

// ==========================================================================
// 9. Input Sanitization / HTML Escaper Utility
// ==========================================================================
function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

// Trigger count-up animation after DOM loads
document.addEventListener('DOMContentLoaded', () => {
  setTimeout(initStatCountUp, 150);
});
