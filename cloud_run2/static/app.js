/**
 * Gemini Web Application
 * Matches https://gemini.google.com/app
 * With Google Search Grounding (인터넷 실시간 검색) & Fluid Greeting Layout
 */

(function () {
  'use strict';

  // --- User Identification ---
  function getOrCreateUserId() {
    let uid = localStorage.getItem('gemini_user_id');
    if (!uid) {
      uid = 'usr_' + Math.random().toString(36).substring(2, 10) + Date.now().toString(36);
      localStorage.setItem('gemini_user_id', uid);
    }
    return uid;
  }

  // --- State ---
  const state = {
    userId: getOrCreateUserId(),
    currentModel: 'gemini-3.8-flash',
    models: [],
    sessions: [],
    currentSessionId: null,
    currentMessages: [],
    attachedFiles: [],
    useWebSearch: true, // Google 실시간 검색 활성화
    isStreaming: false,
    abortController: null,
    systemInstruction: '',
    temperature: 0.7,
    topP: 0.95,
    userName: localStorage.getItem('gemini_user_name') || 'SH',
    isRecording: false,
    speechRecognition: null,
  };

  // --- DOM Elements ---
  const elements = {
    appRoot: document.getElementById('app-root'),
    
    // Top Bar
    menuBtn: document.getElementById('menu-btn'),
    headerLogoBtn: document.getElementById('header-logo-btn'),
    topNewChatBtn: document.getElementById('top-new-chat-btn'),
    settingsToggleBtn: document.getElementById('settings-toggle-btn'),
    themeToggleBtn: document.getElementById('theme-toggle-btn'),
    userProfileBtn: document.getElementById('user-profile-btn'),
    avatarInitials: document.getElementById('avatar-initials'),
    userNameDisplay: document.getElementById('user-name-display'),

    // Main View
    chatViewport: document.getElementById('chat-viewport'),
    welcomeScreen: document.getElementById('welcome-screen'),
    messagesContainer: document.getElementById('messages-container'),
    messagesInner: document.getElementById('messages-inner'),

    // Capsule Dock
    capsuleDock: document.getElementById('capsule-dock'),
    geminiCapsule: document.getElementById('gemini-capsule'),
    promptInput: document.getElementById('prompt-input'),
    attachedFilesBar: document.getElementById('attached-files-bar'),

    // Capsule Left (Plus Button & Menu)
    plusBtn: document.getElementById('plus-btn'),
    plusPopupMenu: document.getElementById('plus-popup-menu'),
    menuUploadFileBtn: document.getElementById('menu-upload-file-btn'),
    menuSuggestionBtn: document.getElementById('menu-suggestion-btn'),
    menuSettingsBtn: document.getElementById('menu-settings-btn'),
    fileUploadInput: document.getElementById('file-upload-input'),

    // Capsule Right (Search, Model Pill, Mic, Send)
    webSearchToggleBtn: document.getElementById('web-search-toggle-btn'),
    modelPillBtn: document.getElementById('model-pill-btn'),
    modelPillText: document.getElementById('model-pill-text'),
    modelSelectMenu: document.getElementById('model-select-menu'),
    micBtn: document.getElementById('mic-btn'),
    sendBtn: document.getElementById('send-btn'),
    voiceRecordingToast: document.getElementById('voice-recording-toast'),
    voiceStopBtn: document.getElementById('voice-stop-btn'),

    // Left Sidebar Drawer
    sidebarBackdrop: document.getElementById('sidebar-backdrop'),
    sidebarDrawer: document.getElementById('sidebar-drawer'),
    sidebarCloseBtn: document.getElementById('sidebar-close-btn'),
    drawerNewChatBtn: document.getElementById('drawer-new-chat-btn'),
    recentChatList: document.getElementById('recent-chat-list'),
    clearHistoryBtn: document.getElementById('clear-history-btn'),
    sidebarEnvText: document.getElementById('sidebar-env-text'),

    // Right Settings Drawer
    settingsBackdrop: document.getElementById('settings-backdrop'),
    settingsDrawer: document.getElementById('settings-drawer'),
    settingsCloseBtn: document.getElementById('settings-close-btn'),
    settingsSearchToggle: document.getElementById('settings-search-toggle'),
    settingsSystemPrompt: document.getElementById('settings-system-prompt'),
    tempRange: document.getElementById('temp-range'),
    tempValBadge: document.getElementById('temp-val-badge'),
    toppRange: document.getElementById('topp-range'),
    toppValBadge: document.getElementById('topp-val-badge'),
    usernameInput: document.getElementById('username-input'),
    saveUsernameBtn: document.getElementById('save-username-btn'),
    infoApiSource: document.getElementById('info-api-source'),
    infoProjectId: document.getElementById('info-project-id'),
    infoServiceAccount: document.getElementById('info-service-account'),
    infoEnv: document.getElementById('info-env'),

    // Prompt Suggestion Modal
    suggestionModal: document.getElementById('suggestion-modal'),
    modalCloseBtn: document.getElementById('modal-close-btn'),
  };

  // Configure marked options
  if (window.marked) {
    marked.setOptions({
      gfm: true,
      breaks: true,
      headerIds: false,
      mangle: false,
    });
  }

  // --- Initialize ---
  async function init() {
    initTheme();
    initUserName();
    setupEventListeners();
    initSpeechRecognition();

    await checkSystemStatus();
    await fetchModels();
    await loadSessions();

    const savedSessionId = localStorage.getItem('gemini_active_session_id');
    if (savedSessionId && state.sessions.some(s => s.id === savedSessionId)) {
      selectSession(savedSessionId);
    } else {
      startNewChat();
    }
  }

  // --- Theme Management ---
  function initTheme() {
    const savedTheme = localStorage.getItem('gemini_theme') || 'light';
    setTheme(savedTheme);
  }

  function setTheme(theme) {
    if (theme === 'dark') {
      document.body.classList.add('dark-theme');
      document.body.classList.remove('light-theme');
      document.querySelector('.theme-icon.sun').classList.remove('hidden');
      document.querySelector('.theme-icon.moon').classList.add('hidden');
      localStorage.setItem('gemini_theme', 'dark');
    } else {
      document.body.classList.remove('dark-theme');
      document.body.classList.add('light-theme');
      document.querySelector('.theme-icon.sun').classList.add('hidden');
      document.querySelector('.theme-icon.moon').classList.remove('hidden');
      localStorage.setItem('gemini_theme', 'light');
    }
  }

  function toggleTheme() {
    const isDark = document.body.classList.contains('dark-theme');
    setTheme(isDark ? 'light' : 'dark');
  }

  // --- User Name Customization ---
  function initUserName() {
    updateUserNameDisplay(state.userName);
  }

  function updateUserNameDisplay(name) {
    state.userName = name || 'SH';
    localStorage.setItem('gemini_user_name', state.userName);
    elements.userNameDisplay.textContent = state.userName;
    elements.avatarInitials.textContent = state.userName.slice(0, 2).toUpperCase();
    elements.usernameInput.value = state.userName;
  }

  // --- API Calls ---
  async function checkSystemStatus() {
    try {
      const res = await fetch('/api/status');
      const data = await res.json();
      if (data.api_key_configured) {
        elements.sidebarEnvText.textContent = `ADC (${data.project_id || 'GCP'}) 연결됨`;
        if (elements.infoApiSource) elements.infoApiSource.textContent = data.auth_mode || 'ADC (권장 / Keyless)';
        if (elements.infoProjectId) elements.infoProjectId.textContent = data.project_id || 'iceu-songpa15';
        if (elements.infoServiceAccount) elements.infoServiceAccount.textContent = data.service_account || 'Default Compute SA';
        if (elements.infoEnv) elements.infoEnv.textContent = data.environment || 'Cloud Run (Vertex AI Gemini)';
      } else {
        elements.sidebarEnvText.textContent = 'ADC 인증 필요';
        if (elements.infoApiSource) elements.infoApiSource.textContent = '자격증명 없음';
        if (elements.infoProjectId) elements.infoProjectId.textContent = '미설정';
        if (elements.infoServiceAccount) elements.infoServiceAccount.textContent = '미설정';
      }
    } catch (e) {
      console.error('Status check error:', e);
      elements.sidebarEnvText.textContent = '서버 연결 오류';
    }
  }

  async function fetchModels() {
    try {
      const res = await fetch('/api/models');
      const data = await res.json();
      state.models = data.models || [];
      const savedModel = localStorage.getItem('gemini_selected_model') || data.default || 'gemini-3.8-flash';
      selectModel(savedModel);
    } catch (e) {
      console.error('Models fetch error:', e);
    }
  }

  async function loadSessions() {
    try {
      const res = await fetch('/api/sessions', {
        headers: { 'X-User-Id': state.userId }
      });
      const data = await res.json();
      state.sessions = data.sessions || [];
      renderRecentChatList();
    } catch (e) {
      console.error('Load sessions error:', e);
    }
  }

  // --- Model Selection ---
  function selectModel(modelId) {
    state.currentModel = modelId;
    localStorage.setItem('gemini_selected_model', modelId);

    let pillLabel = 'Flash';
    if (modelId === 'gemini-3.8-flash') pillLabel = 'Flash';
    else if (modelId === 'gemini-3.7-flash') pillLabel = '3.7 Flash';
    else if (modelId === 'gemini-2.5-pro') pillLabel = 'Pro';
    else pillLabel = modelId.replace('gemini-', '');

    elements.modelPillText.textContent = pillLabel;

    document.querySelectorAll('.menu-model-item').forEach(el => {
      if (el.getAttribute('data-model') === modelId) {
        el.classList.add('active');
      } else {
        el.classList.remove('active');
      }
    });

    document.querySelectorAll('.model-option-card').forEach(card => {
      if (card.getAttribute('data-model') === modelId) {
        card.classList.add('active');
      } else {
        card.classList.remove('active');
      }
    });
  }

  // --- Web Search Toggle ---
  function setWebSearch(enabled) {
    state.useWebSearch = enabled;
    if (enabled) {
      elements.webSearchToggleBtn.classList.add('active');
      elements.webSearchToggleBtn.title = 'Google 실시간 검색 켜짐';
      elements.settingsSearchToggle.checked = true;
    } else {
      elements.webSearchToggleBtn.classList.remove('active');
      elements.webSearchToggleBtn.title = 'Google 실시간 검색 꺼짐 (클릭하여 켜기)';
      elements.settingsSearchToggle.checked = false;
    }
  }

  function toggleWebSearch() {
    setWebSearch(!state.useWebSearch);
  }

  // --- Session Management ---
  function startNewChat() {
    if (state.isStreaming && state.abortController) {
      state.abortController.abort();
    }
    state.currentSessionId = null;
    state.currentMessages = [];
    state.attachedFiles = [];
    renderAttachedFiles();
    localStorage.removeItem('gemini_active_session_id');

    // Return to Fluid Welcome View Mode (Greeting above capsule, 0 overlap)
    elements.chatViewport.classList.add('welcome-mode');
    elements.welcomeScreen.classList.remove('hidden');
    elements.capsuleDock.classList.remove('bottom-mode');
    elements.capsuleDock.classList.add('centered-mode');

    elements.messagesContainer.classList.add('hidden');
    elements.messagesInner.innerHTML = '';

    elements.promptInput.value = '';
    adjustTextareaHeight();
    updateInputToolsState();
    renderRecentChatList();

    closeSidebar();
    closeSettings();
    elements.promptInput.focus();
  }

  async function selectSession(sessionId) {
    if (state.isStreaming && state.abortController) {
      state.abortController.abort();
    }

    try {
      const res = await fetch(`/api/sessions/${sessionId}`, {
        headers: { 'X-User-Id': state.userId }
      });
      if (!res.ok) {
        startNewChat();
        return;
      }
      const data = await res.json();
      state.currentSessionId = data.id;
      state.currentMessages = data.messages || [];
      if (data.model) {
        selectModel(data.model);
      }
      localStorage.setItem('gemini_active_session_id', data.id);

      closeSidebar();
      renderRecentChatList();
      displayConversation(state.currentMessages);
    } catch (e) {
      console.error('Failed to select session:', e);
      startNewChat();
    }
  }

  async function deleteSession(sessionId, e) {
    if (e) e.stopPropagation();
    if (!confirm('이 대화 내역을 삭제하시겠습니까?')) return;

    try {
      await fetch(`/api/sessions/${sessionId}`, { 
        method: 'DELETE',
        headers: { 'X-User-Id': state.userId }
      });
      state.sessions = state.sessions.filter(s => s.id !== sessionId);
      if (state.currentSessionId === sessionId) {
        startNewChat();
      } else {
        renderRecentChatList();
      }
    } catch (e) {
      console.error('Delete session error:', e);
    }
  }

  async function clearAllSessions() {
    if (!confirm('모든 대화 기록을 영구적으로 삭제하시겠습니까?')) return;
    try {
      await fetch('/api/sessions', { 
        method: 'DELETE',
        headers: { 'X-User-Id': state.userId }
      });
      state.sessions = [];
      startNewChat();
    } catch (e) {
      console.error('Clear all sessions error:', e);
    }
  }

  async function persistSession() {
    if (!state.currentMessages.length) return;

    let title = '새 대화';
    const firstUserMsg = state.currentMessages.find(m => m.role === 'user');
    if (firstUserMsg) {
      title = firstUserMsg.content.slice(0, 24).trim();
      if (firstUserMsg.content.length > 24) title += '...';
    }

    const payload = {
      id: state.currentSessionId,
      user_id: state.userId,
      title: title,
      model: state.currentModel,
      messages: state.currentMessages,
    };

    try {
      const res = await fetch('/api/sessions', {
        method: 'POST',
        headers: { 
          'Content-Type': 'application/json',
          'X-User-Id': state.userId
        },
        body: JSON.stringify(payload),
      });
      const saved = await res.json();
      state.currentSessionId = saved.id;
      localStorage.setItem('gemini_active_session_id', saved.id);
      await loadSessions();
    } catch (e) {
      console.error('Persist session error:', e);
    }
  }

  function renderRecentChatList() {
    elements.recentChatList.innerHTML = '';
    if (state.sessions.length === 0) {
      const emptyItem = document.createElement('div');
      emptyItem.style.padding = '8px 10px';
      emptyItem.style.color = 'var(--text-muted)';
      emptyItem.style.fontSize = '12px';
      emptyItem.textContent = '이전 대화가 없습니다.';
      elements.recentChatList.appendChild(emptyItem);
      return;
    }

    state.sessions.forEach(sess => {
      const item = document.createElement('div');
      item.className = `chat-history-item ${sess.id === state.currentSessionId ? 'active' : ''}`;
      item.innerHTML = `
        <span class="chat-title-span" title="${escapeHtml(sess.title)}">${escapeHtml(sess.title)}</span>
        <button class="chat-del-btn" title="삭제">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polyline points="3 6 5 6 21 6"></polyline>
            <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
          </svg>
        </button>
      `;

      item.addEventListener('click', (e) => {
        if (e.target.closest('.chat-del-btn')) return;
        selectSession(sess.id);
      });

      const delBtn = item.querySelector('.chat-del-btn');
      delBtn.addEventListener('click', (e) => deleteSession(sess.id, e));

      elements.recentChatList.appendChild(item);
    });
  }

  // --- View Mode Transition (Welcome -> Bottom Dock) ---
  function switchToBottomMode() {
    elements.chatViewport.classList.remove('welcome-mode');
    elements.welcomeScreen.classList.add('hidden');
    elements.capsuleDock.classList.remove('centered-mode');
    elements.capsuleDock.classList.add('bottom-mode');
    elements.messagesContainer.classList.remove('hidden');
  }

  function displayConversation(messages) {
    if (!messages.length) {
      startNewChat();
      return;
    }

    switchToBottomMode();
    elements.messagesInner.innerHTML = '';

    messages.forEach(msg => {
      if (msg.role === 'user') {
        renderUserMessage(msg.content);
      } else {
        renderBotMessage(msg.content, state.currentModel, false, msg.search_queries, msg.search_sources);
      }
    });

    scrollToBottom();
  }

  function renderUserMessage(text) {
    const row = document.createElement('div');
    row.className = 'message-row user';
    row.innerHTML = `<div class="user-bubble">${escapeHtml(text)}</div>`;
    elements.messagesInner.appendChild(row);
  }

  function createBotMessagePlaceholder(modelName) {
    const row = document.createElement('div');
    row.className = 'message-row bot';

    const displayName = modelName === 'gemini-3.8-flash' ? 'Gemini 3.8 Flash' :
                        modelName === 'gemini-3.7-flash' ? 'Gemini 3.7 Flash' : modelName;

    row.innerHTML = `
      <div class="gemini-avatar-box">
        <svg width="24" height="24" viewBox="0 0 24 24">
          <path fill="url(#gemini-grad)" d="M12 2L14.4 8.6L21 11L14.4 13.4L12 20L9.6 13.4L3 11L9.6 8.6L12 2Z" />
        </svg>
      </div>
      <div class="gemini-message-body">
        <div class="gemini-meta">
          <span class="gemini-model-badge">${displayName}</span>
        </div>
        <div class="grounding-slot"></div>
        <div class="gemini-text">
          <span class="content-body"></span><span class="typing-cursor"></span>
        </div>
        <div class="message-actions hidden">
          <button class="msg-action-btn copy-full-btn" title="답변 복사">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
              <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
            </svg>
            <span>복사</span>
          </button>
        </div>
      </div>
    `;

    elements.messagesInner.appendChild(row);
    return {
      row,
      groundingSlot: row.querySelector('.grounding-slot'),
      contentBody: row.querySelector('.content-body'),
      cursor: row.querySelector('.typing-cursor'),
      actions: row.querySelector('.message-actions'),
      copyBtn: row.querySelector('.copy-full-btn')
    };
  }

  function renderGroundingCard(slotEl, queries, sources) {
    if (!queries || !queries.length) return;

    let sourcesHtml = '';
    if (sources && sources.length) {
      sourcesHtml = `
        <div class="grounding-sources-row">
          <span class="source-label">출처:</span>
          ${sources.map(s => `<a href="${escapeHtml(s.uri)}" target="_blank" rel="noopener" class="grounding-link" title="${escapeHtml(s.title)}">🌐 ${escapeHtml(s.title)}</a>`).join('')}
        </div>
      `;
    }

    slotEl.innerHTML = `
      <div class="google-grounding-card">
        <div class="grounding-header">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="11" cy="11" r="8"></circle>
            <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
          </svg>
          <span>Google 실시간 검색:</span>
          <span class="grounding-queries-tag">"${escapeHtml(queries.join(', '))}"</span>
        </div>
        ${sourcesHtml}
      </div>
    `;
  }

  function renderBotMessage(text, modelName, isStreaming = false, queries = null, sources = null) {
    const placeholder = createBotMessagePlaceholder(modelName);
    placeholder.contentBody.innerHTML = formatMarkdown(text);

    if (queries && queries.length) {
      renderGroundingCard(placeholder.groundingSlot, queries, sources);
    }

    if (!isStreaming) {
      if (placeholder.cursor) placeholder.cursor.remove();
      placeholder.actions.classList.remove('hidden');
      attachCodeCopyHandlers(placeholder.row);
      setupFullCopyHandler(placeholder.copyBtn, text);
    }
    return placeholder;
  }

  function formatMarkdown(text) {
    if (!window.marked) return escapeHtml(text);
    const raw = marked.parse(text);
    const sanitized = window.DOMPurify ? DOMPurify.sanitize(raw) : raw;

    const div = document.createElement('div');
    div.innerHTML = sanitized;

    div.querySelectorAll('pre code').forEach((codeEl) => {
      const preEl = codeEl.parentElement;
      const langMatch = (codeEl.className || '').match(/language-([\w-]+)/);
      const lang = langMatch ? langMatch[1] : 'code';

      if (window.hljs) {
        hljs.highlightElement(codeEl);
      }

      const wrapper = document.createElement('div');
      wrapper.className = 'code-block-wrapper';
      wrapper.innerHTML = `
        <div class="code-block-header">
          <span class="code-lang">${lang}</span>
          <button class="copy-code-btn" type="button">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
              <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
            </svg>
            <span>코드 복사</span>
          </button>
        </div>
      `;
      preEl.parentNode.insertBefore(wrapper, preEl);
      wrapper.appendChild(preEl);
    });

    return div.innerHTML;
  }

  function attachCodeCopyHandlers(scope) {
    scope.querySelectorAll('.copy-code-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const wrapper = btn.closest('.code-block-wrapper');
        const codeText = wrapper.querySelector('pre code').textContent;
        navigator.clipboard.writeText(codeText).then(() => {
          const orig = btn.innerHTML;
          btn.innerHTML = `<span style="color: #81c995;">✓ 복사됨</span>`;
          setTimeout(() => { btn.innerHTML = orig; }, 2000);
        });
      });
    });
  }

  function setupFullCopyHandler(btn, text) {
    if (!btn) return;
    btn.addEventListener('click', () => {
      navigator.clipboard.writeText(text).then(() => {
        const orig = btn.innerHTML;
        btn.innerHTML = `<span style="color: #81c995;">✓ 복사 완료</span>`;
        setTimeout(() => { btn.innerHTML = orig; }, 2000);
      });
    });
  }

  function scrollToBottom() {
    elements.chatViewport.scrollTop = elements.chatViewport.scrollHeight;
  }

  // --- Send Message & Stream ---
  async function sendMessage() {
    const text = elements.promptInput.value.trim();
    if ((!text && state.attachedFiles.length === 0) || state.isStreaming) return;

    elements.promptInput.value = '';
    adjustTextareaHeight();
    updateInputToolsState();

    switchToBottomMode();

    let displayPrompt = text;
    if (state.attachedFiles.length > 0) {
      const filesInfo = state.attachedFiles.map(f => `[📄 ${f.filename}]`).join(' ');
      displayPrompt = `${filesInfo}\n${text}`;
    }

    state.currentMessages.push({ role: 'user', content: displayPrompt });
    renderUserMessage(displayPrompt);
    scrollToBottom();

    const filesToSend = [...state.attachedFiles];
    state.attachedFiles = [];
    renderAttachedFiles();

    state.isStreaming = true;
    state.abortController = new AbortController();
    setStreamingUI(true);

    const placeholder = createBotMessagePlaceholder(state.currentModel);
    let accumulatedText = '';
    let latestQueries = [];
    let latestSources = [];

    try {
      const payload = {
        model: state.currentModel,
        messages: state.currentMessages,
        attached_files: filesToSend.length ? filesToSend : undefined,
        system_instruction: state.systemInstruction || undefined,
        use_web_search: state.useWebSearch,
        temperature: state.temperature,
        top_p: state.topP,
      };

      const response = await fetch('/api/chat/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
        signal: state.abortController.signal
      });

      if (!response.ok) {
        const errJson = await response.json().catch(() => ({}));
        throw new Error(errJson.detail || `서버 응답 오류 (${response.status})`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          const trimmed = line.trim();
          if (!trimmed.startsWith('data: ')) continue;
          const jsonStr = trimmed.slice(6);
          if (!jsonStr) continue;

          try {
            const data = JSON.parse(jsonStr);
            if (data.chunk) {
              accumulatedText += data.chunk;
              placeholder.contentBody.innerHTML = formatMarkdown(accumulatedText);
              scrollToBottom();
            } else if (data.search_queries && data.search_queries.length) {
              latestQueries = data.search_queries;
              latestSources = data.search_sources || [];
              renderGroundingCard(placeholder.groundingSlot, latestQueries, latestSources);
            } else if (data.error) {
              accumulatedText += `\n\n> ⚠️ **오류**: ${data.error}`;
              placeholder.contentBody.innerHTML = formatMarkdown(accumulatedText);
            }
          } catch (e) {
            console.error('SSE JSON parse error:', e);
          }
        }
      }

    } catch (err) {
      if (err.name === 'AbortError') {
        accumulatedText += '\n\n*(생성이 중단되었습니다)*';
      } else {
        accumulatedText += `\n\n> ⚠️ **오류 발생**: ${err.message}`;
      }
      placeholder.contentBody.innerHTML = formatMarkdown(accumulatedText);
    } finally {
      if (placeholder.cursor) placeholder.cursor.remove();
      placeholder.actions.classList.remove('hidden');
      attachCodeCopyHandlers(placeholder.row);
      setupFullCopyHandler(placeholder.copyBtn, accumulatedText);

      // Save message with search metadata
      state.currentMessages.push({
        role: 'model',
        content: accumulatedText,
        search_queries: latestQueries.length ? latestQueries : undefined,
        search_sources: latestSources.length ? latestSources : undefined,
      });

      state.isStreaming = false;
      state.abortController = null;
      setStreamingUI(false);
      scrollToBottom();

      await persistSession();
    }
  }

  function stopStreaming() {
    if (state.isStreaming && state.abortController) {
      state.abortController.abort();
    }
  }

  function setStreamingUI(streaming) {
    const arrowIcon = elements.sendBtn.querySelector('.send-arrow-icon');
    const stopIcon = elements.sendBtn.querySelector('.stop-sq-icon');

    if (streaming) {
      elements.sendBtn.classList.remove('hidden');
      elements.sendBtn.classList.add('streaming');
      arrowIcon.classList.add('hidden');
      stopIcon.classList.remove('hidden');
      elements.sendBtn.title = '응답 생성 중지';
    } else {
      elements.sendBtn.classList.remove('streaming');
      arrowIcon.classList.remove('hidden');
      stopIcon.classList.add('hidden');
      elements.sendBtn.title = '메시지 전송';
      updateInputToolsState();
    }
  }

  function updateInputToolsState() {
    if (state.isStreaming) return;
    const hasText = elements.promptInput.value.trim().length > 0 || state.attachedFiles.length > 0;
    if (hasText) {
      elements.sendBtn.classList.remove('hidden');
    } else {
      elements.sendBtn.classList.add('hidden');
    }
  }

  function adjustTextareaHeight() {
    const el = elements.promptInput;
    if (!el) return;
    el.style.height = 'auto';
    if (!el.value || el.value.length === 0) {
      el.style.height = window.innerWidth <= 768 ? '26px' : '28px';
    } else {
      const maxH = window.innerWidth <= 768 ? 120 : 180;
      const newH = Math.min(el.scrollHeight, maxH);
      el.style.height = `${newH}px`;
    }
  }

  // --- File Attachment Handler ---
  function handleFileSelect(event) {
    const files = Array.from(event.target.files);
    if (!files.length) return;

    files.forEach(file => {
      const reader = new FileReader();
      reader.onload = (e) => {
        state.attachedFiles.push({
          filename: file.name,
          content: e.target.result,
          size: file.size
        });
        renderAttachedFiles();
        updateInputToolsState();
      };
      reader.readAsText(file);
    });

    event.target.value = '';
    elements.plusPopupMenu.classList.add('hidden');
  }

  function renderAttachedFiles() {
    elements.attachedFilesBar.innerHTML = '';
    if (!state.attachedFiles.length) {
      elements.attachedFilesBar.classList.add('hidden');
      return;
    }

    elements.attachedFilesBar.classList.remove('hidden');
    state.attachedFiles.forEach((f, idx) => {
      const chip = document.createElement('div');
      chip.className = 'file-chip';
      chip.innerHTML = `
        <span>📄 ${escapeHtml(f.filename)}</span>
        <span class="file-chip-remove" data-idx="${idx}" title="삭제">✕</span>
      `;
      chip.querySelector('.file-chip-remove').addEventListener('click', () => {
        state.attachedFiles.splice(idx, 1);
        renderAttachedFiles();
        updateInputToolsState();
      });
      elements.attachedFilesBar.appendChild(chip);
    });
  }

  // --- Web Speech Recognition (Microphone Feature) ---
  function initSpeechRecognition() {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      console.warn('Web Speech API is not supported in this browser.');
      return;
    }

    const recognition = new SpeechRecognition();
    recognition.lang = 'ko-KR';
    recognition.continuous = false;
    recognition.interimResults = true;

    recognition.onstart = () => {
      state.isRecording = true;
      elements.micBtn.classList.add('recording');
      elements.voiceRecordingToast.classList.remove('hidden');
    };

    recognition.onresult = (event) => {
      let transcript = '';
      for (let i = event.resultIndex; i < event.results.length; i++) {
        transcript += event.results[i][0].transcript;
      }
      elements.promptInput.value = transcript;
      adjustTextareaHeight();
      updateInputToolsState();
    };

    recognition.onerror = (event) => {
      console.error('Speech error:', event.error);
      stopRecording();
    };

    recognition.onend = () => {
      stopRecording();
    };

    state.speechRecognition = recognition;
  }

  function toggleVoiceRecording() {
    if (!state.speechRecognition) {
      alert('현재 브라우저 환경에서는 Web Speech API를 지원하지 않습니다.\n텍스트를 직접 입력해 주세요.');
      return;
    }

    if (state.isRecording) {
      state.speechRecognition.stop();
    } else {
      try {
        state.speechRecognition.start();
      } catch (e) {
        console.error('Failed to start speech:', e);
      }
    }
  }

  function stopRecording() {
    state.isRecording = false;
    elements.micBtn.classList.remove('recording');
    elements.voiceRecordingToast.classList.add('hidden');
  }

  // --- Drawer Open / Close ---
  function openSidebar() {
    elements.sidebarDrawer.classList.add('open');
    elements.sidebarBackdrop.classList.add('active');
  }

  function closeSidebar() {
    elements.sidebarDrawer.classList.remove('open');
    elements.sidebarBackdrop.classList.remove('active');
  }

  function openSettings() {
    elements.settingsDrawer.classList.add('open');
    elements.settingsBackdrop.classList.add('active');
  }

  function closeSettings() {
    elements.settingsDrawer.classList.remove('open');
    elements.settingsBackdrop.classList.remove('active');
  }

  // --- Event Listeners Setup ---
  function setupEventListeners() {
    // 1. Top Bar Buttons
    elements.menuBtn.addEventListener('click', openSidebar);
    elements.sidebarCloseBtn.addEventListener('click', closeSidebar);
    elements.sidebarBackdrop.addEventListener('click', closeSidebar);

    elements.topNewChatBtn.addEventListener('click', startNewChat);
    elements.drawerNewChatBtn.addEventListener('click', startNewChat);
    elements.headerLogoBtn.addEventListener('click', startNewChat);

    elements.settingsToggleBtn.addEventListener('click', openSettings);
    elements.settingsCloseBtn.addEventListener('click', closeSettings);
    elements.settingsBackdrop.addEventListener('click', closeSettings);

    elements.themeToggleBtn.addEventListener('click', toggleTheme);

    // Profile Click
    elements.userProfileBtn.addEventListener('click', () => {
      openSettings();
      elements.usernameInput.focus();
    });

    elements.saveUsernameBtn.addEventListener('click', () => {
      const val = elements.usernameInput.value.trim() || 'SH';
      updateUserNameDisplay(val);
      closeSettings();
    });

    // 2. Plus Button & Popover Menu
    elements.plusBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      elements.plusPopupMenu.classList.toggle('hidden');
      elements.modelSelectMenu.classList.add('hidden');
    });

    elements.menuUploadFileBtn.addEventListener('click', () => {
      elements.fileUploadInput.click();
    });

    elements.fileUploadInput.addEventListener('change', handleFileSelect);

    elements.menuSuggestionBtn.addEventListener('click', () => {
      elements.plusPopupMenu.classList.add('hidden');
      elements.suggestionModal.classList.remove('hidden');
    });

    elements.menuSettingsBtn.addEventListener('click', () => {
      elements.plusPopupMenu.classList.add('hidden');
      openSettings();
    });

    // 3. Google Web Search Toggle
    elements.webSearchToggleBtn.addEventListener('click', toggleWebSearch);
    elements.settingsSearchToggle.addEventListener('change', (e) => {
      setWebSearch(e.target.checked);
    });

    // 4. Model Pill Dropdown
    elements.modelPillBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      elements.modelSelectMenu.classList.toggle('hidden');
      elements.plusPopupMenu.classList.add('hidden');
    });

    elements.modelSelectMenu.querySelectorAll('.menu-model-item').forEach(item => {
      item.addEventListener('click', () => {
        const model = item.getAttribute('data-model');
        selectModel(model);
        elements.modelSelectMenu.classList.add('hidden');
      });
    });

    document.querySelectorAll('.model-option-card').forEach(card => {
      card.addEventListener('click', () => {
        const model = card.getAttribute('data-model');
        selectModel(model);
      });
    });

    // Document click to close popovers
    document.addEventListener('click', (e) => {
      if (!elements.plusBtn.contains(e.target) && !elements.plusPopupMenu.contains(e.target)) {
        elements.plusPopupMenu.classList.add('hidden');
      }
      if (!elements.modelPillBtn.contains(e.target) && !elements.modelSelectMenu.contains(e.target)) {
        elements.modelSelectMenu.classList.add('hidden');
      }
    });

    // 5. Microphone & Voice
    elements.micBtn.addEventListener('click', toggleVoiceRecording);
    elements.voiceStopBtn.addEventListener('click', stopRecording);

    // 6. Input Textarea
    elements.promptInput.addEventListener('input', () => {
      adjustTextareaHeight();
      updateInputToolsState();
    });

    elements.promptInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        if (!state.isStreaming) {
          sendMessage();
        }
      }
    });

    // 7. Send / Stop Button
    elements.sendBtn.addEventListener('click', () => {
      if (state.isStreaming) {
        stopStreaming();
      } else {
        sendMessage();
      }
    });

    // 8. Clear History
    elements.clearHistoryBtn.addEventListener('click', clearAllSessions);

    // 9. Persona Chips in Settings
    document.querySelectorAll('.persona-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('.persona-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        const instruction = btn.getAttribute('data-instruction') || '';
        elements.settingsSystemPrompt.value = instruction;
        state.systemInstruction = instruction;
      });
    });

    elements.settingsSystemPrompt.addEventListener('input', (e) => {
      state.systemInstruction = e.target.value;
    });

    // 10. Hyperparameter Sliders
    elements.tempRange.addEventListener('input', (e) => {
      state.temperature = parseFloat(e.target.value);
      elements.tempValBadge.textContent = state.temperature.toFixed(1);
    });

    elements.toppRange.addEventListener('input', (e) => {
      state.topP = parseFloat(e.target.value);
      elements.toppValBadge.textContent = state.topP.toFixed(2);
    });

    // 11. Suggestion Modal
    elements.modalCloseBtn.addEventListener('click', () => {
      elements.suggestionModal.classList.add('hidden');
    });

    elements.suggestionModal.addEventListener('click', (e) => {
      if (e.target === elements.suggestionModal) {
        elements.suggestionModal.classList.add('hidden');
      }
    });

    elements.suggestionModal.querySelectorAll('.modal-item').forEach(item => {
      item.addEventListener('click', () => {
        const prompt = item.getAttribute('data-prompt');
        if (prompt) {
          elements.promptInput.value = prompt;
          adjustTextareaHeight();
          updateInputToolsState();
          elements.suggestionModal.classList.add('hidden');
          sendMessage();
        }
      });
    });
  }

  // --- Helper: Escape HTML ---
  function escapeHtml(str) {
    if (!str) return '';
    return str
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  // Run on DOM ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

})();
