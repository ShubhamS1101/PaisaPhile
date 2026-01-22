// API Communication
async function sendMessage() {
    const text = (composer.value || '').trim();
    if (!text || isProcessing || !sessionActive) return;

    renderUser(text);
    composer.value = '';
    composer.style.height = 'auto';

    const typingId = addTyping();
    isProcessing = true;
    composer.disabled = true;
    sendBtn.disabled = true;

    try {
        const res = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: text, config: pendingSettings })
        });
        const data = await res.json();
        removeTyping(typingId);
        if (data && data.success) {
            renderAssistant(data.response || '', data.charts || []);
        } else {
            renderError((data && data.error) ? data.error : 'An error occurred.');
        }
    } catch (_) {
        removeTyping(typingId);
        renderError('Failed to send message.');
    } finally {
        pendingSettings = null;
        isProcessing = false;
        composer.disabled = false;
        sendBtn.disabled = false;
        composer.focus();
    }
}
