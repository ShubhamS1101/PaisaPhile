// Message Rendering Functions - Premium Analyst UI

// Get current theme's bull logo path
function getBotAvatarSrc() {
    const theme = document.documentElement.getAttribute('data-theme') || 'dark';
    return theme === 'dark' 
        ? '/templates/assets/logo/dark_mode/dark_mode_bull.svg'
        : '/templates/assets/logo/light_mode/light_mode_bull.svg';
}

/**
 * Render assistant message with optional charts in proper layout
 * Charts are displayed when planner assigns pattern/trend analysis
 */
function renderAssistant(text, charts) {
    const msg = document.createElement('div');
    msg.className = 'msg';

    // Parse charts and create proper layout
    const chartsList = charts || [];
    console.log('renderAssistant called with charts:', chartsList.length, chartsList);
    let chartsHtml = '';
    
    if (chartsList.length > 0) {
        // Use grid layout for multiple charts
        if (chartsList.length === 1) {
            chartsHtml = `
                <div class="chart">
                    <img src="${chartsList[0].data}" alt="${escapeHtml(chartsList[0].caption || 'Analysis Chart')}" />
                    <div class="cap">
                        <i class="fa-solid fa-chart-line"></i>
                        ${escapeHtml(chartsList[0].caption || 'Technical Analysis')}
                    </div>
                </div>
            `;
        } else {
            // Multiple charts - use grid layout
            const chartItems = chartsList.map((c, index) => {
                const type = detectChartType(c.caption || '');
                const icon = getChartIcon(type);
                return `
                    <div class="chart">
                        <img src="${c.data}" alt="${escapeHtml(c.caption || `Chart ${index + 1}`)}" />
                        <div class="cap">
                            <i class="fa-solid ${icon}"></i>
                            ${escapeHtml(c.caption || `Analysis ${index + 1}`)}
                        </div>
                    </div>
                `;
            }).join('');
            
            chartsHtml = `<div class="charts-grid">${chartItems}</div>`;
        }
    }

    msg.innerHTML = `
        <div class="avatar bot"><img src="${getBotAvatarSrc()}" alt="Bot" /></div>
        <div class="bubble">
            <div class="text">${marked.parse(text || '')}</div>
            ${chartsHtml}
        </div>
    `;
    messagesWrap.appendChild(msg);
    scrollToBottom();
}

/**
 * Detect chart type from caption
 */
function detectChartType(caption) {
    const lower = caption.toLowerCase();
    if (lower.includes('pattern')) return 'pattern';
    if (lower.includes('trend')) return 'trend';
    if (lower.includes('indicator') || lower.includes('rsi') || lower.includes('macd')) return 'indicator';
    if (lower.includes('support') || lower.includes('resistance')) return 'levels';
    return 'analysis';
}

/**
 * Get appropriate icon for chart type
 */
function getChartIcon(type) {
    const icons = {
        pattern: 'fa-shapes',
        trend: 'fa-arrow-trend-up',
        indicator: 'fa-gauge-high',
        levels: 'fa-layer-group',
        analysis: 'fa-chart-line'
    };
    return icons[type] || icons.analysis;
}

/**
 * Render analysis card for structured data display
 */
function renderAnalysisCard(title, content, type = 'default', confidence = null) {
    const msg = document.createElement('div');
    msg.className = 'msg';
    
    const badgeClass = type === 'warning' ? 'warning' : (type === 'risk' ? 'risk' : '');
    const badgeHtml = confidence !== null ? 
        `<span class="analysis-badge ${badgeClass}">${confidence}% Confidence</span>` : '';
    
    const icon = type === 'pattern' ? 'fa-shapes' : 
                 type === 'trend' ? 'fa-arrow-trend-up' :
                 type === 'indicator' ? 'fa-gauge-high' : 'fa-chart-line';
    
    msg.innerHTML = `
        <div class="avatar bot"><img src="${getBotAvatarSrc()}" alt="Bot" /></div>
        <div class="bubble">
            <div class="analysis-card">
                <div class="analysis-header">
                    <div class="analysis-title">
                        <i class="fa-solid ${icon}"></i>
                        ${escapeHtml(title)}
                    </div>
                    ${badgeHtml}
                </div>
                <div class="analysis-content">
                    ${marked.parse(content || '')}
                </div>
            </div>
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
        <div class="avatar bot"><img src="${getBotAvatarSrc()}" alt="Bot" /></div>
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
