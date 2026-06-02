(function() {
    'use strict';

    const CONFIG = {
        apiBaseUrl: '/api/chat/',
        position: 'bottom-right',
        primaryColor: '#16a34a',
        secondaryColor: '#0d9488',
        botName: 'Dr. Assistant',
        // Avatar dentiste professionnel
        botAvatar: `<img src="/static/rdv/images/dentist-avatar.png" 
            style="width:36px;height:36px;border-radius:50%;object-fit:cover;border:2px solid rgba(255,255,255,0.3);" 
            alt="Dr. Assistant">`,
        userAvatar: '👤',
        greetingDelay: 3000,
    };

    let state = {
        isOpen: false,
        sessionId: null,
        messages: [],
        isTyping: false,
        conversationId: null,
    };

    function init() {
        state.sessionId = getSessionId();
        createWidgetDOM();
        loadHistory();
        setTimeout(() => {
            if (state.messages.length === 0) {
                addBotMessage(
                    "Bonjour ! Je suis l'assistant virtuel du Centre Dentaire. Comment puis-je vous aider ?",
                    ['Voir les services', 'Prendre un RDV', 'Horaires', 'Urgence']
                );
            }
        }, CONFIG.greetingDelay);
    }

    function getSessionId() {
        let sid = localStorage.getItem('chatbot_session_id');
        if (!sid) {
            sid = 'cb_' + Math.random().toString(36).substring(2, 15) + Math.random().toString(36).substring(2, 15);
            localStorage.setItem('chatbot_session_id', sid);
        }
        return sid;
    }

    function createWidgetDOM() {
        const styles = `
            <style>
                #chatbot-widget {
                    --cb-primary: ${CONFIG.primaryColor};
                    --cb-secondary: ${CONFIG.secondaryColor};
                    --cb-bg: #ffffff;
                    --cb-text: #1e293b;
                    --cb-text-light: #64748b;
                    --cb-border: #e2e8f0;
                    --cb-shadow: 0 10px 40px rgba(0,0,0,0.15);
                    --cb-radius: 16px;
                    position: fixed;
                    ${CONFIG.position === 'bottom-left' ? 'left: 20px;' : 'right: 20px;'}
                    bottom: 20px;
                    z-index: 9999;
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                }
                .cb-bubble {
                    width: 68px;
                    height: 68px;
                    border-radius: 50%;
                    background: linear-gradient(135deg, var(--cb-primary), var(--cb-secondary));
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    cursor: pointer;
                    box-shadow: 
                        0 6px 25px rgba(22, 163, 74, 0.5),
                        0 0 0 4px rgba(22, 163, 74, 0.15),
                        inset 0 2px 4px rgba(255,255,255,0.3);
                    transition: all 0.4s cubic-bezier(0.34, 1.56, 0.64, 1);
                    position: relative;
                    overflow: hidden;
                    border: 3px solid white;
                }
                .cb-bubble::after {
                    content: '';
                    position: absolute;
                    bottom: 2px;
                    right: 2px;
                    width: 16px;
                    height: 16px;
                    background: #4ade80;
                    border-radius: 50%;
                    border: 3px solid white;
                    animation: cb-pulse 2s infinite;
                    z-index: 10;
                }
                @keyframes cb-pulse {
                    0%, 100% { box-shadow: 0 0 0 0 rgba(74, 222, 128, 0.7); }
                    50% { box-shadow: 0 0 0 10px rgba(74, 222, 128, 0); }
                }
                .cb-bubble:hover { 
                    transform: scale(1.15) translateY(-3px);
                    box-shadow: 
                        0 10px 35px rgba(22, 163, 74, 0.6),
                        0 0 0 8px rgba(22, 163, 74, 0.2),
                        inset 0 2px 4px rgba(255,255,255,0.4);
                }
                .cb-window {
                    position: absolute;
                    ${CONFIG.position === 'bottom-left' ? 'left: 0;' : 'right: 0;'}
                    bottom: 75px;
                    width: 380px;
                    height: 550px;
                    background: var(--cb-bg);
                    border-radius: var(--cb-radius);
                    box-shadow: var(--cb-shadow);
                    display: flex;
                    flex-direction: column;
                    overflow: hidden;
                    opacity: 0;
                    transform: translateY(20px) scale(0.95);
                    pointer-events: none;
                    transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
                }
                .cb-window.open {
                    opacity: 1;
                    transform: translateY(0) scale(1);
                    pointer-events: all;
                }
                .cb-header {
                    background: linear-gradient(135deg, var(--cb-primary), var(--cb-secondary));
                    color: white;
                    padding: 16px 20px;
                    display: flex;
                    align-items: center;
                    gap: 12px;
                }
                .cb-header-avatar {
                    background: rgba(255,255,255,0.25);
                    border-radius: 50%;
                    padding: 2px;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    width: 44px;
                    height: 44px;
                    overflow: hidden;
                    border: 2px solid rgba(255,255,255,0.4);
                }
                .cb-header-info { flex: 1; }
                .cb-header-name { font-weight: 600; font-size: 15px; }
                .cb-header-status {
                    font-size: 12px;
                    opacity: 0.9;
                    display: flex;
                    align-items: center;
                    gap: 5px;
                }
                .cb-status-dot {
                    width: 8px;
                    height: 8px;
                    background: #4ade80;
                    border-radius: 50%;
                    animation: cb-blink 2s infinite;
                }
                @keyframes cb-blink {
                    0%, 100% { opacity: 1; }
                    50% { opacity: 0.5; }
                }
                .cb-header-close {
                    background: none;
                    border: none;
                    color: white;
                    font-size: 24px;
                    cursor: pointer;
                    padding: 4px;
                    opacity: 0.8;
                }
                .cb-header-close:hover { opacity: 1; }
                .cb-messages {
                    flex: 1;
                    overflow-y: auto;
                    padding: 16px;
                    display: flex;
                    flex-direction: column;
                    gap: 12px;
                }
                .cb-message {
                    display: flex;
                    gap: 8px;
                    max-width: 85%;
                    animation: cb-fade-in 0.3s ease;
                }
                @keyframes cb-fade-in {
                    from { opacity: 0; transform: translateY(10px); }
                    to { opacity: 1; transform: translateY(0); }
                }
                .cb-message.user { align-self: flex-end; flex-direction: row-reverse; }
                .cb-message.bot { align-self: flex-start; }
                .cb-message-avatar {
                    width: 32px;
                    height: 32px;
                    border-radius: 50%;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    font-size: 16px;
                    flex-shrink: 0;
                    overflow: hidden;
                }
                .cb-message.bot .cb-message-avatar {
                    background: linear-gradient(135deg, var(--cb-primary), var(--cb-secondary));
                    border: 2px solid rgba(255,255,255,0.5);
                    box-shadow: 0 2px 8px rgba(0,0,0,0.15);
                }
                .cb-message.user .cb-message-avatar { background: #e2e8f0; }
                .cb-message-content {
                    background: #f1f5f9;
                    padding: 10px 14px;
                    border-radius: 14px;
                    font-size: 14px;
                    line-height: 1.5;
                    color: var(--cb-text);
                    word-wrap: break-word;
                }
                .cb-message.user .cb-message-content {
                    background: linear-gradient(135deg, var(--cb-primary), var(--cb-secondary));
                    color: white;
                    border-bottom-right-radius: 4px;
                }
                .cb-message.bot .cb-message-content { border-bottom-left-radius: 4px; }
                .cb-message-content a { color: var(--cb-primary); text-decoration: underline; }
                .cb-message.user .cb-message-content a { color: #bbf7d0; }
                .cb-message-time {
                    font-size: 11px;
                    color: var(--cb-text-light);
                    margin-top: 4px;
                    text-align: right;
                }
                .cb-typing {
                    display: flex;
                    gap: 4px;
                    padding: 12px 16px;
                    align-self: flex-start;
                }
                .cb-typing-dot {
                    width: 8px;
                    height: 8px;
                    background: #cbd5e1;
                    border-radius: 50%;
                    animation: cb-typing-bounce 1.4s infinite ease-in-out;
                }
                .cb-typing-dot:nth-child(1) { animation-delay: 0s; }
                .cb-typing-dot:nth-child(2) { animation-delay: 0.2s; }
                .cb-typing-dot:nth-child(3) { animation-delay: 0.4s; }
                @keyframes cb-typing-bounce {
                    0%, 80%, 100% { transform: translateY(0); }
                    40% { transform: translateY(-8px); }
                }
                .cb-suggestions {
                    display: flex;
                    flex-wrap: wrap;
                    gap: 6px;
                    padding: 0 16px 8px;
                }
                .cb-suggestion {
                    background: white;
                    border: 1px solid var(--cb-border);
                    border-radius: 20px;
                    padding: 6px 14px;
                    font-size: 13px;
                    color: var(--cb-primary);
                    cursor: pointer;
                    transition: all 0.2s;
                    white-space: nowrap;
                }
                .cb-suggestion:hover {
                    background: var(--cb-primary);
                    color: white;
                    border-color: var(--cb-primary);
                }
                .cb-input-area {
                    padding: 12px 16px;
                    border-top: 1px solid var(--cb-border);
                    display: flex;
                    gap: 8px;
                    align-items: center;
                }
                .cb-input {
                    flex: 1;
                    border: 1px solid var(--cb-border);
                    border-radius: 24px;
                    padding: 10px 16px;
                    font-size: 14px;
                    outline: none;
                    transition: border-color 0.2s;
                    resize: none;
                    max-height: 100px;
                }
                .cb-input:focus { border-color: var(--cb-primary); }
                .cb-send-btn {
                    width: 40px;
                    height: 40px;
                    border-radius: 50%;
                    background: linear-gradient(135deg, var(--cb-primary), var(--cb-secondary));
                    border: none;
                    color: white;
                    cursor: pointer;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    transition: transform 0.2s;
                }
                .cb-send-btn:hover { transform: scale(1.05); }
                .cb-send-btn:disabled { opacity: 0.5; cursor: not-allowed; transform: none; }
                @media (max-width: 480px) {
                    .cb-window {
                        width: calc(100vw - 40px);
                        height: calc(100vh - 120px);
                        ${CONFIG.position === 'bottom-left' ? 'left: 0;' : 'right: 0;'}
                    }
                }
            </style>
        `;

        const html = `
            <div id="chatbot-widget">
                ${styles}
                <div class="cb-window" id="cb-window">
                    <div class="cb-header">
                        <div class="cb-header-avatar">
                            <img src="/static/rdv/images/dentist-avatar.png" style="width: 36px; height: 36px; border-radius: 50%; object-fit: cover;" alt="Dr. Assistant">
                        </div>
                        <div class="cb-header-info">
                            <div class="cb-header-name">${CONFIG.botName}</div>
                            <div class="cb-header-status">
                                <span class="cb-status-dot"></span>
                                En ligne
                            </div>
                        </div>
                        <button class="cb-header-close" id="cb-close">&times;</button>
                    </div>
                    <div class="cb-messages" id="cb-messages"></div>
                    <div class="cb-suggestions" id="cb-suggestions"></div>
                    <div class="cb-input-area">
                        <textarea class="cb-input" id="cb-input" placeholder="Ecrivez votre message..." rows="1"></textarea>
                        <button class="cb-send-btn" id="cb-send">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="18" height="18">
                                <path d="M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z"/>
                            </svg>
                        </button>
                    </div>
                </div>
                <div class="cb-bubble" id="cb-bubble">
                    <img src="/static/rdv/images/dentist-avatar.png" style="width: 40px; height: 40px; border-radius: 50%; object-fit: cover; border: 2px solid rgba(255,255,255,0.5);" alt="Dr. Assistant">
                </div>
            </div>
        `;

        const container = document.createElement('div');
        container.innerHTML = html;
        document.body.appendChild(container);

        document.getElementById('cb-bubble').addEventListener('click', toggleChat);
        document.getElementById('cb-close').addEventListener('click', toggleChat);
        document.getElementById('cb-send').addEventListener('click', sendMessage);
        document.getElementById('cb-input').addEventListener('keydown', handleKeyDown);
        document.getElementById('cb-input').addEventListener('input', autoResize);
    }

    function toggleChat() {
        state.isOpen = !state.isOpen;
        const window = document.getElementById('cb-window');
        if (state.isOpen) {
            window.classList.add('open');
            document.getElementById('cb-input').focus();
            scrollToBottom();
        } else {
            window.classList.remove('open');
        }
    }

    function handleKeyDown(e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    }

    function autoResize(e) {
        const textarea = e.target;
        textarea.style.height = 'auto';
        textarea.style.height = Math.min(textarea.scrollHeight, 100) + 'px';
    }

    function addUserMessage(text) {
        const container = document.getElementById('cb-messages');
        const el = document.createElement('div');
        el.className = 'cb-message user';
        el.innerHTML = `
            <div class="cb-message-avatar">${CONFIG.userAvatar}</div>
            <div>
                <div class="cb-message-content">${escapeHtml(text)}</div>
                <div class="cb-message-time">${formatTime(new Date())}</div>
            </div>
        `;
        container.appendChild(el);
        scrollToBottom();
        state.messages.push({ role: 'user', content: text });
    }

    function addBotMessage(text, suggestions) {
        const container = document.getElementById('cb-messages');
        const formattedText = formatMessage(text);
        const el = document.createElement('div');
        el.className = 'cb-message bot';
        el.innerHTML = `
            <div class="cb-message-avatar">
                <img src="/static/rdv/images/dentist-avatar.png" style="width: 24px; height: 24px; border-radius: 50%; object-fit: cover;" alt="Dr. Assistant">
            </div>
            <div>
                <div class="cb-message-content">${formattedText}</div>
                <div class="cb-message-time">${formatTime(new Date())}</div>
            </div>
        `;
        container.appendChild(el);
        scrollToBottom();
        state.messages.push({ role: 'assistant', content: text });
        if (suggestions && suggestions.length > 0) showSuggestions(suggestions);
    }

    function showTyping() {
        const container = document.getElementById('cb-messages');
        const el = document.createElement('div');
        el.className = 'cb-typing';
        el.id = 'cb-typing';
        el.innerHTML = `
            <div class="cb-message-avatar">
                <img src="/static/rdv/images/dentist-avatar.png" style="width: 24px; height: 24px; border-radius: 50%; object-fit: cover;" alt="Dr. Assistant">
            </div>
            <div class="cb-typing">
                <div class="cb-typing-dot"></div>
                <div class="cb-typing-dot"></div>
                <div class="cb-typing-dot"></div>
            </div>
        `;
        container.appendChild(el);
        scrollToBottom();
        state.isTyping = true;
    }

    function hideTyping() {
        const el = document.getElementById('cb-typing');
        if (el) el.remove();
        state.isTyping = false;
    }

    function showSuggestions(suggestions) {
        const container = document.getElementById('cb-suggestions');
        container.innerHTML = '';
        suggestions.forEach(suggestion => {
            const chip = document.createElement('button');
            chip.className = 'cb-suggestion';
            chip.textContent = suggestion;
            chip.addEventListener('click', () => {
                document.getElementById('cb-input').value = suggestion;
                sendMessage();
            });
            container.appendChild(chip);
        });
    }

    function clearSuggestions() {
        document.getElementById('cb-suggestions').innerHTML = '';
    }

    async function sendMessage() {
        const input = document.getElementById('cb-input');
        const text = input.value.trim();
        if (!text || state.isTyping) return;

        input.value = '';
        input.style.height = 'auto';
        clearSuggestions();
        addUserMessage(text);
        showTyping();

        try {
            const response = await fetch(CONFIG.apiBaseUrl, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCsrfToken(),
                },
                body: JSON.stringify({ message: text, session_id: state.sessionId }),
            });

            const data = await response.json();
            hideTyping();

            if (data.success) {
                state.conversationId = data.conversation_id;
                addBotMessage(data.reponse, data.suggestions);
            } else {
                addBotMessage("Desole, une erreur est survenue. Reessayez.", ['Reessayer', 'Contacter le cabinet']);
            }
        } catch (error) {
            hideTyping();
            addBotMessage("Probleme de connexion. Reessayez.", ['Reessayer', 'Contacter le cabinet']);
        }
    }

    async function loadHistory() {
        try {
            const response = await fetch(CONFIG.apiBaseUrl + 'history/?session_id=' + state.sessionId);
            const data = await response.json();
            if (data.success && data.messages.length > 0) {
                document.getElementById('cb-messages').innerHTML = '';
                data.messages.forEach(msg => {
                    if (msg.role === 'user') addUserMessage(msg.contenu);
                    else if (msg.role === 'assistant') addBotMessage(msg.contenu);
                });
            }
        } catch (error) {
            console.log('Pas d historique');
        }
    }

    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    function formatMessage(text) {
        text = text.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
        text = text.replace(/\[(.+?)\]\((.+?)\)/g, '<a href="$2" target="_blank">$1</a>');
        text = text.replace(/\n/g, '<br>');
        return text;
    }

    function formatTime(date) {
        return date.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' });
    }

    function scrollToBottom() {
        const container = document.getElementById('cb-messages');
        if (container) container.scrollTop = container.scrollHeight;
    }

    function getCsrfToken() {
        const cookie = document.cookie.split(';').find(c => c.trim().startsWith('csrftoken='));
        if (cookie) return cookie.split('=')[1];
        const input = document.querySelector('[name=csrfmiddlewaretoken]');
        if (input) return input.value;
        return '';
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();