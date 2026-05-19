/**
 * Kudos System — Frontend Application Logic
 * Handles session management, API calls, DOM rendering, and admin moderation.
 */

// ─── State ──────────────────────────────────────────────────────────────────

const state = {
  currentUser: null,
  users: [],
  feedInterval: null,
  pendingHideId: null,
  pendingDeleteId: null,
};

const API = '';

// ─── Initialization ─────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', async () => {
  await loadUsers();
  checkExistingSession();
  bindEvents();
});

async function loadUsers() {
  try {
    const res = await fetch(`${API}/api/users`);
    state.users = await res.json();
    populateLoginSelect();
  } catch (err) {
    showToast('Failed to load users. Is the server running?', 'error');
  }
}

function checkExistingSession() {
  const saved = localStorage.getItem('kudos_user');
  if (saved) {
    try {
      state.currentUser = JSON.parse(saved);
      showDashboard();
    } catch {
      localStorage.removeItem('kudos_user');
    }
  }
}

// ─── Login ──────────────────────────────────────────────────────────────────

function populateLoginSelect() {
  const select = document.getElementById('login-user-select');
  state.users.forEach(user => {
    const opt = document.createElement('option');
    opt.value = user.id;
    opt.textContent = `${user.name}${user.role === 'admin' ? ' ★' : ''}`;
    select.appendChild(opt);
  });
}

function handleLogin() {
  const select = document.getElementById('login-user-select');
  const userId = parseInt(select.value);
  if (!userId) return;

  state.currentUser = state.users.find(u => u.id === userId);
  localStorage.setItem('kudos_user', JSON.stringify(state.currentUser));
  showDashboard();
}

function handleLogout() {
  state.currentUser = null;
  localStorage.removeItem('kudos_user');
  clearInterval(state.feedInterval);
  document.getElementById('dashboard').classList.remove('active');
  document.getElementById('login-screen').style.display = 'flex';
  showToast('Signed out successfully.', 'info');
}

// ─── Dashboard ──────────────────────────────────────────────────────────────

function showDashboard() {
  const user = state.currentUser;
  document.getElementById('login-screen').style.display = 'none';
  document.getElementById('dashboard').classList.add('active');

  // Header
  const avatar = document.getElementById('header-avatar');
  avatar.textContent = getInitials(user.name);
  avatar.style.backgroundColor = user.avatar_color;

  document.getElementById('header-user-name').textContent = user.name;

  const adminBadge = document.getElementById('header-admin-badge');
  const moderatedTab = document.getElementById('tab-moderated');
  if (user.role === 'admin') {
    adminBadge.style.display = 'inline';
    moderatedTab.style.display = 'inline-flex';
  } else {
    adminBadge.style.display = 'none';
    moderatedTab.style.display = 'none';
  }

  populateRecipientSelect();
  loadFeed();

  // Auto-refresh every 15 seconds
  clearInterval(state.feedInterval);
  state.feedInterval = setInterval(loadFeed, 15000);
}

function populateRecipientSelect() {
  const select = document.getElementById('recipient-select');
  // Clear existing options except the first placeholder
  while (select.options.length > 1) select.remove(1);

  state.users
    .filter(u => u.id !== state.currentUser.id)
    .forEach(user => {
      const opt = document.createElement('option');
      opt.value = user.id;
      opt.textContent = user.name;
      select.appendChild(opt);
    });
}

// ─── Feed ───────────────────────────────────────────────────────────────────

async function loadFeed() {
  try {
    const res = await fetch(`${API}/api/kudos`);
    const data = await res.json();
    renderFeed(data.kudos);
  } catch (err) {
    console.error('Feed load error:', err);
  }
}

function renderFeed(kudosList) {
  const container = document.getElementById('feed-list');

  if (!kudosList || kudosList.length === 0) {
    container.innerHTML = `
      <div class="empty-state">
        <div class="icon">💬</div>
        <p>No kudos yet. Be the first to appreciate a colleague!</p>
      </div>`;
    return;
  }

  container.innerHTML = kudosList.map(k => createKudosCard(k, false)).join('');
}

function createKudosCard(k, isHidden) {
  const isAdmin = state.currentUser && state.currentUser.role === 'admin';
  const timeAgo = formatTimeAgo(k.created_at);

  let actions = '';
  if (isAdmin && !isHidden) {
    actions = `
      <div class="kudos-actions">
        <button class="btn btn-danger btn-sm" onclick="openHideModal(${k.id})">Hide</button>
      </div>`;
  }
  if (isAdmin && isHidden) {
    actions = `
      <div class="kudos-actions">
        <button class="btn btn-success btn-sm" onclick="restoreKudos(${k.id})">Restore</button>
        <button class="btn btn-danger btn-sm" onclick="openDeleteModal(${k.id})">Delete</button>
      </div>`;
  }

  let moderationInfo = '';
  if (isHidden && k.moderation_reason) {
    moderationInfo = `
      <div class="moderation-info">
        Reason: ${escapeHtml(k.moderation_reason)}
        ${k.moderator_name ? ` · By ${escapeHtml(k.moderator_name)}` : ''}
      </div>`;
  }

  return `
    <div class="kudos-card" id="kudos-${k.id}">
      <div class="kudos-card-header">
        <div class="kudos-arrow">
          <div class="avatar" style="background-color: ${k.sender_color}">${getInitials(k.sender_name)}</div>
          <span class="user-name">${escapeHtml(k.sender_name)}</span>
          <span class="arrow">→</span>
          <div class="avatar" style="background-color: ${k.receiver_color}">${getInitials(k.receiver_name)}</div>
          <span class="user-name">${escapeHtml(k.receiver_name)}</span>
        </div>
      </div>
      <div class="kudos-message">${escapeHtml(k.message)}</div>
      <div class="kudos-footer">
        <span class="kudos-time">${timeAgo}</span>
        ${actions}
      </div>
      ${moderationInfo}
    </div>`;
}

// ─── Submit Kudos ───────────────────────────────────────────────────────────

async function handleSubmit(e) {
  e.preventDefault();
  clearErrors();

  const receiverId = parseInt(document.getElementById('recipient-select').value);
  const message = document.getElementById('kudos-message').value.trim();

  // Client-side validation
  let valid = true;

  if (!receiverId) {
    showError('recipient-error', 'Please select a colleague.');
    valid = false;
  }

  if (message.length < 5) {
    showError('message-error', 'Message must be at least 5 characters.');
    valid = false;
  }

  if (message.length > 500) {
    showError('message-error', 'Message must be 500 characters or fewer.');
    valid = false;
  }

  if (!valid) return;

  // Disable submit
  const btn = document.getElementById('submit-btn');
  const btnText = document.getElementById('submit-text');
  const spinner = document.getElementById('submit-spinner');
  btn.disabled = true;
  btnText.style.display = 'none';
  spinner.style.display = 'inline-block';

  try {
    const res = await fetch(`${API}/api/kudos`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        sender_id: state.currentUser.id,
        receiver_id: receiverId,
        message: message,
      }),
    });

    const data = await res.json();

    if (!res.ok) {
      showToast(data.details || data.error || 'Something went wrong.', 'error');
      return;
    }

    // Success!
    showToast('Kudos sent! 🎉', 'success');
    document.getElementById('kudos-form').reset();
    document.getElementById('char-count').textContent = '0';
    loadFeed();
  } catch (err) {
    showToast('Network error. Please try again.', 'error');
  } finally {
    btn.disabled = false;
    btnText.style.display = 'inline';
    spinner.style.display = 'none';
  }
}

// ─── Admin: Moderation ──────────────────────────────────────────────────────

function openHideModal(kudosId) {
  state.pendingHideId = kudosId;
  document.getElementById('hide-reason').value = '';
  document.getElementById('hide-modal').classList.add('active');
}

async function confirmHide() {
  const reason = document.getElementById('hide-reason').value.trim();

  try {
    const res = await fetch(`${API}/api/kudos/${state.pendingHideId}/hide`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        moderated_by: state.currentUser.id,
        reason: reason,
      }),
    });

    if (res.ok) {
      showToast('Kudos hidden from public feed.', 'info');
      loadFeed();
    } else {
      const data = await res.json();
      showToast(data.details || 'Failed to hide kudos.', 'error');
    }
  } catch {
    showToast('Network error.', 'error');
  }

  closeHideModal();
}

function closeHideModal() {
  state.pendingHideId = null;
  document.getElementById('hide-modal').classList.remove('active');
}

async function restoreKudos(kudosId) {
  try {
    const res = await fetch(`${API}/api/kudos/${kudosId}/restore`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ moderated_by: state.currentUser.id }),
    });

    if (res.ok) {
      showToast('Kudos restored to public feed.', 'success');
      loadModerated();
      loadFeed();
    } else {
      showToast('Failed to restore kudos.', 'error');
    }
  } catch {
    showToast('Network error.', 'error');
  }
}

function openDeleteModal(kudosId) {
  state.pendingDeleteId = kudosId;
  document.getElementById('delete-modal').classList.add('active');
}

async function confirmDelete() {
  try {
    const res = await fetch(
      `${API}/api/kudos/${state.pendingDeleteId}?moderated_by=${state.currentUser.id}`,
      { method: 'DELETE' }
    );

    if (res.ok) {
      showToast('Kudos permanently deleted.', 'info');
      loadModerated();
    } else {
      showToast('Failed to delete kudos.', 'error');
    }
  } catch {
    showToast('Network error.', 'error');
  }

  closeDeleteModal();
}

function closeDeleteModal() {
  state.pendingDeleteId = null;
  document.getElementById('delete-modal').classList.remove('active');
}

async function loadModerated() {
  try {
    const res = await fetch(`${API}/api/kudos/hidden`);
    const data = await res.json();
    renderModerated(data);
  } catch {
    console.error('Failed to load moderated kudos');
  }
}

function renderModerated(kudosList) {
  const container = document.getElementById('moderated-list');

  if (!kudosList || kudosList.length === 0) {
    container.innerHTML = `
      <div class="empty-state">
        <div class="icon">✅</div>
        <p>No hidden kudos. Everything looks good!</p>
      </div>`;
    return;
  }

  container.innerHTML = kudosList.map(k => createKudosCard(k, true)).join('');
}

// ─── Tabs ───────────────────────────────────────────────────────────────────

function switchTab(tab) {
  document.querySelectorAll('.feed-tab').forEach(t => t.classList.remove('active'));
  document.querySelector(`[data-tab="${tab}"]`).classList.add('active');

  if (tab === 'feed') {
    document.getElementById('feed-list').style.display = 'flex';
    document.getElementById('moderated-list').style.display = 'none';
    loadFeed();
  } else {
    document.getElementById('feed-list').style.display = 'none';
    document.getElementById('moderated-list').style.display = 'flex';
    loadModerated();
  }
}

// ─── Event Binding ──────────────────────────────────────────────────────────

function bindEvents() {
  // Login
  const loginSelect = document.getElementById('login-user-select');
  const loginBtn = document.getElementById('login-btn');
  loginSelect.addEventListener('change', () => {
    loginBtn.disabled = !loginSelect.value;
  });
  loginBtn.addEventListener('click', handleLogin);

  // Logout
  document.getElementById('logout-btn').addEventListener('click', handleLogout);

  // Form
  document.getElementById('kudos-form').addEventListener('submit', handleSubmit);

  // Character counter
  const textarea = document.getElementById('kudos-message');
  textarea.addEventListener('input', () => {
    const count = textarea.value.length;
    const counter = document.getElementById('char-count');
    counter.textContent = count;
    const parent = counter.parentElement;
    parent.classList.remove('warning', 'danger');
    if (count > 450) parent.classList.add('danger');
    else if (count > 350) parent.classList.add('warning');
  });

  // Tabs
  document.querySelectorAll('.feed-tab').forEach(tab => {
    tab.addEventListener('click', () => switchTab(tab.dataset.tab));
  });

  // Modals
  document.getElementById('hide-cancel').addEventListener('click', closeHideModal);
  document.getElementById('hide-confirm').addEventListener('click', confirmHide);
  document.getElementById('delete-cancel').addEventListener('click', closeDeleteModal);
  document.getElementById('delete-confirm').addEventListener('click', confirmDelete);

  // Close modals on overlay click
  document.getElementById('hide-modal').addEventListener('click', e => {
    if (e.target === e.currentTarget) closeHideModal();
  });
  document.getElementById('delete-modal').addEventListener('click', e => {
    if (e.target === e.currentTarget) closeDeleteModal();
  });
}

// ─── Utilities ──────────────────────────────────────────────────────────────

function getInitials(name) {
  return name
    .split(' ')
    .map(w => w[0])
    .join('')
    .toUpperCase()
    .slice(0, 2);
}

function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

function formatTimeAgo(dateStr) {
  const date = new Date(dateStr + (dateStr.includes('Z') ? '' : 'Z'));
  const now = new Date();
  const diff = Math.floor((now - date) / 1000);

  if (diff < 60) return 'Just now';
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  if (diff < 604800) return `${Math.floor(diff / 86400)}d ago`;
  return date.toLocaleDateString('en-NZ', { day: 'numeric', month: 'short' });
}

function showError(elementId, message) {
  const el = document.getElementById(elementId);
  el.textContent = message;
  el.classList.add('visible');
}

function clearErrors() {
  document.querySelectorAll('.error-message').forEach(el => {
    el.classList.remove('visible');
    el.textContent = '';
  });
}

// ─── Toast Notifications ────────────────────────────────────────────────────

function showToast(message, type = 'info') {
  const container = document.getElementById('toast-container');

  const icons = { success: '✅', error: '❌', info: 'ℹ️' };

  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.innerHTML = `
    <span class="toast-icon">${icons[type] || icons.info}</span>
    <span>${escapeHtml(message)}</span>
    <button class="toast-close" onclick="this.parentElement.remove()">×</button>
  `;

  container.appendChild(toast);

  // Auto-dismiss after 4 seconds
  setTimeout(() => {
    if (toast.parentElement) {
      toast.style.opacity = '0';
      toast.style.transform = 'translateX(100px)';
      toast.style.transition = 'all 0.3s ease';
      setTimeout(() => toast.remove(), 300);
    }
  }, 4000);
}
