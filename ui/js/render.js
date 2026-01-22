// Message Rendering Functions
function renderAssistant(text, charts) {
    const msg = document.createElement('div');
    msg.className = 'msg';

    const chartsHtml = (charts || []).map(c => {
        return `
            <div class="chart">
                <img src="${c.data}" alt="${escapeHtml(c.caption || 'Chart')}" />
                <div class="cap">${escapeHtml(c.caption || '')}</div>
            </div>
        `;
    }).join('');

    msg.innerHTML = `
        <div class="avatar bot"><i class="fa-solid fa-robot"></i></div>
        <div class="bubble">
            <div class="text">${marked.parse(text || '')}</div>
            ${chartsHtml}
        </div>
    `;
    messagesWrap.appendChild(msg);
    scrollToBottom();
}

function renderUser(text) {
    const msg = document.createElement('div');
    msg.className = 'msg';
    msg.innerHTML = `
        <div class="avatar user"><i class="fa-solid fa-user"></i></div>
        <div class="bubble"><div class="text">${escapeHtml(text)}</div></div>
    `;
    messagesWrap.appendChild(msg);
    scrollToBottom();
}

function renderError(text) {
    const wrap = document.createElement('div');
    wrap.className = 'error';
    wrap.innerHTML = `<i class="fa-solid fa-circle-exclamation"></i><div>${escapeHtml(text)}</div>`;
    messagesWrap.appendChild(wrap);
    scrollToBottom();
}

function addTyping() {
    const id = `typing-${Date.now()}`;
    const msg = document.createElement('div');
    msg.className = 'msg';
    msg.id = id;
    msg.innerHTML = `
        <div class="avatar bot"><i class="fa-solid fa-robot"></i></div>
        <div class="bubble">
            <div class="typing"><span class="dot"></span><span class="dot"></span><span class="dot"></span></div>
        </div>
    `;
    messagesWrap.appendChild(msg);
    scrollToBottom();
    return id;
}

function removeTyping(id) {
    const el = document.getElementById(id);
    if (el) el.remove();
}
